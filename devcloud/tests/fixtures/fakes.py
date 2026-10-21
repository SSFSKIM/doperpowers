"""Stand-ins for everything a devcloud host reaches, for the integration
tests: Secret Manager (:8081), the GCE metadata server (:8082), the
configuration repository over git's smart HTTP behind basic auth (:8083, with
the public project repositories make-repo.sh adds beside it), and
the gateway (:8084), an Anthropic Messages API that runs one Bash call and
then answers "ok".

State lives in /srv/fakes: secrets.json ({secret id: value}, re-read on every
request so a test can rotate or remove one), and the logs the tests read —
sm.log (one secret id per access), gateway.jsonl (one line per request).
Every value here is made up for the tests."""

import base64
import http.server
import json
import os
import pathlib
import subprocess
import threading

STATE = pathlib.Path("/srv/fakes")
GIT_ROOT = "/srv/git"
PROJECT = "devcloud-test-project"
ACCESS_TOKEN = "fake-metadata-access-token"
# A prompt holding this asks for the bridge probe in place of the variables'.
BRIDGE_PROBE = "devcloud-bridge-probe"


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send(self, code, body, content_type="application/json", headers=()):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""


class SecretManager(Handler):
    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {ACCESS_TOKEN}":
            return self.send(401, {"error": {"code": 401, "status": "UNAUTHENTICATED"}})
        prefix = f"/v1/projects/{PROJECT}/secrets/"
        suffix = "/versions/latest:access"
        if not (self.path.startswith(prefix) and self.path.endswith(suffix)):
            return self.send(404, {"error": {"code": 404, "status": "NOT_FOUND"}})
        name = self.path[len(prefix):-len(suffix)]
        with open(STATE / "sm.log", "a") as log:
            log.write(name + "\n")
        values = json.loads((STATE / "secrets.json").read_text())
        if name not in values:
            return self.send(404, {"error": {"code": 404, "status": "NOT_FOUND"}})
        data = base64.b64encode(values[name].encode()).decode()
        self.send(200, {"name": f"projects/{PROJECT}/secrets/{name}/versions/1", "payload": {"data": data}})


class Metadata(Handler):
    def do_GET(self):
        if self.headers.get("Metadata-Flavor") != "Google":
            return self.send(403, b"missing Metadata-Flavor", "text/plain")
        paths = {
            "/computeMetadata/v1/instance/service-accounts/default/token":
                {"access_token": ACCESS_TOKEN, "expires_in": 3599, "token_type": "Bearer"},
            "/computeMetadata/v1/instance/service-accounts/default/email": "host@example.iam.gserviceaccount.com",
            "/computeMetadata/v1/project/project-id": PROJECT,
        }
        value = paths.get(self.path.split("?")[0])
        if value is None:
            return self.send(404, b"not found", "text/plain")
        if isinstance(value, str):
            return self.send(200, value.encode(), "application/text", [("Metadata-Flavor", "Google")])
        self.send(200, value, headers=[("Metadata-Flavor", "Google")])


class Git(Handler):
    """git http-backend; the configuration repository behind basic auth whose password is the bootstrap secret."""

    def authorized(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        _, _, password = base64.b64decode(header[6:]).decode().partition(":")
        return password == json.loads((STATE / "secrets.json").read_text()).get("config-token")

    def handle_git(self):
        # The configuration repository is private; the project repositories
        # beside it (example/*, standing in for GitHub's) are public.
        if self.path.startswith("/config.git") and not self.authorized():
            return self.send(401, b"auth required", "text/plain", [("WWW-Authenticate", 'Basic realm="config"')])
        path, _, query = self.path.partition("?")
        env = dict(os.environ, GIT_PROJECT_ROOT=GIT_ROOT, GIT_HTTP_EXPORT_ALL="1", PATH_INFO=path,
                   REQUEST_METHOD=self.command, QUERY_STRING=query, REMOTE_USER="devcloud",
                   CONTENT_TYPE=self.headers.get("Content-Type", ""),
                   CONTENT_LENGTH=self.headers.get("Content-Length", "0"),
                   HTTP_GIT_PROTOCOL=self.headers.get("Git-Protocol", ""),
                   HTTP_CONTENT_ENCODING=self.headers.get("Content-Encoding", ""))
        out = subprocess.run(["git", "http-backend"], input=self.body(), env=env, capture_output=True).stdout
        head, _, body = out.partition(b"\r\n\r\n")
        code = 200
        headers = []
        for line in head.decode().split("\r\n"):
            name, _, value = line.partition(": ")
            if name.lower() == "status":
                code = int(value.split()[0])
            elif name:
                headers.append((name, value))
        content_type = dict((k.lower(), v) for k, v in headers).pop("content-type", "text/plain")
        self.send(code, body, content_type, [(k, v) for k, v in headers if k.lower() != "content-type"])

    do_GET = handle_git
    do_POST = handle_git


class Gateway(Handler):
    def do_GET(self):
        if self.path.startswith("/v1/models"):
            return self.send(200, {"data": [], "has_more": False, "first_id": None, "last_id": None})
        self.send(200, b"gateway stand-in\n", "text/plain")

    def do_HEAD(self):
        self.send(200, b"", "text/plain")

    def do_POST(self):
        request = json.loads(self.body() or b"{}")
        path = self.path.split("?")[0]
        if path.endswith("/count_tokens"):
            return self.send(200, {"input_tokens": 1})
        if path != "/v1/messages":
            return self.send(404, {"type": "error", "error": {"type": "not_found_error", "message": path}})
        results = [block for message in request.get("messages", []) if isinstance(message.get("content"), list)
                   for block in message["content"] if block.get("type") == "tool_result"]
        tools = [tool.get("name") for tool in request.get("tools", [])]
        with open(STATE / "gateway.jsonl", "a") as log:
            log.write(json.dumps({
                "authorization": self.headers.get("Authorization") or self.headers.get("x-api-key") or "",
                "tools": tools, "tool_results": [_text(r.get("content")) for r in results],
            }) + "\n")
        model = request.get("model", "claude-stand-in")
        if "Bash" in tools and not results:
            probe = 'printf "%s|%s|%s" "$DEVCLOUD_PROBE_SYNCED" "$DEVCLOUD_PROBE_MANAGED" "$ANTHROPIC_BASE_URL"'
            if BRIDGE_PROBE in json.dumps(request.get("messages", [])):
                # The bridge's socket while the session runs, and a token-shaped
                # string (made up) the secrets guard turns into a handle.
                probe = ("ls -1 ~/.claude/sminos/bridge/ 2>/dev/null | grep -c 'sock$'; "
                         "printf 'ghp_%s%s\\n' Zq9XwT4vLp2Rk7Ny8Bm3Hc6Fd1Gs5Jx0 Ae4u")
            block = {"type": "tool_use", "id": "toolu_devcloud_probe", "name": "Bash",
                     "input": {"command": probe, "description": "Print the probe variables"}}
            stop = "tool_use"
        else:
            block = {"type": "text", "text": "ok"}
            stop = "end_turn"
        if request.get("stream"):
            return self.stream(model, block, stop)
        self.send(200, {"id": "msg_devcloud", "type": "message", "role": "assistant", "model": model,
                        "content": [block], "stop_reason": stop, "stop_sequence": None,
                        "usage": {"input_tokens": 1, "output_tokens": 1}})

    def stream(self, model, block, stop):
        events = [("message_start", {"type": "message_start", "message": {
            "id": "msg_devcloud", "type": "message", "role": "assistant", "model": model, "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}})]
        if block["type"] == "text":
            events += [("content_block_start", {"type": "content_block_start", "index": 0,
                                                "content_block": {"type": "text", "text": ""}}),
                       ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                                "delta": {"type": "text_delta", "text": block["text"]}})]
        else:
            events += [("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {
                           "type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}}),
                       ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {
                           "type": "input_json_delta", "partial_json": json.dumps(block["input"])}})]
        events += [("content_block_stop", {"type": "content_block_stop", "index": 0}),
                   ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                                      "usage": {"output_tokens": 1}}),
                   ("message_stop", {"type": "message_stop"})]
        data = "".join(f"event: {name}\ndata: {json.dumps(body)}\n\n" for name, body in events).encode()
        self.send(200, data, "text/event-stream", [("Cache-Control", "no-cache")])


def _text(content):
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content or [] if isinstance(part, dict))


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    servers = [http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
               for port, handler in ((8081, SecretManager), (8082, Metadata), (8083, Git), (8084, Gateway))]
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print("fakes: serving", flush=True)
    servers[0].serve_forever()


if __name__ == "__main__":
    main()

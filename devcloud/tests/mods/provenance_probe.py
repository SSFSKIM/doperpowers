#!/usr/bin/env python3
"""Offline native acceptance. Requires Claude Code and macOS sandbox-exec.

Only synthetic fixtures enter the isolated session. The Messages server binds
loopback; an OS network sandbox prevents the engine and children reaching any
other address. This is an acceptance run, not part of the mocked mod-test gate.
"""
import argparse
import base64
from contextlib import ExitStack
import hashlib
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import signal
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[2]
GENERIC = 'Ab3Cd4Ef5Gh6Ij7Kl8Mn9Op0'
STORED = 'stored-fixture-value-2468'
CREDENTIAL = 'credential-fixture-value-1357'
PROVIDER = 'ghp_' + 'Ab3Cd4Ef5Gh6Ij7Kl8Mn9Op0Qr1St2Uv3'
PEM = '-----BEGIN PRIVATE KEY-----\nsynthetic-fixture-only\n-----END PRIVATE KEY-----'


def helper():
    spec = importlib.util.spec_from_file_location('provenance', PLUGIN / 'hooks/mods/secrets-provenance.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixtures(base):
    root = base / 'prefix/lib/node_modules'
    pkg = root / 'probe-fixture'
    pkg.mkdir(parents=True)
    plain = 'const password = "' + GENERIC + '";\n'
    members = {
        'package.json': b'{"name":"probe-fixture","version":"1.0.0"}',
        'plain.js': plain.encode(),
        'timeout-one.js': plain.encode(),
        'timeout-two.js': plain.encode(),
        'abort.js': plain.encode(),
        'tabs.js': ('\t' + plain + '\t// second\r\n').encode(),
        'partial.js': ('// before\n' + plain + '// after\n').encode(),
        'paginated.js': (plain + '// filler alpha beta gamma delta epsilon\n' * 5000).encode(),
        'strong.js': (plain + '\n'.join([STORED, CREDENTIAL, PROVIDER, PEM]) + '\n').encode(),
    }
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w:gz') as out:
        for name, data in members.items():
            (pkg / name).write_bytes(data)
            entry = tarfile.TarInfo('package/' + name)
            entry.size = len(data)
            out.addfile(entry, io.BytesIO(data))
    blob = archive.getvalue()
    doc = {'name': 'probe-fixture', 'version': '1.0.0', 'dist': {
        'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(blob).digest()).decode(),
        'tarball': 'https://registry.npmjs.org/probe-fixture/-/probe-fixture-1.0.0.tgz'}}
    p = helper()
    # Synthetic publisher boundary only. Real archive validation, index builder,
    # verifier, native Read, hooks, mapper and transcript are not substituted.
    with patch.dict(os.environ, {'XDG_CACHE_HOME': str(base / 'cache')}), \
            patch.object(p, 'discover', return_value={'npmRoot': str(root), 'npmCache': str(base / 'npm-cache'), 'gcloudRoot': None}), \
            patch.object(p, 'fetch_public', side_effect=lambda url, limit: blob if url.endswith('.tgz') else json.dumps(doc).encode()):
        result = p.build_index(fetch=True, project_root=base / 'project')
        assert result['sources']['npm']['verifiedFiles'] == len(members), 'fixture index incomplete'
    (pkg / 'unknown.js').write_text(plain)
    return pkg


class Messages:
    def __init__(self, calls, base):
        self.calls = calls
        self.base = base
        self.child_checks = {}
        self.results = {}
        self.requests = 0
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.reply({'data': [], 'has_more': False})

            def reply(self, value):
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                owner.requests += 1
                if 'count_tokens' in self.path:
                    self.reply({'input_tokens': max(1, len(json.dumps(req.get('messages', []))) // 4)})
                    return
                # Side requests are answered, but never advance the main script.
                main = any(tool.get('name') == 'Read' for tool in req.get('tools', []))
                for msg in req.get('messages', []) if main else []:
                    for block in msg.get('content', []) if isinstance(msg.get('content'), list) else []:
                        if block.get('type') == 'tool_result':
                            owner.results[block['tool_use_id']] = block
                            name = block['tool_use_id'].removeprefix('probe_')
                            marker = owner.base / (name + '.pid')
                            if name.startswith('timeout-') and name not in owner.child_checks and marker.exists():
                                pid, started, _ = json.loads(marker.read_text())
                                owner.child_checks[name] = {'gone': not alive(pid), 'seconds': time.monotonic() - started}
                pending = next((call for call in owner.calls if call['id'] not in owner.results), None) if main else None
                content = [pending] if pending else [{'type': 'text', 'text': 'Synthetic acceptance complete.'}]
                message = {'id': 'msg_probe', 'type': 'message', 'role': 'assistant',
                           'model': req.get('model', 'claude-opus-5-5'), 'content': content,
                           'stop_reason': 'tool_use' if pending else 'end_turn', 'stop_sequence': None,
                           'usage': {'input_tokens': 100, 'output_tokens': 10}}
                if not req.get('stream'):
                    self.reply(message)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                def event(kind, data):
                    self.wfile.write(('event: ' + kind + '\ndata: ' + json.dumps({'type': kind, **data}) + '\n\n').encode())
                event('message_start', {'message': {**message, 'content': [], 'stop_reason': None}})
                for i, block in enumerate(content):
                    field = 'input' if block['type'] == 'tool_use' else 'text'
                    event('content_block_start', {'index': i, 'content_block': {**block, field: {} if field == 'input' else ''}})
                    delta = {'type': 'input_json_delta', 'partial_json': json.dumps(block['input'])} if field == 'input' else {'type': 'text_delta', 'text': block['text']}
                    event('content_block_delta', {'index': i, 'delta': delta})
                    event('content_block_stop', {'index': i})
                event('message_delta', {'delta': {'stop_reason': message['stop_reason'], 'stop_sequence': None}, 'usage': {'output_tokens': 10}})
                event('message_stop', {})
                self.wfile.flush()

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def check_results(rows, results):
    for name in ['plain', 'partial', 'tabs', 'paginated', 'strong', 'unknown', 'timeout-one', 'timeout-two']:
        call_id = 'probe_' + name
        row = next((r for r in rows if r.get('toolUseResult') and any(b.get('tool_use_id') == call_id for b in r.get('message', {}).get('content', []) if isinstance(b, dict))), None)
        assert row, name + ': native structured transcript row missing'
        source = row['toolUseResult']['file']['content']
        block = next(b for b in row['message']['content'] if b.get('tool_use_id') == call_id)
        rendered = json.dumps(block['content'])
        immediate = json.dumps(results.get(call_id, {}))
        assert call_id in results, name + ': no immediate model-facing result'
        for value in [source, rendered, immediate]:
            assert (GENERIC in value) == (name not in ['unknown', 'timeout-one', 'timeout-two']), name + ': generic preservation/fallback failed'
            if name == 'strong':
                assert all(secret not in value for secret in [STORED, CREDENTIAL, PROVIDER, 'synthetic-fixture-only']), 'strong: secret survived'
                assert '[secret:' in value and '[redacted:' in value, 'strong: handles missing'
        if name == 'partial':
            assert row['toolUseResult']['file']['startLine'] == 2, 'partial: wrong source slice'
        if name == 'tabs':
            assert '\r' not in source, 'tabs: expected native CRLF normalization'
            assert isinstance(block['content'], str) and block['content'].startswith(('1\t\t', '1:\t')), 'tabs: unsupported native separator'
        if name == 'paginated':
            assert row['toolUseResult']['file']['numLines'] < row['toolUseResult']['file']['totalLines'], 'pagination did not occur'
            assert row['toolUseResult']['file'].get('truncatedByTokenCap') is True, 'native pagination flag missing'
            assert any(r.get('attachment', {}).get('type') == 'read_truncation_notice' and r['attachment'].get('toolUseID') == call_id for r in rows), 'native pagination companion attachment missing'
        print('PASS native ' + name + ': immediate, structured persistence, appended text')


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def fault_interpreter(base):
    """A hung verifier child, not a mocked process.run or fabricated result."""
    binary = base / 'bin'
    binary.mkdir()
    wrapper = binary / 'python3'
    wrapper.write_text('#!' + sys.executable + '\n' + '''import json, os, pathlib, sys, time
if 'verify' in sys.argv:
    raw = sys.stdin.buffer.read()
    request = json.loads(raw)
    name = pathlib.Path(request['inputPath']).stem
    if name.startswith('timeout-') or name == 'abort':
        marker = pathlib.Path(os.environ['PROBE_BASE']) / (name + '.pid')
        pending = marker.with_suffix('.pending')
        pending.write_text(json.dumps([os.getpid(), time.monotonic(), int(sys.argv[-1])]))
        pending.replace(marker)
        while True:
            time.sleep(60)
    read, write = os.pipe()
    os.write(write, raw)
    os.close(write)
    os.dup2(read, 0)
    os.close(read)
os.execv(''' + repr(sys.executable) + ''', [''' + repr(sys.executable) + ''', *sys.argv[1:]])
''')
    wrapper.chmod(0o700)
    return binary


def abort_probe(command, env, base, pkg):
    call = {'type': 'tool_use', 'id': 'probe_abort', 'name': 'Read', 'input': {'file_path': str(pkg / 'abort.js')}}
    with Messages([call], base) as messages:
        url = 'http://127.0.0.1:' + str(messages.server.server_port)
        abort_env = {**env, 'ANTHROPIC_BASE_URL': url, 'HTTP_PROXY': url, 'HTTPS_PROXY': url, 'ALL_PROXY': url}
        # The SDK interrupt exercises the native hook abort signal while its
        # process.run child is alive. Killing the engine would not prove this.
        args = command[:]
        args[args.index('--output-format') + 1] = 'stream-json'
        args += ['--input-format', 'stream-json', '--verbose']
        args.remove('Run the synthetic acceptance script.')
        proc = subprocess.Popen(args, cwd=base / 'project', env=abort_env, text=True,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = [], []
        readers = [threading.Thread(target=lambda pipe=pipe, target=target: target.extend(pipe), daemon=True)
                   for pipe, target in [(proc.stdout, out), (proc.stderr, err)]]
        for reader in readers:
            reader.start()
        pid = None
        try:
            proc.stdin.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': 'Run the synthetic abort fixture.'}}) + '\n')
            proc.stdin.flush()
            marker = base / 'abort.pid'
            deadline = time.monotonic() + 30
            while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert marker.exists(), 'abort: native verifier child never started'
            pid, started, remaining_ms = json.loads(marker.read_text())
            assert alive(pid), 'abort: child was not alive before interrupt'
            start = time.monotonic()
            assert remaining_ms / 1000 - (start - started) > 1.0, 'abort: insufficient time to distinguish interrupt from timeout'
            proc.stdin.write(json.dumps({'type': 'control_request', 'request_id': 'probe-interrupt', 'request': {'subtype': 'interrupt'}}) + '\n')
            proc.stdin.flush()
            while alive(pid) and time.monotonic() - start < 0.75:
                time.sleep(0.01)
            assert not alive(pid), 'abort: verifier survived native interruption (before stage timeout)'
            assert proc.poll() is None, 'abort: engine exited instead of cancelling the child'
            print('PASS native abort: live verifier child disappeared before deadline; engine remained alive')
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=5)
            for reader in readers:
                reader.join(timeout=2)
            if pid and alive(pid):
                os.kill(pid, signal.SIGKILL)


def run(engine):
    if sys.platform != 'darwin' or not shutil.which('sandbox-exec'):
        raise RuntimeError('native acceptance requires macOS sandbox-exec for loopback-only networking; other platforms are unproved')
    with tempfile.TemporaryDirectory(prefix='guard-native-probe-') as temp, ExitStack() as cleanup:
        base = Path(temp).resolve()
        def stop_children():
            # Acceptance checks happen while the engine lives. This last-resort
            # cleanup also owns children on a failed assertion or launch timeout.
            for marker in base.glob('*.pid'):
                pid = json.loads(marker.read_text())[0]
                if alive(pid):
                    os.kill(pid, signal.SIGKILL)
        cleanup.callback(stop_children)
        for name in ['home', 'config', 'cache', 'project', 'tmp']:
            (base / name).mkdir()
        # Copy only the runtime plugin, never personal configuration or sessions.
        plugin = base / 'plugin'
        for name in ['hooks', 'types', '.claude-plugin']:
            shutil.copytree(PLUGIN / name, plugin / name)
        pkg = fixtures(base)
        binary = fault_interpreter(base)
        store = base / 'home/.config/claude-secrets'
        store.mkdir(parents=True)
        (store / 'PROBE_STORED').write_text(STORED)
        (base / 'home/.netrc').write_text('machine fixture.example login probe password ' + CREDENTIAL + '\n')
        calls = [{'type': 'tool_use', 'id': 'probe_' + name, 'name': 'Read', 'input': {'file_path': str(pkg / (name + '.js')), **({'offset': 2, 'limit': 1} if name == 'partial' else {})}} for name in ['plain', 'partial', 'tabs', 'paginated', 'strong', 'unknown', 'timeout-one', 'timeout-two']]
        with Messages(calls, base) as messages:
            url = 'http://127.0.0.1:' + str(messages.server.server_port)
            env = {'PATH': str(binary) + os.pathsep + os.environ['PATH'], 'PROBE_BASE': str(base), 'HOME': str(base / 'home'), 'TMPDIR': str(base / 'tmp'),
                   'CLAUDE_CONFIG_DIR': str(base / 'config'), 'XDG_CACHE_HOME': str(base / 'cache'),
                   'ANTHROPIC_BASE_URL': url, 'ANTHROPIC_API_KEY': 'synthetic-probe-key',
                   'CLAUDE_CODE_ENABLE_FUNCTION_HOOKS': '1', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1',
                   'DISABLE_TELEMETRY': '1', 'DISABLE_ERROR_REPORTING': '1', 'DISABLE_AUTOUPDATER': '1',
                   'CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY': '1', 'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '1',
                   'HTTP_PROXY': url, 'HTTPS_PROXY': url, 'ALL_PROXY': url, 'NO_PROXY': '127.0.0.1,localhost'}
            profile = '(version 1) (allow default) (deny network*) (allow network* (remote ip "localhost:*"))'
            command = ['sandbox-exec', '-p', profile, engine, '-p', 'Run the synthetic acceptance script.',
                       '--model', 'claude-opus-5-5', '--plugin-dir', str(plugin), '--setting-sources', '',
                       '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--tools', 'Read',
                       '--allowedTools', 'Read', '--add-dir', str(pkg), '--output-format', 'json',
                       '--debug-file', str(base / 'debug.log')]
            result = subprocess.run(command, cwd=base / 'project', env=env, text=True, capture_output=True, timeout=90)
            if result.returncode:
                raise RuntimeError('native launch failed: ' + result.stderr[-2000:] + result.stdout[-2000:])
            rows = []
            for transcript in (base / 'config/projects').rglob('*.jsonl'):
                rows.extend(json.loads(line) for line in transcript.read_text().splitlines() if line)
            try:
                check_results(rows, messages.results)
            except (AssertionError, TypeError, KeyError):
                # All artifacts are synthetic; optional local diagnostics never
                # persist by default or point at the person's transcript tree.
                if os.environ.get('PROVENANCE_PROBE_DIAGNOSTICS'):
                    dest = Path(os.environ['PROVENANCE_PROBE_DIAGNOSTICS'])
                    shutil.copytree(base, dest, dirs_exist_ok=True)
                raise
            for name in ['timeout-one', 'timeout-two']:
                check = messages.child_checks.get(name)
                assert check and check['gone'], name + ': verifier child survived to next native request'
                assert check['seconds'] < 3, name + ': provenance deadline overran'
            print('PASS native repeated timeouts: children gone before next request, full fallback, no hook overrun')
            print('PASS loopback-only native requests: ' + str(messages.requests))
        abort_probe(command, env, base, pkg)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', default=shutil.which('claude'))
    args = parser.parse_args()
    if not args.engine:
        parser.error('native engine missing; pass --engine')
    run(args.engine)


if __name__ == '__main__':
    main()

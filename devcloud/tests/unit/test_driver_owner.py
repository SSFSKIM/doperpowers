"""`devcloud vm owner <name> <thread>` (EN.G1's plan, M2; Interfaces §5): a
host handed to another thread of this machine.

- The order: the host's write (the tag and the project's id), then the
  provider's label or the adoption record, then both read back; the lines
  it prints, a host with no owner before, nothing differing.
- Each refusal before anything is asked of a host or a provider, and
  `sminos who --thread`'s own failures.
- A host that refuses (a departure, a notice being sent), a lost reply on
  either side, what the host is read to hold, the reversed completion of two
  runs, a label write that did not land; run again, it settles.
- X9's answer for the two short ids afterwards.
- The owner program's own text, run against a temporary host: its two
  modes, its send lock, a parser that predates the project key.

Hermetic: the stand-in provider and stand-in hosts (driver_fixtures), and a
temporary host directory for the program.
Run: python3 -m unittest discover -s devcloud/tests/unit -p test_driver_owner.py"""
import fcntl
import json
import shlex
import shutil
import stat
import subprocess
import sys
import time

import _path  # noqa: F401
from driver import adopt, cli, context, hostctl, owned
from driver.errors import DriverError
from driver.ssh import Result

from driver_fixtures import NOW, SESSION, DriverBase, thread_answer, vm_labels
from test_lease import BASE

NAME = "dc-a-0001"
OLD = "abcd1234"
SHORT = SESSION[:8]
PROGRAM = _path.DEVCLOUD / "driver" / "owner_host.py"


class FakeHost:
    """A host as the owner program finds it: what its descriptor holds and
    whether its parser takes the project key. `on_write(tag, project)`, when
    set, answers the write instead (a host that refuses, or one whose answer
    is lost); `read_fails` makes every read go unanswered."""

    def __init__(self, remote, tag=f"@{OLD}", project="example", takes_project=True):
        self.state = {"tag": tag, "project": project, "takes_project": takes_project}
        self.writes, self.reads, self.inputs = [], 0, []
        self.on_write = None
        self.read_fails = False
        remote.on("python3 -P - write", fn=self.write)
        remote.on("python3 -P - read", fn=self.read)
        self.remote = remote

    def apply(self, tag, project):
        self.state["tag"] = tag
        if self.state["takes_project"]:
            self.state["project"] = project

    def answer(self):
        return Result(0, json.dumps(self.state) + "\n", "", False)

    def write(self, target, command):
        words = shlex.split(command)
        tag, project = words[4], words[5]
        self.writes.append((target, tag, project))
        if self.on_write:
            return self.on_write(tag, project)
        self.apply(tag, project)
        return self.answer()

    def read(self, target, command):
        self.reads += 1
        if self.read_fails:
            return Result(255, "", "ssh: connect to host: Connection timed out", False)
        return self.answer()


class OwnerBase(DriverBase):
    def setUp(self):
        super().setUp()
        self.threads["builder"] = thread_answer()
        self.host = FakeHost(self.remote)

    def vm(self, creator=OLD, **extra):
        labels = vm_labels(lifetime="keep", **extra)
        if creator:
            labels["devcloud-creator"] = creator
        return self.add_server(NAME, labels)

    def label(self):
        return self.servers()[NAME]["labels"].get("devcloud-creator")

    def owner(self, given="builder", name=NAME):
        """(exit, stdout, stderr) of `devcloud vm owner <name> <given>`."""
        for stream in (self.out, self.err):
            stream.truncate(0)
            stream.seek(0)
        code = cli.main(["owner", name, given], ctx=self.ctx, host_marker=self.tmp / "no-boot.env")
        return code, self.out.getvalue(), self.err.getvalue()

    def nothing_sent(self):
        self.assertEqual(self.remote.commands("python3 -P"), [], "nothing asked of the host")


class HandedOn(OwnerBase):
    def test_a_vm_takes_the_host_then_the_label_and_says_who_owned_it_and_who_does(self):
        self.vm()
        before = dict(self.servers()[NAME]["labels"])
        code, out, err = self.owner()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.host.writes, [(NAME, f"@{SHORT}", "p-7c1e9a")], "one command, the project by its id")
        self.assertEqual(self.host.state, {"tag": f"@{SHORT}", "project": "p-7c1e9a", "takes_project": True})
        self.assertEqual(self.remote.calls[0]["input"], PROGRAM.read_bytes(), "the program on standard input")
        after = self.servers()[NAME]["labels"]
        self.assertEqual(after, dict(before, **{"devcloud-creator": SHORT}), "every other label as it was")
        self.assertEqual(out, f"{NAME} was owned by @{OLD}; builder#{SHORT} (example on testmac) owns it now\n")
        self.assertEqual(err, "")

    def test_the_project_goes_by_its_id_whatever_its_name(self):
        for name in ("shared-name", "two words"):
            with self.subTest(name=name):
                self.state_file.write_text(json.dumps({"servers": [], "images": [], "deleted": [], "calls": [],
                                                       "behavior": {}}))
                self.vm()
                self.host.writes.clear()
                self.threads["builder"] = thread_answer(project={"id": "p-5d2b", "name": name})
                code, out, err = self.owner()
                self.assertEqual(code, 0, err)
                self.assertEqual(self.host.writes[-1][2], "p-5d2b")
                self.assertIn(f"({name} on testmac)", out)

    def test_an_adopted_machine_takes_the_record_and_its_lease_stays(self):
        adopt.save(self.ctx, adopt.Record(name="lab-box", address="203.0.113.50", user="root", lifetime="ttl",
                                          expires=NOW + 7200, projects=[], phase="booted", created=NOW - 600,
                                          ready=NOW - 60, creator=OLD))
        code, out, err = self.owner(name="lab-box")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.host.writes, [("lab-box", f"@{SHORT}", "p-7c1e9a")])
        record = adopt.load(self.ctx, "lab-box")
        self.assertEqual((record.creator, record.expires, record.lifetime), (SHORT, NOW + 7200, "ttl"))
        self.assertEqual(self.ops(), [], "no provider call")
        self.assertIn("lab-box was owned by @abcd1234; builder#e5f6a7b8", out)

    def test_a_host_with_no_owner_before(self):
        self.vm(creator=None)
        self.host.state.update(tag=None, project=None)
        code, out, err = self.owner()
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"{NAME} had no owner; builder#{SHORT} (example on testmac) owns it now\n")
        self.assertEqual(self.label(), SHORT)

    def test_run_when_nothing_differs_says_so_and_writes_no_label(self):
        self.vm(creator=SHORT)
        self.host.apply(f"@{SHORT}", "p-7c1e9a")
        code, out, err = self.owner()
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"{NAME} is owned by builder#{SHORT} (example on testmac) already\n")
        self.assertNotIn("set-labels", self.ops())

    def test_after_a_handover_x9_answers_owned_for_the_new_short_and_none_for_the_old(self):
        self.vm()
        self.assertEqual(self.owner()[0], 0)
        for short, answer in ((SHORT, "owned"), (OLD, "none")):
            with self.subTest(short=short):
                self.out.truncate(0)
                self.out.seek(0)
                self.assertEqual(owned.run(self.ctx, [short]), 0)
                got = json.loads(self.out.getvalue())
                self.assertEqual(got["answer"], answer)
                self.assertEqual([vm["name"] for vm in got["vms"]], [NAME] if answer == "owned" else [])


class Refusals(OwnerBase):
    ROWS = [
        ("a session that is no thread", dict(thread="", opened=""),
         "owner: builder is a session, not a thread (one the MAWS app launched keeps MAWS's rules), and a VM is "
         "owned by a thread: nothing was changed"),
        ("a vacant seat", dict(session="", short=""),
         "owner: builder holds no session (a vacant seat); fill it first: nothing was changed"),
        ("another machine's thread", dict(local=False, machine="mini"),
         f"owner: builder#{SHORT} is a thread of mini, and a VM is handed to a thread of the machine this runs on, "
         "the only place sminos asks devcloud what a thread owns: run it on mini; nothing was changed"),
        ("an ended thread", dict(ended=True, state="retired"),
         "owner: builder has ended (retired, or stopped for three days), and a VM is handed to a thread that has "
         "not: nothing was changed"),
        ("a project not read", dict(project=None),
         "owner: sminos could not read builder's project from here (its directory is in a folder macOS protects): "
         "run it from inside that folder; nothing was changed"),
    ]

    def test_each_refusal_changes_nothing_and_asks_no_host(self):
        self.vm()
        adopt.save(self.ctx, adopt.Record(name="lab-box", address="203.0.113.50", user="root", lifetime="keep",
                                          expires=None, projects=[], phase="booted", created=NOW, creator=OLD))
        for what, over, words in self.ROWS:
            for name in (NAME, "lab-box"):
                with self.subTest(what=what, name=name):
                    self.threads["builder"] = thread_answer(**over)
                    code, out, err = self.owner(name=name)
                    self.assertEqual((code, out), (1, ""))
                    self.assertEqual(err, f"devcloud vm: {words}\n")
        code, out, err = self.owner("nobody")
        self.assertEqual(code, 1)
        self.assertIn("owner: sminos names no thread for nobody", err)
        self.nothing_sent()
        self.assertEqual(self.label(), OLD)
        self.assertEqual(adopt.load(self.ctx, "lab-box").creator, OLD)
        self.assertNotIn("set-labels", self.ops())
        self.assertNotIn("list", self.ops(), "decided before any provider is asked")

    def test_fewer_than_two_arguments_is_usage_and_on_a_host_exit_6(self):
        marker = self.tmp / "boot.env"
        self.assertEqual(cli.main(["owner", NAME], ctx=self.ctx, host_marker=self.tmp / "no-boot.env"), 2)
        marker.write_text("")
        self.assertEqual(cli.main(["owner", NAME, "builder"], ctx=self.ctx, host_marker=marker), 6)
        self.nothing_sent()


class SminosAnswer(DriverBase):
    """Context.thread as it is built: `sminos who --thread`, found as
    session_creator finds sminos."""

    def sminos(self, script):
        bindir = self.tmp / "bin"
        bindir.mkdir(exist_ok=True)
        path = bindir / "sminos"
        path.write_text("#!/bin/sh\n" + script + "\n")
        path.chmod(0o755)
        return {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(self.tmp / "home")}

    def refusal(self, env, name="builder"):
        with self.assertRaises(DriverError) as caught:
            context.sminos_thread(env, name)
        return caught.exception.code, str(caught.exception)

    def test_its_answer_its_refusals_and_a_copy_that_predates_the_flag(self):
        answer = thread_answer()
        env = self.sminos(f"[ \"$1 $2 $3\" = 'who --thread builder' ] || exit 9\necho '{json.dumps(answer)}'")
        self.assertEqual(context.sminos_thread(env, "builder"), answer)
        self.assertEqual(self.refusal({"PATH": str(self.tmp / "empty"), "HOME": str(self.tmp / "home")}),
                         (1, "owner: no sminos CLI was found, and only sminos says which thread a name is: nothing "
                             "was changed"))
        self.assertEqual(self.refusal(self.sminos("echo 'usage: sminos ...' >&2; exit 2")),
                         (1, "owner: this machine's sminos does not answer who --thread (it is older than 1.53.0): "
                             "update the sminos plugin; nothing was changed"))
        self.assertEqual(self.refusal(self.sminos("echo \"sminos: no seat or member matching 'builder'\" >&2; exit 4")),
                         (1, "owner: sminos names no thread for builder (sminos: no seat or member matching "
                             "'builder'): nothing was changed"))
        self.assertEqual(self.refusal(self.sminos("echo 'not an answer'")),
                         (1, "owner: sminos names no thread for builder (it printed no answer): nothing was changed"))
        self.assertEqual(self.refusal(self.sminos(f"echo '{json.dumps(dict(answer, local='yes'))}'")),
                         (1, "owner: sminos names no thread for builder (it printed no answer): nothing was changed"))


class HostRefuses(OwnerBase):
    def test_a_departure_or_a_notice_being_sent_changes_nothing(self):
        self.vm()
        for code, words in ((3, f"{NAME}'s departure has started; its owner stays as it is"),
                            (4, f"{NAME} is sending a notice now, and a handover waits for it, so that none goes to "
                                "the thread that gives the host up once it is done: nothing was changed; run it "
                                "again in a minute")):
            with self.subTest(code=code):
                self.host.on_write = lambda tag, project, code=code: Result(code, "", "devcloud owner: …", False)
                got, out, err = self.owner()
                self.assertEqual((got, out, err), (1, "", f"devcloud vm: {words}\n"))
                self.assertEqual(self.label(), OLD)
        self.assertNotIn("set-labels", self.ops())


class LostReply(OwnerBase):
    def lost(self, apply=None, out="", err="ssh: Connection to dc-a-0001 closed by remote host.", code=255):
        """A write whose answer does not come back; `apply(tag, project)`, the
        part of it that landed on the host."""
        def write(tag, project):
            if apply:
                apply(tag, project)
            return Result(code, out, err, False)
        self.host.on_write = write

    def test_no_whole_answer_but_the_host_holds_what_was_written_goes_on(self):
        for code, err in ((255, "ssh: Connection to dc-a-0001 closed by remote host."), (255, "\n(timed out)")):
            with self.subTest(err=err):
                self.state_file.write_text(json.dumps({"servers": [], "images": [], "deleted": [], "calls": [],
                                                       "behavior": {}}))
                self.vm()
                self.host.apply(f"@{OLD}", "example")
                self.lost(apply=self.host.apply, err=err, code=code)
                got, out, err_ = self.owner()
                self.assertEqual(got, 0, err_)
                self.assertEqual(self.label(), SHORT)
                self.assertIn("owns it now", out)

    def test_no_whole_answer_and_another_project_on_the_host_is_said_with_the_label_untouched(self):
        self.vm()
        self.lost(apply=lambda tag, project: self.host.state.update(tag=tag, project="p-other"))
        code, out, err = self.owner()
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err, f"devcloud vm: {NAME} gave no whole answer to the new owner (no exit status: ssh: "
                              f"Connection to dc-a-0001 closed by remote host.) and holds @{SHORT} with project "
                              f"p-other now; the command may still be running there. Nothing else was changed: run "
                              f"devcloud vm owner {NAME} builder again to settle it\n")
        self.assertEqual(self.label(), OLD)

    def test_no_whole_answer_and_the_old_tag_never_says_it_did_nothing(self):
        self.vm()
        self.lost(code=1, err="devcloud owner: unknown key DEVCLOUD_X in the boot descriptor")
        code, out, err = self.owner()
        self.assertEqual(code, 1)
        self.assertIn(f"gave no whole answer to the new owner (exit 1: devcloud owner: unknown key DEVCLOUD_X in the "
                      f"boot descriptor) and holds @{OLD} with project example now; the command may still be "
                      "running there", err)
        self.assertNotIn("did nothing", err)
        self.assertEqual(self.label(), OLD)

    def test_no_whole_answer_and_no_read_is_not_known(self):
        self.vm()
        self.lost()
        self.host.read_fails = True
        code, out, err = self.owner()
        self.assertEqual(code, 1)
        self.assertEqual(err, f"devcloud vm: {NAME} gave no answer about its owner (no exit status: ssh: Connection "
                              f"to dc-a-0001 closed by remote host.): what it holds is not known, and nothing else "
                              f"was changed; run devcloud vm owner {NAME} builder again\n")
        self.assertEqual(self.label(), OLD)

    def test_an_answer_of_another_shape_or_another_owner_is_no_answer_and_the_host_is_read(self):
        """A reply missing a key (a null is never taken from an absent one),
        and a whole reply naming another owner than the one asked for: the
        recovery read decides, and the label moves only when it holds."""
        for reply, lands in (({"takes_project": True}, False), ({"tag": "@0f1e2d3c", "project": "p-2222",
                                                                   "takes_project": True}, False),
                             ({"tag": "@0f1e2d3c", "project": "p-2222", "takes_project": True}, True)):
            with self.subTest(reply=reply, lands=lands):
                self.state_file.write_text(json.dumps({"servers": [], "images": [], "deleted": [], "calls": [],
                                                       "behavior": {}}))
                self.vm()
                self.host.apply(f"@{OLD}", "example")

                def write(tag, project, reply=reply, lands=lands):
                    if lands:
                        self.host.apply(tag, project)
                    return Result(0, json.dumps(reply) + "\n", "", False)
                self.host.on_write = write
                code, out, err = self.owner()
                if lands:
                    self.assertEqual(code, 0, err)
                    self.assertEqual(self.label(), SHORT)
                else:
                    self.assertEqual((code, out), (1, ""))
                    self.assertIn(f"gave no whole answer to the new owner (", err)
                    self.assertIn(f"and holds @{OLD} with project example now", err)
                    self.assertEqual(self.label(), OLD, "the label never moves past a host left as it was")

    def test_the_providers_reply_lost_after_the_label_was_written_is_settled_by_the_read_back(self):
        self.vm()
        self.behave(fail_after=["set-labels"])
        code, out, err = self.owner()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.label(), SHORT)
        self.assertIn("owns it now", out)


class ReadBack(OwnerBase):
    def test_the_new_tag_beside_the_old_project_is_not_settled(self):
        self.vm()

        def write(tag, project):
            answer = dict(self.host.state, tag=tag, project=project)
            self.host.state["tag"] = tag          # the project's line did not land
            return Result(0, json.dumps(answer) + "\n", "", False)
        self.host.on_write = write
        code, out, err = self.owner()
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err, f"devcloud vm: {NAME}'s owner is not settled: the host, which sends its notices, holds "
                              f"@{SHORT} with project example, and its provider's label, which decides whom sminos "
                              f"refuses to retire, names @{SHORT}; this run wrote @{SHORT} with project p-7c1e9a. "
                              f"Another devcloud vm owner ran at the same time, or a write did not land: run devcloud "
                              f"vm owner {NAME} builder again to settle it\n")

    def test_a_host_whose_parser_does_not_take_the_project_is_settled_on_the_tag_with_a_second_line(self):
        self.vm()
        self.host.state.update(project=None, takes_project=False)
        code, out, err = self.owner()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.host.state["project"], None)
        self.assertEqual(out.splitlines()[1], f"{NAME} was built before a host kept its owner's project: a notice no "
                                              "session of builder takes ends in its journal")

    def test_a_host_that_cannot_be_read_at_the_end_is_said_so(self):
        self.vm()
        real = self.host.write

        def write(target, command):
            got = real(target, command)
            self.host.read_fails = True
            return got
        self.remote.rules[0]["fn"] = write
        code, out, err = self.owner()
        self.assertEqual(code, 1)
        self.assertIn("the host, which sends its notices, holds what could not be read, and its provider's label", err)

    def test_two_runs_completing_in_reverse_order_are_said_and_one_run_again_settles(self):
        self.vm()
        other = "0f1e2d3c"

        def write(tag, project):
            self.host.apply(tag, project)
            answer = self.host.answer()
            # Another run's two writes land between this run's host write and its label write.
            self.host.apply(f"@{other}", "p-2222")
            data = self.state()
            data["servers"][0]["labels"]["devcloud-creator"] = other
            self.state_file.write_text(json.dumps(data))
            return answer
        self.host.on_write = write
        code, out, err = self.owner()
        self.assertEqual((code, out), (1, ""))
        self.assertIn(f"holds @{other} with project p-2222, and its provider's label, which decides whom sminos "
                      f"refuses to retire, names @{SHORT}; this run wrote @{SHORT}", err)
        self.host.on_write = None
        code, out, err = self.owner()
        self.assertEqual(code, 0, err)
        self.assertEqual((self.host.state["tag"], self.label()), (f"@{SHORT}", SHORT))

    def test_a_label_write_that_did_not_land_is_not_settled_and_run_again_finishes(self):
        self.vm()
        self.behave(fail={"set-labels": 1})
        code, out, err = self.owner()
        self.assertEqual(code, 1)
        self.assertIn(f"holds @{SHORT} with project p-7c1e9a, and its provider's label, which decides whom sminos "
                      f"refuses to retire, names @{OLD}", err)
        self.behave(fail={})
        code, out, err = self.owner()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.label(), SHORT)

    def adopted(self):
        adopt.save(self.ctx, adopt.Record(name="lab-box", address="203.0.113.50", user="root", lifetime="keep",
                                          expires=None, projects=[], phase="booted", created=NOW, creator=OLD))

    def test_a_record_that_cannot_be_written_or_read_is_said_from_both_sides(self):
        self.adopted()
        real = adopt._write

        def full(ctx, record):
            raise OSError(28, "No space left on device")
        adopt._write = full
        try:
            code, out, err = self.owner(name="lab-box")
        finally:
            adopt._write = real
        self.assertEqual((code, out), (1, ""))
        self.assertIn("lab-box's adoption record: No space left on device", err)
        self.assertIn(f"lab-box's owner is not settled: the host, which sends its notices, holds @{SHORT} with "
                      f"project p-7c1e9a, and this Mac's adoption record, which decides whom sminos refuses to "
                      f"retire, names @{OLD}", err)
        self.assertNotIn("Traceback", err)

        def corrupt(tag, project):
            adopt.path(self.ctx, "lab-box").write_text("{not json")
            self.host.apply(tag, project)
            return self.host.answer()
        self.host.on_write = corrupt
        code, out, err = self.owner(name="lab-box")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("and this Mac's adoption record, which decides whom sminos refuses to retire, names what could "
                      "not be read", err)

    def test_an_adoption_record_removed_meanwhile_writes_nothing_more(self):
        adopt.save(self.ctx, adopt.Record(name="lab-box", address="203.0.113.50", user="root", lifetime="keep",
                                          expires=None, projects=[], phase="booted", created=NOW, creator=OLD))

        def write(tag, project):
            adopt.path(self.ctx, "lab-box").unlink()
            self.host.apply(tag, project)
            return self.host.answer()
        self.host.on_write = write
        code, out, err = self.owner(name="lab-box")
        self.assertEqual((code, err), (1, "devcloud vm: lab-box's adoption record was removed while this ran (the "
                                          "machine was released): nothing more was written\n"))
        self.assertIsNone(adopt.load(self.ctx, "lab-box"))


# --- the owner program, run as the driver sends it, against a temporary host ------------------------


class Program(DriverBase):
    def setUp(self):
        super().setUp()
        self.host_dir = self.tmp / "host"
        (self.host_dir / "run").mkdir(parents=True)
        self.desc = self.host_dir / "boot.env"
        self.desc.write_text(BASE + 'DEVCLOUD_CREATOR="@abcd1234"\n')
        self.desc.chmod(0o600)
        self.status = self.host_dir / "status.json"
        self.devcloud = _path.DEVCLOUD / "boot" / "devcloud"

    def host_args(self, wait=None):
        out = ["--descriptor", str(self.desc), "--lock", str(self.host_dir / "run" / "lifecycle.lock"),
               "--send-lock", str(self.host_dir / "run" / "notices.lock"), "--status", str(self.status),
               "--devcloud", str(self.devcloud)]
        return out + (["--wait", str(wait)] if wait is not None else [])

    def program(self, *args, wait=None):
        done = subprocess.run([sys.executable, "-P", "-", *args, *self.host_args(wait)], input=PROGRAM.read_bytes(),
                              capture_output=True, timeout=60)
        return done.returncode, done.stdout.decode(), done.stderr.decode()

    def test_write_rewrites_the_two_keys_and_no_other_line(self):
        self.desc.write_text(BASE.replace("DEVCLOUD_ROLE=persistent\n", "# who runs here\nexport DEVCLOUD_ROLE=persistent\n")
                             + 'DEVCLOUD_CREATOR="@abcd1234"\nDEVCLOUD_EXPIRES=1792000000\nDEVCLOUD_CREATOR="@0000ffff"\n'
                             + "DEVCLOUD_CREATOR_PROJECT=example")
        self.desc.chmod(0o640)
        code, out, err = self.program("write", f"@{SHORT}", "p-7c1e9a")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"tag": f"@{SHORT}", "project": "p-7c1e9a", "takes_project": True})
        self.assertEqual(self.desc.read_text(),
                         BASE.replace("DEVCLOUD_ROLE=persistent\n", "# who runs here\nexport DEVCLOUD_ROLE=persistent\n")
                         + f'DEVCLOUD_CREATOR="@{SHORT}"\nDEVCLOUD_EXPIRES=1792000000\n'
                         + 'DEVCLOUD_CREATOR_PROJECT="p-7c1e9a"\n')
        self.assertEqual(stat.S_IMODE(self.desc.stat().st_mode), 0o640, "the file's own mode")

    def test_write_appends_a_missing_key(self):
        self.desc.write_text(BASE)
        code, out, err = self.program("write", f"@{SHORT}", "p-7c1e9a")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.desc.read_text(), BASE + f'DEVCLOUD_CREATOR="@{SHORT}"\nDEVCLOUD_CREATOR_PROJECT="p-7c1e9a"\n')

    def test_read_answers_as_the_hosts_parser_reads_and_writes_nothing(self):
        before = (self.desc.read_text(), self.desc.stat().st_mtime_ns)
        code, out, err = self.program("read")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"tag": "@abcd1234", "project": None, "takes_project": True})
        self.assertEqual((self.desc.read_text(), self.desc.stat().st_mtime_ns), before)

    def test_exit_3_once_the_departure_has_started(self):
        self.status.write_text(json.dumps({"steps": [], "lifecycle": {"op": "depart", "state": "departing"}}))
        before = self.desc.read_text()
        code, out, err = self.program("write", f"@{SHORT}", "p-7c1e9a")
        self.assertEqual((code, out), (3, ""), err)
        self.assertEqual(self.desc.read_text(), before)

    def test_exit_4_while_a_notice_is_sent_past_the_wait_and_the_write_made_once_it_lets_go(self):
        before = self.desc.read_text()
        lock = self.host_dir / "run" / "notices.lock"
        with open(lock, "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            code, out, err = self.program("write", f"@{SHORT}", "p-7c1e9a", wait=0.3)
            self.assertEqual((code, out), (4, ""), err)
            self.assertEqual(self.desc.read_text(), before)
            waiting = subprocess.Popen([sys.executable, "-P", "-", "write", f"@{SHORT}", "p-7c1e9a", *self.host_args(5)],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            waiting.stdin.write(PROGRAM.read_bytes())
            waiting.stdin.close()
            time.sleep(0.5)
            self.assertIsNone(waiting.poll(), "it waits for the notice")
            self.assertEqual(self.desc.read_text(), before)
            fcntl.flock(held, fcntl.LOCK_UN)
        self.assertEqual(waiting.wait(30), 0, waiting.stderr.read())
        waiting.stdout.close()
        waiting.stderr.close()
        self.assertIn(f'DEVCLOUD_CREATOR="@{SHORT}"', self.desc.read_text())

    def test_a_parser_that_predates_the_project_key_takes_the_tag_alone(self):
        older = self.tmp / "older"
        shutil.copytree(_path.DEVCLOUD / "boot", older, ignore=shutil.ignore_patterns("__pycache__"))
        parser = older / "devcloudlib" / "descriptor.py"
        parser.write_text(parser.read_text().replace(', "DEVCLOUD_CREATOR_PROJECT")', ")"))
        self.devcloud = older / "devcloud"
        code, out, err = self.program("write", f"@{SHORT}", "p-7c1e9a")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"tag": f"@{SHORT}", "project": None, "takes_project": False})
        self.assertNotIn("DEVCLOUD_CREATOR_PROJECT", self.desc.read_text(), "the key its parser would refuse")
        self.assertEqual(json.loads(self.program("read")[1])["takes_project"], False)

    def test_a_text_that_would_not_parse_is_not_written(self):
        before = self.desc.read_text()
        code, out, err = self.program("write", "not-a-tag", "p-7c1e9a")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("is not a sminos tag", err)
        self.assertEqual(self.desc.read_text(), before)

    def test_usage(self):
        self.assertEqual(self.program("write", "@x")[0], 2)
        self.assertEqual(self.program("erase")[0], 2)

    def test_the_driver_sends_this_text_and_reads_its_answer(self):
        """owner_set and host_owner, each through a stand-in ssh that runs
        the command it was given, as root on this temporary host."""
        def run(target, command):
            done = subprocess.run(shlex.split(command.replace("python3", sys.executable, 1)) + self.host_args(),
                                  input=PROGRAM.read_bytes(), capture_output=True, timeout=60)
            return Result(done.returncode, done.stdout.decode(), done.stderr.decode(), False)
        self.remote.on("python3 -P - ", fn=run)
        host = hostctl.Host(name=NAME, alias="devcloud-main-500", public=None)
        self.assertEqual(hostctl.owner_set(self.ctx, host, f"@{SHORT}", "p-7c1e9a"),
                         hostctl.HostOwner(f"@{SHORT}", "p-7c1e9a", True))
        self.assertEqual(hostctl.host_owner(self.ctx, host), hostctl.HostOwner(f"@{SHORT}", "p-7c1e9a", True))
        self.assertEqual([c["input"] for c in self.remote.calls], [PROGRAM.read_bytes()] * 2)
        self.assertEqual([c["user"] for c in self.remote.calls], ["root"] * 2)


if __name__ == "__main__":
    import unittest
    unittest.main()

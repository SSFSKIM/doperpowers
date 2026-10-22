"""Synthetic public artifacts: test publication evidence, not local-cache consistency."""
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[2] / 'hooks/mods/secrets-provenance.py'
spec = importlib.util.spec_from_file_location('provenance', HELPER)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as out:
        for name, data in members:
            info = tarfile.TarInfo(name)
            if isinstance(data, str):
                info.type = tarfile.SYMTYPE
                info.linkname = data
                out.addfile(info)
            else:
                info.size = len(data)
                out.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / 'prefix/lib/node_modules'
        self.pkg = self.root / 'fixture'
        self.pkg.mkdir(parents=True)
        self.project = self.base / 'project'
        self.project.mkdir()
        self.cache = self.base / 'cache'
        self.npm_cache = self.base / 'npm-cache'
        self.env = patch.dict(os.environ, {'XDG_CACHE_HOME': str(self.cache)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.content = b'const password = "synthetic-distribution-constant";\nsecond\n'
        self.manifest = b'{"name":"fixture","version":"1.2.3"}'
        (self.pkg / 'package.json').write_bytes(self.manifest)
        (self.pkg / 'index.js').write_bytes(self.content)
        self.tar = archive([('package/package.json', self.manifest), ('package/index.js', self.content)])
        self.url = 'https://registry.npmjs.org/fixture/1.2.3'
        self.tar_url = 'https://registry.npmjs.org/fixture/-/fixture-1.2.3.tgz'
        self.doc = {'name': 'fixture', 'version': '1.2.3', 'dist': {
            'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(self.tar).digest()).decode(),
            'tarball': self.tar_url}}
        self.responses = {self.url: json.dumps(self.doc).encode(), self.tar_url: self.tar}

    def fetch(self, url, limit):
        return self.responses[url]

    def build(self, fetch=True, gcloud=None):
        with patch.object(p, 'discover', return_value={
            'npmRoot': str(self.root), 'npmCache': str(self.npm_cache),
            'gcloudRoot': str(gcloud) if gcloud else None}), patch.object(p, 'fetch_public', side_effect=self.fetch):
            return p.build_index(fetch=fetch, project_root=self.project)

    def request(self, file=None, **kwargs):
        path = str(file or self.pkg / 'index.js')
        req = {'inputPath': path, 'filePath': path, 'projectRoot': str(self.project),
               'startLine': 1, 'lineCount': 3, 'contentBytes': len(self.content), 'newline': 'preserve'}
        req.update(kwargs)
        return req

    def verify(self, **kwargs):
        return p.verify(self.request(**kwargs))

    def test_public_distribution_and_partial_slice(self):
        result = self.build()
        self.assertEqual(result['sources']['npm']['verifiedFiles'], 2)
        answer = self.verify()
        self.assertEqual(answer['status'], 'verified')
        self.assertEqual(answer['fileSha256'], sha(self.content))
        self.assertEqual(answer['sliceSha256'], sha(self.content))
        self.assertEqual(answer['generation'], result['generation'])
        partial = self.verify(startLine=2, lineCount=1, contentBytes=6)
        self.assertEqual(partial['sliceSha256'], sha(b'second'))
        self.assertEqual(self.verify(startLine=2, lineCount=1, contentBytes=5)['reason'], 'unsupported_slice')

    def test_modification_addition_and_rebuild_do_not_adopt_local_bytes(self):
        self.build()
        (self.pkg / 'index.js').write_bytes(b'password = "local-synthetic-value"')
        (self.pkg / 'generated.js').write_bytes(self.content)
        self.assertEqual(self.verify()['reason'], 'changed_bytes')
        self.assertEqual(self.verify(file=self.pkg / 'generated.js')['reason'], 'nonmember')
        rebuilt = self.build(fetch=False)
        self.assertEqual(rebuilt['sources']['npm']['verifiedFiles'], 1)
        self.assertEqual(rebuilt['sources']['npm']['skipped']['changed_bytes'], 1)
        self.assertEqual(self.verify()['reason'], 'nonmember')

    def test_marker_change_is_stale_even_when_source_is_unchanged(self):
        self.build()
        (self.pkg / 'package.json').write_bytes(self.manifest + b'\n')
        self.assertEqual(self.verify()['reason'], 'stale_metadata')

    def test_project_and_linked_checkout_are_excluded(self):
        self.build()
        self.assertEqual(self.verify(projectRoot=str(self.pkg))['reason'], 'excluded_path')
        outside = self.base / 'checkout'
        outside.mkdir()
        (outside / 'package.json').write_bytes(self.manifest)
        (outside / 'index.js').write_bytes(self.content)
        (self.root / 'linked').symlink_to(outside, target_is_directory=True)
        self.build()
        self.assertEqual(self.verify(file=self.root / 'linked/index.js')['status'], 'unknown')
        (self.root.parent / '.git').mkdir()
        self.assertEqual(self.build()['sources']['npm']['verifiedFiles'], 0)

    def test_manifest_inside_examples_does_not_create_package_boundary(self):
        (self.pkg / 'examples').mkdir()
        (self.pkg / 'examples/package.json').write_text('{"name":"unpublished","version":"1.0.0"}')
        self.assertEqual(self.build()['sources']['npm']['verifiedFiles'], 2)

    def test_unavailable_public_evidence_is_not_local_baseline(self):
        self.assertEqual(self.build(fetch=False)['sources']['npm']['verifiedFiles'], 0)
        self.assertEqual(self.verify()['status'], 'unknown')

    def test_local_tarball_with_public_identity_must_match_public_checksum(self):
        local = archive([('package/package.json', self.manifest), ('package/index.js', b'local-only')])
        self.responses[self.tar_url] = local
        result = self.build()
        self.assertEqual(result['sources']['npm']['verifiedFiles'], 0)
        self.assertEqual(result['sources']['npm']['skipped']['checksum_mismatch'], 1)

    def test_unpublished_and_nonpublic_metadata_are_not_evidence(self):
        for doc in ({'name': 'other', 'version': '1.2.3', 'dist': self.doc['dist']},
                    dict(self.doc, dist=dict(self.doc['dist'], tarball='https://private.example/pkg.tgz'))):
            with self.subTest(doc=doc):
                self.responses[self.url] = json.dumps(doc).encode()
                self.assertEqual(self.build()['sources']['npm']['verifiedFiles'], 0)

    def test_archive_ambiguity_links_and_traversal_reject_evidence(self):
        bad = [ [('package/index.js', b'a'), ('package/index.js', b'b')],
                [('package/../escape', b'a')], [('package/index.js', '../outside')],
                [('/package/index.js', b'a')], [('package/./index.js', b'a')]]
        for members in bad:
            with self.subTest(members=members):
                with self.assertRaises(p.EvidenceError):
                    p.archive_digests(archive(members), 'npm')

    def test_archive_and_file_bounds(self):
        with patch.object(p, 'MAX_ARCHIVE_BYTES', 10):
            with self.assertRaises(p.EvidenceError):
                p.archive_digests(self.tar, 'npm')
        with patch.object(p, 'MAX_EXPANDED_BYTES', 10):
            with self.assertRaises(p.EvidenceError):
                p.archive_digests(self.tar, 'npm')
        with patch.object(p, 'MAX_ARCHIVE_ENTRIES', 1):
            with self.assertRaises(p.EvidenceError):
                p.archive_digests(self.tar, 'npm')
        self.build()
        with patch.object(p, 'MAX_FILE_BYTES', 10):
            self.assertEqual(self.verify(lineCount=1, contentBytes=0)['reason'], 'oversized_file')

    def test_missing_malformed_and_incompatible_index(self):
        self.assertEqual(self.verify()['reason'], 'missing_index')
        self.build()
        db = p.cache_dir() / 'index.sqlite3'
        db.write_bytes(b'not sqlite')
        self.assertEqual(self.verify()['reason'], 'invalid_index')
        self.build()
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE metadata SET value='{}'")
        self.assertEqual(self.verify()['reason'], 'invalid_index')

    def test_verify_has_no_network_archive_discovery_or_cache_traversal(self):
        self.build()
        with patch.object(p, 'fetch_public', side_effect=AssertionError('network')), \
             patch.object(p, 'archive_digests', side_effect=AssertionError('archive')), \
             patch.object(p, 'discover', side_effect=AssertionError('discovery')), \
             patch.object(p, 'npm_cache_entries', side_effect=AssertionError('cache traversal')):
            self.assertEqual(self.verify()['status'], 'verified')

    def test_failed_build_retains_previous_generation(self):
        old = self.build()
        with patch.object(p, 'discover', side_effect=RuntimeError('failed discovery')):
            with self.assertRaises(RuntimeError):
                p.build_index(fetch=False, project_root=self.project)
        self.assertEqual(self.verify()['generation'], old['generation'])

    def test_private_metadata_only_cache_and_read_only_verify(self):
        self.build()
        cache = p.cache_dir()
        before = {str(f): f.stat().st_mtime_ns for f in cache.rglob('*') if f.is_file()}
        self.assertEqual(self.verify()['status'], 'verified')
        self.assertEqual(before, {str(f): f.stat().st_mtime_ns for f in cache.rglob('*') if f.is_file()})
        for f in cache.rglob('*'):
            self.assertEqual(f.stat().st_mode & 0o077, 0)
            if f.is_file():
                self.assertNotIn(b'synthetic-distribution-constant', f.read_bytes())
        roots = json.loads((cache / 'roots.json').read_text())
        self.assertEqual(roots['roots'], [str(self.root)])

    def test_verify_protocol_and_timeout_exit_without_child_processes(self):
        self.build()
        run = subprocess.run([sys.executable, '-I', str(HELPER), 'verify'],
                             input=json.dumps(self.request()), text=True, capture_output=True, timeout=3)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'], 'verified')
        proc = subprocess.Popen([sys.executable, '-I', str(HELPER), 'verify', '--timeout-ms', '50'],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            proc.wait(timeout=2)  # Deliberately keep stdin open: the helper must bound preflight too.
            self.assertEqual(json.loads(proc.stdout.read())['reason'], 'timeout')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdin.close()
            proc.stdout.close()
            proc.stderr.close()

    def cache_npm(self, url, data):
        integrity = 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode()
        digest = hashlib.sha512(data).hexdigest()
        blob = self.npm_cache / '_cacache/content-v2/sha512' / digest[:2] / digest[2:4] / digest[4:]
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(data)
        payload = json.dumps({'key': 'make-fetch-happen:request-cache:' + url,
                              'integrity': integrity, 'time': 1}).encode()
        index = self.npm_cache / '_cacache/index-v5/aa/bb' / sha(url.encode())
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_bytes(hashlib.sha1(payload).hexdigest().encode() + b'\t' + payload + b'\n')

    def test_offline_npm_cache_requires_public_document_and_exact_tarball(self):
        # A complete cacache fixture, not a mocked cache lookup.
        self.cache_npm('https://registry.npmjs.org/fixture',
                       json.dumps({'name': 'fixture', 'versions': {'1.2.3': self.doc}}).encode())
        self.cache_npm(self.tar_url, self.tar)
        with patch.object(p, 'fetch_public', side_effect=AssertionError('offline network')):
            self.assertEqual(self.build(fetch=False)['sources']['npm']['verifiedFiles'], 2)
        self.assertEqual(self.verify()['status'], 'verified')

    def test_private_cached_document_and_local_only_artifact_are_unknown(self):
        self.cache_npm('https://private.example/fixture', json.dumps(self.doc).encode())
        self.cache_npm(self.tar_url, self.tar)
        self.assertEqual(self.build(fetch=False)['sources']['npm']['verifiedFiles'], 0)
        self.cache_npm(self.url, json.dumps(self.doc).encode())
        self.cache_npm(self.tar_url, archive([('package/index.js', b'locally packed')]))
        self.assertEqual(self.build(fetch=False)['sources']['npm']['verifiedFiles'], 0)

    def test_scoped_nested_dependencies_are_separate_boundaries(self):
        nested = self.pkg / 'node_modules/@scope/child'
        nested.mkdir(parents=True)
        manifest = b'{"name":"@scope/child","version":"2.0.0"}'
        (nested / 'package.json').write_bytes(manifest)
        (nested / 'index.js').write_bytes(self.content)
        tar = archive([('package/package.json', manifest), ('package/index.js', self.content)])
        url = 'https://registry.npmjs.org/@scope%2Fchild/2.0.0'
        tar_url = 'https://registry.npmjs.org/@scope/child/-/child-2.0.0.tgz'
        self.responses[url] = json.dumps({'name': '@scope/child', 'version': '2.0.0', 'dist': {
            'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(tar).digest()).decode(),
            'tarball': tar_url}}).encode()
        self.responses[tar_url] = tar
        self.assertEqual(self.build()['sources']['npm']['verifiedFiles'], 4)
        self.assertEqual(self.verify(file=nested / 'index.js')['status'], 'verified')
        (nested / 'package.json').write_bytes(manifest + b'\n')
        self.assertEqual(self.verify(file=nested / 'index.js')['reason'], 'stale_metadata')
        self.assertEqual(self.verify()['status'], 'verified')

    def test_project_symlink_cannot_borrow_global_membership(self):
        self.build()
        linked = self.project / 'node_modules'
        linked.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.verify(file=linked / 'fixture/index.js')['reason'], 'excluded_path')

    def test_crlf_unicode_and_binary_slice_policy(self):
        for content, newline, expected in [(b'first\r\n\tsecond\r\n', 'preserve', b'\tsecond\r'),
                                           (b'first\r\n\tsecond\r\n', 'lf', b'\tsecond'),
                                           ('first\nα\U0001f600\n'.encode(), 'preserve', 'α\U0001f600'.encode())]:
            with self.subTest(newline=newline, content=content):
                (self.pkg / 'index.js').write_bytes(content)
                tar = archive([('package/index.js', content)])
                doc = dict(self.doc, dist=dict(self.doc['dist'],
                           integrity='sha512-' + base64.b64encode(hashlib.sha512(tar).digest()).decode()))
                # Fresh evidence namespace for each synthetic publication.
                with tempfile.TemporaryDirectory() as cache, patch.dict(os.environ, {'XDG_CACHE_HOME': cache}):
                    self.responses[self.url] = json.dumps(doc).encode()
                    self.responses[self.tar_url] = tar
                    self.build()
                    answer = self.verify(startLine=2, lineCount=1, contentBytes=len(expected), newline=newline)
                    self.assertEqual(answer['sliceSha256'], sha(expected))
        for content in (b'\x00binary', b'\xffinvalid', b'\x01control'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as cache, \
                 patch.dict(os.environ, {'XDG_CACHE_HOME': cache}):
                (self.pkg / 'index.js').write_bytes(content)
                tar = archive([('package/index.js', content)])
                doc = dict(self.doc, dist=dict(self.doc['dist'],
                           integrity='sha512-' + base64.b64encode(hashlib.sha512(tar).digest()).decode()))
                self.responses[self.url] = json.dumps(doc).encode()
                self.responses[self.tar_url] = tar
                self.build()
                self.assertEqual(self.verify(lineCount=1, contentBytes=len(content))['reason'], 'unsupported_slice')

    def test_archive_expansion_counts_headers_not_only_regular_member_sizes(self):
        # Tar's extended headers are decompressed before a member is yielded.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz', format=tarfile.PAX_FORMAT) as out:
            info = tarfile.TarInfo('package/index.js')
            info.pax_headers = {'comment': 'a' * 20000}
            out.addfile(info, io.BytesIO())
        with patch.object(p, 'MAX_EXPANDED_BYTES', 10000):
            with self.assertRaises(p.EvidenceError):
                p.archive_digests(buf.getvalue(), 'npm')

    def test_malformed_owner_evidence_and_request_are_unknown(self):
        self.build()
        db = p.cache_dir() / 'index.sqlite3'
        with sqlite3.connect(db) as conn:
            record = json.loads(conn.execute('SELECT record FROM packages LIMIT 1').fetchone()[0])
            record.pop('evidence')
            conn.execute('UPDATE packages SET record=?', (json.dumps(record),))
        self.assertEqual(self.verify()['status'], 'unknown')
        for request in ({}, [], {'inputPath': 'relative'}, self.request(startLine=True),
                        self.request(lineCount=0), self.request(newline='guess')):
            self.assertEqual(p.verify(request)['status'], 'unknown')

    def test_metadata_change_between_discovery_and_comparison_is_not_adopted(self):
        original = p.Builder.add_package
        def changing(builder, *args, **kwargs):
            (self.pkg / 'package.json').write_bytes(self.manifest + b'\n')
            return original(builder, *args, **kwargs)
        with patch.object(p.Builder, 'add_package', changing):
            self.assertEqual(self.build()['sources']['npm']['verifiedFiles'], 0)

    def test_cli_offline_index_uses_caller_path_without_host_imports(self):
        self.cache_npm(self.url, json.dumps(self.doc).encode())
        self.cache_npm(self.tar_url, self.tar)
        binaries = self.base / 'bin'
        binaries.mkdir()
        npm = binaries / 'npm'
        npm.write_text('#!/bin/sh\ncase "$1" in\nroot) printf "%s\\n" "$FIXTURE_NPM_ROOT";;\n'
                       'config) printf "%s\\n" "$FIXTURE_NPM_CACHE";;\nesac\n')
        npm.chmod(0o700)
        cli = HELPER.parents[2] / 'bin/devcloud'
        env = dict(os.environ, PATH=os.pathsep.join((str(binaries), str(Path(sys.executable).parent), '/usr/bin', '/bin')),
                   FIXTURE_NPM_ROOT=str(self.root), FIXTURE_NPM_CACHE=str(self.npm_cache))
        run = subprocess.run([str(cli), 'guard', 'index'], cwd=self.project, env=env,
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['sources']['npm']['verifiedFiles'], 2)

    def test_cli_status_is_user_level_and_does_not_need_host_libraries(self):
        self.build()
        boot = HELPER.parents[2] / 'boot/devcloud'
        run = subprocess.run([sys.executable, str(boot), 'guard', 'status', '--json'],
                             text=True, capture_output=True, timeout=3)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['sources']['npm']['verifiedFiles'], 2)

    def test_gcloud_requires_public_release_archive_not_local_snapshot_checksum(self):
        sdk = self.base / 'sdk'
        install = sdk / '.install'
        install.mkdir(parents=True)
        (sdk / 'lib').mkdir()
        (sdk / 'lib/source.py').write_bytes(self.content)
        (sdk / 'lib/generated.pyc').write_bytes(self.content)
        (install / 'core.manifest').write_text('lib/source.py\n')
        snapshot = {'version': '999.0.0', 'components': [{'id': 'core',
                    'version': {'version_string': '999', 'build_number': 1},
                    'data': {'contents_checksum': 'a' * 64, 'source': '', 'type': 'tar'}}]}
        (install / 'core.snapshot.json').write_text(json.dumps(snapshot))
        self.assertEqual(self.build(fetch=False, gcloud=sdk)['sources']['gcloud']['verifiedFiles'], 0)
        tar = archive([('lib/source.py', self.content)])
        url = 'https://dl.google.com/dl/cloudsdk/channels/rapid/components-v999.0.0.json'
        tar_url = 'https://dl.google.com/dl/cloudsdk/channels/rapid/components/core.tar.gz'
        public = json.loads(json.dumps(snapshot))
        public['components'][0]['data'] = {'checksum': sha(tar), 'source': 'components/core.tar.gz',
                                          'size': len(tar), 'type': 'tar'}
        self.responses[url] = json.dumps(public).encode()
        self.responses[tar_url] = tar
        self.assertEqual(self.build(gcloud=sdk)['sources']['gcloud']['verifiedFiles'], 1)
        self.assertEqual(self.verify(file=sdk / 'lib/source.py')['status'], 'verified')
        self.assertEqual(self.verify(file=sdk / 'lib/generated.pyc')['reason'], 'nonmember')
        (install / 'core.manifest').write_text('lib/source.py\nlib/generated.pyc\n')
        self.assertEqual(self.verify(file=sdk / 'lib/source.py')['reason'], 'stale_metadata')


if __name__ == '__main__':
    unittest.main()

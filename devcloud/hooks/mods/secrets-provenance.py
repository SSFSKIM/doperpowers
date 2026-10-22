#!/usr/bin/env python3
"""Public distribution evidence for the secrets guard (Python 3.9+, stdlib only).

Out of band: python3 -I secrets-provenance.py index [--fetch]
Inspection:  python3 -I secrets-provenance.py status --json
Hot path:    python3 -I secrets-provenance.py verify [--timeout-ms REMAINING]

verify reads one JSON object from stdin (at most 16 KiB):
  inputPath, filePath, projectRoot: absolute paths
  startLine: 1-based; lineCount: number of source lines, including a trailing
    empty line if present; contentBytes: UTF-8 byte length of file.content
  newline: "preserve" or "lf" (only CRLF is normalized by the latter)
It returns status=verified with schemaVersion, policyVersion, generation,
canonicalPath, fileSha256, byteSize, sliceSha256 and the four slice fields;
otherwise status=unknown with a fixed reason. No content crosses this protocol.
A caller must still compare sliceSha256 with its result and bind the rendering.
The caller owns the whole-stage deadline; --timeout-ms is only its remainder.

Cache v1: index.sqlite3, roots.json (a non-authoritative candidate screen),
documents/ (sanitized public checksum metadata), evidence/ (artifact member
hashes). No downloaded source bytes, installed contents or receipts persist.
"""
import argparse
import base64
import binascii
from collections import Counter
from contextlib import closing
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

SCHEMA_VERSION = 1
POLICY_VERSION = 1
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_DATABASE_BYTES = 256 * 1024 * 1024
MAX_REQUEST_BYTES = 16 * 1024
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 100000
MAX_ROOTS = 64
NPM_ORIGIN = 'https://registry.npmjs.org/'
GCLOUD_ORIGIN = 'https://dl.google.com/dl/cloudsdk/channels/rapid/'


class EvidenceError(Exception):
    """An ordinary coverage loss, reported only by a fixed category."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def cache_dir():
    explicit = os.environ.get('XDG_CACHE_HOME')
    if explicit and os.path.isabs(explicit):
        root = Path(explicit)
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library/Caches'
    else:
        root = Path.home() / '.cache'
    return root / 'devcloud/guard-provenance/v1'


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def atomic_json(path, value):
    private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def bounded_read(path, cap):
    """Regular files only; O_NONBLOCK also prevents opening a substituted FIFO."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise EvidenceError('nonregular_file')
        if before.st_size > cap:
            raise EvidenceError('oversized_file')
        data = stream.read(cap + 1)
        after = os.fstat(stream.fileno())
        if len(data) > cap:
            raise EvidenceError('oversized_file')
        if stat_facts(before) != stat_facts(after) or len(data) != after.st_size:
            raise EvidenceError('changed_bytes')
        return data


def load_json(path, cap=MAX_DOCUMENT_BYTES):
    return json.loads(bounded_read(path, cap))


def within(path, root):
    return path == root or root in path.parents


def stat_facts(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def marker(path):
    resolved = path.resolve(strict=True)
    info = resolved.stat()
    if not stat.S_ISREG(info.st_mode):
        raise EvidenceError('stale_metadata')
    return {'path': str(resolved), 'stat': stat_facts(info)}


def checkout(path):
    return any((parent / '.git').exists() or (parent / '.hg').exists()
               for parent in (path, *path.parents))


def clean_relative(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise EvidenceError('unsafe_archive')
    parts = name.split('/')
    if any(part in ('', '.', '..') for part in parts) or PurePosixPath(name).is_absolute():
        raise EvidenceError('unsafe_archive')
    return name


def integrity_tokens(value):
    """SRI's strongest listed algorithm wins, not a weaker matching alternative."""
    if not isinstance(value, str):
        raise EvidenceError('unavailable_evidence')
    parsed = []
    ranks = {'sha1': 1, 'sha256': 2, 'sha384': 3, 'sha512': 4}
    for item in value.split():
        algorithm, sep, digest = item.partition('-')
        if not sep or algorithm not in ranks:
            continue
        try:
            raw = base64.b64decode(digest, validate=True)
        except (ValueError, binascii.Error):
            continue
        if len(raw) == hashlib.new(algorithm).digest_size:
            parsed.append((algorithm, raw))
    if not parsed:
        raise EvidenceError('unavailable_evidence')
    rank = max(ranks[algorithm] for algorithm, _ in parsed)
    return [(algorithm, raw) for algorithm, raw in parsed if ranks[algorithm] == rank]


def checksum_matches(data, integrity):
    return any(hashlib.new(algorithm, data).digest() == digest
               for algorithm, digest in integrity_tokens(integrity))


def public_url(url, source):
    if not isinstance(url, str):
        return False
    parsed = urllib.parse.urlsplit(url)
    origin = NPM_ORIGIN if source == 'npm' else GCLOUD_ORIGIN
    return (url.startswith(origin) and parsed.scheme == 'https' and
            not parsed.username and not parsed.password and not parsed.query and
            not parsed.fragment and '..' not in urllib.parse.unquote(parsed.path).split('/'))


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        source = 'npm' if public_url(req.full_url, 'npm') else 'gcloud'
        if not public_url(newurl, source):
            raise EvidenceError('nonpublic_source')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url, limit):
    """Only public GETs; no credentials, registry configuration or local uploads."""
    if not (public_url(url, 'npm') or public_url(url, 'gcloud')):
        raise EvidenceError('nonpublic_source')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers={'User-Agent': 'devcloud-provenance/1'}),
                         timeout=30) as response:
            data = response.read(limit + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise EvidenceError('unavailable_evidence') from exc
    if len(data) > limit:
        raise EvidenceError('evidence_limit')
    return data


class ExpandedReader:
    """Cap all decompressed bytes, including tar extension headers and padding."""

    def __init__(self, stream):
        self.stream = stream
        self.remaining = MAX_EXPANDED_BYTES

    def read(self, size):
        data = self.stream.read(min(size, self.remaining + 1))
        self.remaining -= len(data)
        if self.remaining < 0:
            raise EvidenceError('evidence_limit')
        return data


def archive_digests(data, source):
    """Inspect, never extract. Reject the whole artifact on ambiguous membership."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise EvidenceError('evidence_limit')
    result, seen = {}, set()
    expanded = 0
    try:
        # Stream decompression, including headers/padding, is bounded independently
        # of declared member sizes (which do not count extension headers).
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as decompressed, \
                tarfile.open(fileobj=ExpandedReader(decompressed), mode='r|') as archive:
            for count, member in enumerate(archive, 1):
                if count > MAX_ARCHIVE_ENTRIES:
                    raise EvidenceError('evidence_limit')
                name = clean_relative(member.name.rstrip('/') if member.isdir() else member.name)
                if name in seen:
                    raise EvidenceError('unsafe_archive')
                seen.add(name)
                if not (member.isdir() or member.isreg()) or member.issparse():
                    raise EvidenceError('unsafe_archive')
                if member.size < 0:
                    raise EvidenceError('unsafe_archive')
                expanded += member.size
                if expanded > MAX_EXPANDED_BYTES:
                    raise EvidenceError('evidence_limit')
                if source == 'npm':
                    if name == 'package' and member.isdir():
                        continue
                    if not name.startswith('package/'):
                        raise EvidenceError('unsafe_archive')
                    name = name[len('package/'):]
                if member.isdir():
                    continue
                if member.size > MAX_FILE_BYTES:
                    # Retain size-only metadata so coverage reports this loss.
                    result[name] = {'size': member.size, 'sha256': None}
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    raise EvidenceError('unsafe_archive')
                with stream:
                    content = stream.read(MAX_FILE_BYTES + 1)
                if len(content) != member.size:
                    raise EvidenceError('unsafe_archive')
                result[name] = {'size': len(content), 'sha256': sha256(content)}
    except (tarfile.TarError, EOFError, OSError, ValueError) as exc:
        raise EvidenceError('unsafe_archive') from exc
    return result


def npm_cache_entries(root):
    """Read cacache's index, not arbitrary installation files. Index mode only."""
    result = {}
    index = root / '_cacache/index-v5'
    if not index.is_dir():
        return result
    for directory, _, files in os.walk(index, followlinks=False):
        for filename in files:
            try:
                for line in bounded_read(Path(directory) / filename, MAX_DOCUMENT_BYTES).splitlines():
                    checksum, sep, payload = line.partition(b'\t')
                    if not sep or hashlib.sha1(payload).hexdigest().encode() != checksum:
                        continue
                    item = json.loads(payload)
                    key = item.get('key', '')
                    prefix = 'make-fetch-happen:request-cache:'
                    if not isinstance(key, str) or not key.startswith(prefix):
                        continue
                    url = key[len(prefix):]
                    if public_url(url, 'npm') and isinstance(item.get('integrity'), str):
                        previous = result.get(url)
                        if previous is None or item.get('time', 0) > previous.get('time', 0):
                            result[url] = item
            except (OSError, ValueError, TypeError, EvidenceError):
                continue
    return result


def cached_npm_bytes(root, entries, url, limit):
    item = entries.get(url)
    if item is None:
        raise EvidenceError('unavailable_evidence')
    for algorithm, digest in integrity_tokens(item['integrity']):
        hexed = digest.hex()
        path = root / '_cacache/content-v2' / algorithm / hexed[:2] / hexed[2:4] / hexed[4:]
        try:
            data = bounded_read(path, limit)
            if hashlib.new(algorithm, data).digest() == digest:
                return data
        except OSError:
            pass
    raise EvidenceError('unavailable_evidence')


class EvidenceStore:
    """Only indexing constructs this object; verification never touches it."""

    def __init__(self, fetch, npm_cache):
        self.fetch = fetch
        self.root = cache_dir()
        self.npm_cache = Path(npm_cache) if npm_cache else None
        self.npm_entries = npm_cache_entries(self.npm_cache) if self.npm_cache else {}

    def document(self, url, source, normalize, alternatives=()):
        path = self.root / 'documents' / (sha256(url.encode()) + '.json')
        try:
            cached = load_json(path)
            if cached['source'] == url:
                return normalize(cached['document'])
        except (OSError, ValueError, KeyError, TypeError, EvidenceError):
            pass
        if source == 'npm' and self.npm_cache:
            for candidate in (url, *alternatives):
                try:
                    document = normalize(json.loads(cached_npm_bytes(
                        self.npm_cache, self.npm_entries, candidate, MAX_DOCUMENT_BYTES)))
                    atomic_json(path, {'source': url, 'document': document})
                    return document
                except (OSError, ValueError, KeyError, TypeError, EvidenceError):
                    pass
        if not self.fetch:
            raise EvidenceError('unavailable_evidence')
        try:
            document = normalize(json.loads(fetch_public(url, MAX_DOCUMENT_BYTES)))
        except (ValueError, KeyError, TypeError) as exc:
            raise EvidenceError('unavailable_evidence') from exc
        atomic_json(path, {'source': url, 'document': document})
        return document

    def artifact(self, evidence):
        identity = sha256(encoded(evidence))
        path = self.root / 'evidence' / (identity + '.json')
        try:
            cached = load_json(path)
            if (cached['policyVersion'] == POLICY_VERSION and cached['evidence'] == evidence and
                    isinstance(cached['members'], dict)):
                validate_members(cached['members'])
                return identity, cached['members']
        except (OSError, ValueError, KeyError, TypeError, EvidenceError):
            pass
        data = None
        if evidence['source'] == 'npm' and self.npm_cache:
            try:
                data = cached_npm_bytes(self.npm_cache, self.npm_entries, evidence['artifactUrl'], MAX_ARCHIVE_BYTES)
                if not checksum_matches(data, evidence['integrity']):
                    data = None
            except (OSError, EvidenceError):
                pass
        if data is None:
            if not self.fetch:
                raise EvidenceError('unavailable_evidence')
            data = fetch_public(evidence['artifactUrl'], MAX_ARCHIVE_BYTES)
        if not checksum_matches(data, evidence['integrity']):
            raise EvidenceError('checksum_mismatch')
        members = archive_digests(data, evidence['source'])
        atomic_json(path, {'policyVersion': POLICY_VERSION, 'evidence': evidence, 'members': members})
        return identity, members


def validate_members(members):
    if len(members) > MAX_ARCHIVE_ENTRIES:
        raise EvidenceError('evidence_limit')
    for name, entry in members.items():
        clean_relative(name)
        if (not isinstance(entry, dict) or type(entry.get('size')) is not int or entry['size'] < 0 or
                (entry.get('sha256') is not None and not re.fullmatch('[0-9a-f]{64}', entry['sha256']))):
            raise EvidenceError('unavailable_evidence')


def discover():
    """No gcloud invocation: its launcher locates the SDK without running it."""
    result = {'npmRoot': None, 'npmCache': None, 'gcloudRoot': None}
    if shutil.which('npm'):
        for key, args in [('npmRoot', ['npm', 'root', '--global']),
                          ('npmCache', ['npm', 'config', 'get', 'cache'])]:
            try:
                run = subprocess.run(args, capture_output=True, text=True, timeout=15, check=True)
                path = run.stdout.strip()
                if os.path.isabs(path) and '\n' not in path:
                    result[key] = path
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
    binary = shutil.which('gcloud')
    if binary:
        root = Path(binary).resolve().parent.parent
        if (root / '.install').is_dir():
            result['gcloudRoot'] = str(root)
    return result


def npm_packages(root):
    """Only node_modules boundaries, not arbitrary example package.json files."""
    pending, seen = [root], set()
    while pending:
        modules = pending.pop()
        if not within(modules.resolve(), root) or modules.resolve() in seen:
            continue
        seen.add(modules.resolve())
        try:
            children = sorted(modules.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name.startswith('.'):
                continue
            if child.name.startswith('@'):
                try:
                    packages = sorted(child.iterdir())
                except OSError:
                    continue
            else:
                packages = [child]
            for package in packages:
                if not package.is_dir():
                    continue
                yield package
                # Never traverse linked packages, even ones linked within the root.
                if not package.is_symlink() and within(package.resolve(), root):
                    pending.append(package / 'node_modules')


def npm_evidence(store, name, version):
    if (not isinstance(name, str) or not re.fullmatch(r'(?:@[a-z0-9._~-]+/)?[a-z0-9._~-]+', name) or
            not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?', version)):
        raise EvidenceError('unavailable_evidence')
    package_url = NPM_ORIGIN + urllib.parse.quote(name, safe='@')
    url = package_url + '/' + urllib.parse.quote(version, safe='')

    def normalize(document):
        if 'versions' in document:
            document = document['versions'][version]
        if document['name'] != name or document['version'] != version:
            raise EvidenceError('unavailable_evidence')
        dist = document['dist']
        integrity_tokens(dist['integrity'])
        if not public_url(dist['tarball'], 'npm'):
            raise EvidenceError('nonpublic_source')
        return {'name': name, 'version': version,
                'dist': {'integrity': dist['integrity'], 'tarball': dist['tarball']}}

    doc = store.document(url, 'npm', normalize, (package_url, package_url.replace('%2F', '%2f')))
    return {'source': 'npm', 'documentUrl': url, 'version': version, 'package': name,
            'artifactUrl': doc['dist']['tarball'], 'integrity': doc['dist']['integrity']}


def gcloud_evidence(store, snapshot, component):
    release = snapshot['version']
    if not isinstance(release, str) or not re.fullmatch(r'\d+\.\d+\.\d+', release):
        raise EvidenceError('unavailable_evidence')
    url = GCLOUD_ORIGIN + 'components-v' + release + '.json'

    def normalize(document):
        if document['version'] != release:
            raise EvidenceError('unavailable_evidence')
        components = []
        for item in document['components']:
            data = item.get('data', {})
            if 'checksum' in data and 'source' in data:
                components.append({'id': item['id'], 'version': item['version'],
                                   'data': {key: data.get(key) for key in ('checksum', 'source', 'type', 'size')}})
        return {'version': release, 'components': components}

    doc = store.document(url, 'gcloud', normalize)
    candidates = [item for item in doc['components'] if item['id'] == component['id']]
    if len(candidates) != 1 or candidates[0]['version'] != component['version']:
        raise EvidenceError('unavailable_evidence')
    data = candidates[0]['data']
    checksum = data['checksum']
    if data['type'] != 'tar' or not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum):
        raise EvidenceError('unavailable_evidence')
    artifact_url = urllib.parse.urljoin(GCLOUD_ORIGIN, data['source'])
    if not public_url(artifact_url, 'gcloud'):
        raise EvidenceError('nonpublic_source')
    return {'source': 'gcloud', 'documentUrl': url, 'version': release, 'component': component['id'],
            'componentVersion': component['version'], 'artifactUrl': artifact_url,
            'integrity': 'sha256-' + base64.b64encode(bytes.fromhex(checksum)).decode()}


class Builder:
    def __init__(self, conn, store, project):
        self.conn, self.store, self.project = conn, store, project
        self.sources = {source: {'verifiedFiles': 0, 'verifiedPackages': 0, 'skipped': Counter()}
                        for source in ('npm', 'gcloud')}
        self.roots = set()

    def skip(self, source, reason):
        self.sources[source]['skipped'][reason] += 1

    def add_package(self, source, root, package, identity, evidence, markers, before, inventory=None):
        if before != [marker(path) for path in markers] or any(not within(Path(item['path']), package) for item in before):
            raise EvidenceError('stale_metadata')
        artifact_id, digests = self.store.artifact(evidence)
        record = {'source': source, 'installationRoot': str(root), 'packageRoot': str(package),
                  'identity': identity, 'artifactIdentity': artifact_id, 'evidence': evidence,
                  'markers': before}
        # Stage entries until markers have been checked again: an update during
        # the comparison must not publish observations from different installs.
        entries = []
        for relative in (inventory if inventory is not None else digests):
            clean_relative(relative)
            expected = digests.get(relative)
            if expected is None:
                self.skip(source, 'nonmember')
                continue
            if expected['size'] > MAX_FILE_BYTES or expected['sha256'] is None:
                self.skip(source, 'oversized_file')
                continue
            lexical = package / relative
            try:
                canonical = lexical.resolve(strict=True)
                # Archive member links are already forbidden. Do not let a local
                # replacement symlink borrow a different member's pathname.
                if canonical != lexical or not within(canonical, package):
                    raise EvidenceError('excluded_path')
                content = bounded_read(canonical, MAX_FILE_BYTES)
                if len(content) != expected['size'] or sha256(content) != expected['sha256']:
                    raise EvidenceError('changed_bytes')
                entries.append((str(canonical), relative, expected['sha256'], expected['size']))
            except OSError:
                self.skip(source, 'unavailable_file')
            except EvidenceError as exc:
                self.skip(source, exc.reason)
        if before != [marker(path) for path in markers]:
            raise EvidenceError('stale_metadata')
        if not entries:
            return
        package_id = self.conn.execute('INSERT INTO packages(record) VALUES (?)',
                                       (encoded(record).decode(),)).lastrowid
        for path, relative, digest, size in entries:
            # Overlapping component inventories/package members are ambiguous.
            # Remove authority rather than letting insertion order choose it.
            old = self.conn.execute('SELECT 1 FROM files WHERE path=?', (path,)).fetchone()
            if old:
                self.conn.execute('UPDATE files SET package_id=NULL WHERE path=?', (path,))
                self.skip(source, 'ambiguous_member')
            else:
                self.conn.execute('INSERT INTO files VALUES (?,?,?,?,?)',
                                  (path, package_id, relative, digest, size))
        self.sources[source]['verifiedPackages'] += 1
        self.roots.add(str(root))

    def npm(self, root):
        if root is None:
            self.skip('npm', 'installation_not_found')
            return
        root = Path(root).resolve()
        if within(root, self.project) or checkout(root):
            self.skip('npm', 'excluded_path')
            return
        for package in npm_packages(root):
            try:
                canonical = package.resolve(strict=True)
                if canonical != package or not within(canonical, root) or checkout(canonical):
                    raise EvidenceError('excluded_path')
                manifest = package / 'package.json'
                before = marker(manifest)
                doc = load_json(manifest)
                evidence = npm_evidence(self.store, doc['name'], doc['version'])
                if marker(manifest) != before:
                    raise EvidenceError('stale_metadata')
                self.add_package('npm', root, package, doc['name'] + '@' + doc['version'],
                                 evidence, [manifest], [before])
            except EvidenceError as exc:
                self.skip('npm', exc.reason)
            except (OSError, ValueError, KeyError, TypeError):
                self.skip('npm', 'unavailable_evidence')

    def gcloud(self, root):
        if root is None:
            self.skip('gcloud', 'installation_not_found')
            return
        root = Path(root).resolve()
        if within(root, self.project) or checkout(root):
            self.skip('gcloud', 'excluded_path')
            return
        for manifest in sorted((root / '.install').glob('*.manifest')):
            try:
                component_id = manifest.name[:-len('.manifest')]
                snapshot_path = manifest.with_name(component_id + '.snapshot.json')
                markers = [manifest, snapshot_path]
                before = [marker(path) for path in markers]
                snapshot = load_json(snapshot_path)
                components = [item for item in snapshot['components'] if item['id'] == component_id]
                if len(components) != 1:
                    raise EvidenceError('unavailable_evidence')
                inventory = bounded_read(manifest, MAX_DOCUMENT_BYTES).decode('utf-8').splitlines()
                if len(inventory) > MAX_ARCHIVE_ENTRIES or len(set(inventory)) != len(inventory):
                    raise EvidenceError('unsafe_archive')
                evidence = gcloud_evidence(self.store, snapshot, components[0])
                if before != [marker(path) for path in markers]:
                    raise EvidenceError('stale_metadata')
                self.add_package('gcloud', root, root, component_id, evidence, markers, before, inventory)
            except EvidenceError as exc:
                self.skip('gcloud', exc.reason)
            except (OSError, ValueError, KeyError, TypeError):
                self.skip('gcloud', 'unavailable_evidence')


def build_index(fetch=False, project_root=None):
    project = Path(project_root or Path.cwd()).resolve()
    found = discover()
    root = cache_dir()
    private_dir(root)
    store = EvidenceStore(fetch, found.get('npmCache'))
    fd, name = tempfile.mkstemp(prefix='.index-', suffix='.sqlite3', dir=root)
    os.close(fd)
    try:
        with closing(sqlite3.connect(name)) as conn:
            conn.executescript('''
                CREATE TABLE metadata (value TEXT NOT NULL);
                CREATE TABLE packages (id INTEGER PRIMARY KEY, record TEXT NOT NULL);
                CREATE TABLE files (path TEXT PRIMARY KEY, package_id INTEGER,
                    relative_path TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL);
            ''')
            builder = Builder(conn, store, project)
            builder.npm(found.get('npmRoot'))
            builder.gcloud(found.get('gcloudRoot'))
            for record, count in conn.execute(
                    'SELECT packages.record, count(files.path) FROM files JOIN packages '
                    'ON packages.id=files.package_id GROUP BY packages.id'):
                builder.sources[json.loads(record)['source']]['verifiedFiles'] += count
            summary = {'schemaVersion': SCHEMA_VERSION, 'policyVersion': POLICY_VERSION,
                       'generation': uuid.uuid4().hex, 'builtAt': int(time.time()),
                       'sources': builder.sources}
            conn.execute('INSERT INTO metadata VALUES (?)', (encoded(summary).decode(),))
            conn.commit()
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise EvidenceError('invalid_index')
        if Path(name).stat().st_size > MAX_DATABASE_BYTES:
            raise EvidenceError('index_limit')
        roots = sorted(builder.roots)
        if len(roots) > MAX_ROOTS:
            raise EvidenceError('index_limit')
        # The database is the authority. A stale/missing screen can only lose
        # coverage; neither replacement reconstructs hook-side receipts.
        with open(name, 'rb') as stream:
            os.fsync(stream.fileno())
        os.replace(name, root / 'index.sqlite3')
        atomic_json(root / 'roots.json', {key: summary[key] for key in
                    ('schemaVersion', 'policyVersion', 'generation')} | {'roots': roots})
        return summary
    finally:
        if os.path.exists(name):
            os.unlink(name)


def unknown(reason):
    return {'status': 'unknown', 'reason': reason}


def open_index():
    path = cache_dir() / 'index.sqlite3'
    try:
        info = path.stat()
    except FileNotFoundError as exc:
        raise EvidenceError('missing_index') from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DATABASE_BYTES:
        raise EvidenceError('invalid_index')
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.05)
    conn.execute('PRAGMA query_only=ON')
    conn.execute('PRAGMA trusted_schema=OFF')
    conn.set_progress_handler(lambda: 1, 100000)
    return conn


def metadata(conn):
    row = conn.execute('SELECT value FROM metadata LIMIT 2').fetchall()
    if len(row) != 1 or len(row[0][0]) > 65536:
        raise EvidenceError('invalid_index')
    value = json.loads(row[0][0])
    if (value.get('schemaVersion') != SCHEMA_VERSION or value.get('policyVersion') != POLICY_VERSION or
            not isinstance(value.get('generation'), str) or not re.fullmatch('[0-9a-f]{32}', value['generation'])):
        raise EvidenceError('invalid_index')
    return value


def status_report():
    try:
        with closing(open_index()) as conn:
            return dict(status='ready', **metadata(conn))
    except EvidenceError as exc:
        return unknown(exc.reason)
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        return unknown('invalid_index')


def validate_record(record, package):
    """Validate the stored contract without rediscovering metadata or artifacts."""
    source, evidence, markers = record['source'], record['evidence'], record['markers']
    if (source not in ('npm', 'gcloud') or evidence['source'] != source or
            record['artifactIdentity'] != sha256(encoded(evidence)) or
            not public_url(evidence['artifactUrl'], source) or
            not public_url(evidence['documentUrl'], source)):
        raise EvidenceError('invalid_index')
    integrity_tokens(evidence['integrity'])
    if source == 'npm':
        if record['identity'] != evidence['package'] + '@' + evidence['version']:
            raise EvidenceError('invalid_index')
        expected_url = NPM_ORIGIN + urllib.parse.quote(evidence['package'], safe='@') + '/' + urllib.parse.quote(evidence['version'], safe='')
        expected_paths = [package / 'package.json']
    else:
        component = evidence['component']
        if (record['identity'] != component or not re.fullmatch('[A-Za-z0-9._-]+', component) or
                component in ('.', '..')):
            raise EvidenceError('invalid_index')
        expected_url = GCLOUD_ORIGIN + 'components-v' + evidence['version'] + '.json'
        expected_paths = [package / '.install' / (component + suffix)
                          for suffix in ('.manifest', '.snapshot.json')]
    if evidence['documentUrl'] != expected_url or not isinstance(markers, list) or len(markers) != len(expected_paths):
        raise EvidenceError('invalid_index')
    for item, expected_path in zip(markers, expected_paths):
        if (item['path'] != str(expected_path) or not isinstance(item['stat'], list) or
                len(item['stat']) != 5 or any(type(fact) is not int for fact in item['stat'])):
            raise EvidenceError('invalid_index')
    return markers


def verify(request):
    """Bounded local lookup and one file read. No discovery or evidence building."""
    try:
        if not isinstance(request, dict) or len(encoded(request)) > MAX_REQUEST_BYTES:
            return unknown('invalid_request')
        for key in ('inputPath', 'filePath', 'projectRoot'):
            if not isinstance(request.get(key), str) or not os.path.isabs(request[key]) or '\x00' in request[key]:
                return unknown('invalid_request')
        for key in ('startLine', 'lineCount', 'contentBytes'):
            if type(request.get(key)) is not int:
                return unknown('unsupported_slice')
        start, count, length = (request[key] for key in ('startLine', 'lineCount', 'contentBytes'))
        if (start < 1 or count < 1 or start > MAX_FILE_BYTES + 1 or count > MAX_FILE_BYTES + 1 or
                length < 0 or length > MAX_FILE_BYTES or request.get('newline') not in ('preserve', 'lf')):
            return unknown('unsupported_slice')
        with closing(open_index()) as conn:
            meta = metadata(conn)
            path = Path(request['inputPath']).resolve(strict=True)
            returned = Path(request['filePath']).resolve(strict=True)
            project = Path(request['projectRoot']).resolve(strict=True)
            if (path != returned or within(path, project) or
                    within(Path(os.path.abspath(request['inputPath'])), project) or
                    within(Path(os.path.abspath(request['filePath'])), project)):
                return unknown('excluded_path')
            row = conn.execute('''SELECT files.relative_path, files.sha256, files.size, packages.record
                FROM files JOIN packages ON files.package_id=packages.id WHERE files.path=?
                AND length(packages.record) < 16384''', (str(path),)).fetchone()
            if row is None:
                return unknown('nonmember')
            relative, expected, size, raw_record = row
            record = json.loads(raw_record)
            root, package = Path(record['installationRoot']), Path(record['packageRoot'])
            if (not root.is_absolute() or not package.is_absolute() or root.resolve(strict=True) != root or
                    package.resolve(strict=True) != package or not within(package, root) or
                    not within(path, package) or within(root, project) or
                    path != package / clean_relative(relative)):
                return unknown('excluded_path')
            markers = validate_record(record, package)
            for item in markers:
                if not within(Path(item['path']), package) or marker(Path(item['path'])) != item:
                    return unknown('stale_metadata')
            if type(size) is not int or size < 0 or not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
                return unknown('invalid_index')
            if size > MAX_FILE_BYTES:
                return unknown('oversized_file')
            data = bounded_read(path, MAX_FILE_BYTES)
            if len(data) != size or sha256(data) != expected:
                return unknown('changed_bytes')
            # Check markers again after the read; fixed adapter-declared counts.
            if any(marker(Path(item['path'])) != item for item in markers):
                return unknown('stale_metadata')
            if re.search(rb'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', data):
                return unknown('unsupported_slice')
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                return unknown('unsupported_slice')
            if text.startswith('﻿'):
                return unknown('unsupported_slice')
            if request['newline'] == 'lf':
                text = text.replace('\r\n', '\n')
            lines = text.split('\n')
            if start - 1 + count > len(lines):
                return unknown('unsupported_slice')
            sliced = '\n'.join(lines[start - 1:start - 1 + count]).encode('utf-8')
            if len(sliced) != length:
                return unknown('unsupported_slice')
            return {'status': 'verified', 'schemaVersion': SCHEMA_VERSION, 'policyVersion': POLICY_VERSION,
                    'generation': meta['generation'], 'canonicalPath': str(path), 'fileSha256': expected,
                    'byteSize': size, 'sliceSha256': sha256(sliced),
                    **{key: request[key] for key in ('startLine', 'lineCount', 'contentBytes', 'newline')}}
    except EvidenceError as exc:
        return unknown(exc.reason)
    except (OSError, RuntimeError, sqlite3.Error, ValueError, TypeError, KeyError, AttributeError):
        return unknown('invalid_index')


class VerificationTimeout(Exception):
    pass


def verify_stdin(timeout_ms):
    def expired(_signum, _frame):
        raise VerificationTimeout()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, timeout_ms / 1000)
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            return unknown('invalid_request')
        return verify(json.loads(raw))
    except VerificationTimeout:
        return unknown('timeout')
    except (ValueError, OSError):
        return unknown('invalid_request')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    index = commands.add_parser('index', help='rebuild from public evidence; offline unless --fetch')
    index.add_argument('--fetch', action='store_true')
    status = commands.add_parser('status', help='inspect coverage without file contents')
    status.add_argument('--json', action='store_true')
    verifier = commands.add_parser('verify', help='bounded local verification, JSON stdin/stdout')
    verifier.add_argument('--timeout-ms', type=int, default=1500)
    args = parser.parse_args(argv)
    if args.command == 'verify':
        if not 1 <= args.timeout_ms <= 1500:
            answer = unknown('invalid_request')
        else:
            answer = verify_stdin(args.timeout_ms)
    elif args.command == 'status':
        answer = status_report()
    else:
        try:
            answer = build_index(fetch=args.fetch)
        except (OSError, ValueError, sqlite3.Error, EvidenceError):
            print(json.dumps(unknown('build_failed')))
            return 1
    print(json.dumps(answer, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())

# Preserve installed-package constants without exposing local state

When Claude reads an installed library, the secrets guard should preserve the library’s original constants instead of turning them into redaction handles. The exemption must not extend to credentials or runtime state subsequently written into that installation. This change establishes that distinction by comparing a file with its package’s original contents, then binds the exception to that particular Read and its recorded result.

The person enables coverage by running `devcloud guard index --fetch` outside a Claude function hook. Subsequent supported Reads of indexed, unchanged files preserve generic-only constants in both the tool result and its transcript row. Stored values, credential-file values, provider-shaped tokens and private-key blocks remain redacted. Missing evidence means ordinary detection, not refusal.

This is board ticket #124, following #87 and PR #349. It changes neither the detector’s credential heuristics nor the guard’s existing reach. It does not protect against a person deliberately rewriting the guard, its index, or their installed software. It protects against accidental disclosure of the person’s state through an exemption intended for distribution contents.

## Progress

- [x] (2026-10-22 11:32Z) Read #124, the preceding design decisions and measurements, guard implementation, engine API references, native Read mapper, and cua’s vendoring contract.
- [x] (2026-10-22 11:32Z) Reproduced the npm and gcloud corpus counts; measured ownership, modes, metadata, timestamp candidates, local npm cache availability, and original-artifact equality.
- [x] (2026-10-22 11:32Z) Chose out-of-band indexing, bounded local verification, and call-bound, one-use append receipts.
- [ ] Commit this specification and complete one adversarial review of its design and execution section.
- [ ] M1 — Build and inspect the original-content index outside hooks.
- [ ] M2 — Apply bounded verification through both scrubbing passes.
- [ ] M3 — Prove native behavior, measure improvement, review and release; register the cua resync against the merged commit.

## Acceptance

1. **An unchanged distribution file stays intelligible.** After indexing, a native text Read of an eligible installed-package file containing a synthetic generic-only assignment preserves that assignment in the immediate result, the transcript’s structured `toolUseResult`, and its matching `tool_result` content. The same holds for a supported offset/limit Read and a supported automatically paginated Read.

2. **The stronger protections still win.** In the same verified file, synthetic stored values, credential-file values, provider-shaped tokens and PEM private-key blocks become handles in both passes. Tests establish this with distribution fixtures containing those values from the outset, not by modifying a file after indexing and accidentally testing only the fallback.

3. **Local state is not distribution content.** A file added after installation, a modified distributed file, generated state, local build output, a package-cache file, a project’s `node_modules`, an ordinary project file, and a global-package symlink resolving into a checkout all receive full detection. Rebuilding the index does not adopt modified installed contents as a new baseline.

4. **An exception belongs to one result.** The same generic-looking string is redacted in Bash output, a different Read, unrelated text in the same row, an appended note, or a later assistant message. A wrong call id, wrong agent, wrong origin, duplicate result, altered rendering, expired receipt or absent receipt receives full detection.

5. **Reload and persistence do not retain authority.** Reloading between Read and append loses the receipt, so append uses full detection. Restart, resume, compaction and index replacement do not reconstruct call receipts from transcript text or persistent state. Already stored rows remain as stored; this feature does not rewrite historical transcripts.

6. **Verification failure does not refuse a successful Read.** With a missing, unreadable, malformed, incompatible or stale index, a changed ownership marker, a file over the cap, an unsupported format, a missing interpreter, or a verifier timeout, the call runs and its output receives full detection. An error in the existing scrubber retains the guard’s existing failure behavior; provenance failure must not enter that error path.

7. **Hot-path work is bounded and local.** Tests prohibit network access, archive processing, package-manager invocation and cache traversal from the verifier. The verifier reads at most one eligible file of at most 16 MiB, performs indexed lookup and a bounded number of metadata checks, and has a 1.5-second process deadline. Saturation of its concurrency limit uses full detection rather than a queue. Timeout/abort tests show no surviving verification process or repeated hook overrun.

8. **Linux ownership is checked rather than inferred.** For a dpkg fixture, a listed regular file with matching installed-package MD5 evidence can be indexed; a conffile, diversion, missing digest, unlisted file, changed file or ambiguous owner cannot. A Linux acceptance run exercises actual dpkg metadata as well as the fixtures. The authoring measurements did not include a live Linux dpkg database.

9. **Utility and protection are reported separately.** On the unchanged authoring corpus, original-artifact comparison covers 1,094 npm and 424 gcloud generic matches. The implementation reports index coverage and actual preservation through both passes separately, including losses to format, size or other fallback conditions. Its target is at least 95% preservation of those eligible generic matches through both passes, with every credential regression passing. If it misses that target, report the cause before widening the trust rule. These are detector matches, not a claim that every match is a harmless constant.

10. **The shipped copies remain coordinated.** The devcloud release is version-bumped and passes `devcloud-mods` and `mods-types`, including the new Python helper tests. After merge, a cua resync ticket names the actual merged commit, all new vendored files and the existing one-guard adaptations.

## Context and evidence

`devcloud/hooks/mods/secrets.tsx` owns the hook pipeline. `secrets-detect.tsx` identifies token spans; `secrets-handles.tsx` gives known values priority, creates handles, and restores them. `secrets-sources.tsx` supplies stored and credential-file values. `devcloud/tests/mods/` holds the guard tests; `devcloud/tests/mods/run.sh` is the `devcloud-mods` gate entry point.

Today the tool hook scrubs the structured result after `next(input)`. The append hook separately scrubs each text block and `tool_result.content`. It does **not** correlate those passes by call id. `tool_use_id` being reserved in the tool-input code prevents restoration from rewriting it; that is not existing provenance tracking.

The engine’s plugin-authoring reference, “The rows a conversation keeps: session.append,” and the generated declarations for engine 2.1.308 establish:

- `tool.call` carries the call’s reserved `tool_use_id` and its loop’s `agentId`.
- `session.append` carries pinned `agentId`, `door`, `origin` and `uuid`; each tool-result id is pinned as well.
- A native tool result supplies `result` and model-facing `text`. Returning a replacement structured result causes the tool’s mapper to render it again.
- The appended row does not expose `toolUseResult`; that structured record is stored as made. It must therefore be protected in the tool hook, not repaired by append.
- Appends are not transcript loads. Resume does not run old rows through this hook.
- `$.fs.stat(path, { resolve: true })` resolves symlinks but explicitly does not hold the file the tool subsequently opens. Its public result does not supply owner, mode, ctime or file identity.

The native Read mapper in the inspected 2.1.308 bundle renders text from `file.content` and `startLine`, adds line numbers, strips a trailing carriage return from each displayed line, and can use a colon rather than a tab separator for tab-leading source. Pagination banners and other messages sit outside that numbered body. The implementation must bind to supported renderings, not assume that the displayed text is the raw file.

### Measurements on the author’s Mac

The corpus traversal did not follow symlinks and used the preceding report’s source/text extensions. It reproduced that report exactly.

| Corpus | Files examined | All detector matches | Generic-rule matches |
|---|---:|---:|---:|
| Global npm packages | 58,463 | 1,124 | 1,094 |
| gcloud SDK library | 23,324 | 284 | 269 |
| gcloud SDK platform | 2,885 | 197 | 155 |

All examined text files were owner-writable. The global npm root, SDK root, native-install directory and sampled metadata belonged to the current user; sampled directories were mode 0755 and sampled metadata/source files 0644. These facts neither establish unchanged contents nor disqualify a file whose contents are independently compared with its distribution.

The global npm prefix contained one package symlink whose resolved target was outside the global root, in a development checkout. Top-level package manifests had no installed-content integrity field, and the global root had no lockfile. Some manifests supplied `files` patterns; these are publication selection rules, not inventories or checksums of the present installation.

For the 1,094 npm generic matches, requiring both file mtime and ctime to precede the nearest package manifest’s ctime retained 528 matches. Comparing both with the package directory’s mtime retained 582. Neither timestamp is an immutable completion marker: directory modification times also move when later files are added, while extraction can create legitimate files after their package manifest.

Every gcloud generic-hit file appeared in a component manifest. Those manifests are lists of installed paths. Their snapshots contain component-level `contents_checksum` values, not per-file installed hashes; the local snapshots omit the downloadable archive’s original checksum and source. None of the generic-hit files passed the corresponding manifest-time check: installation had created metadata before those files. The SDK also contained 33,585 `.pyc` files under its library and platform trees, none listed in component manifests. This is direct evidence that an installation tree acquires runtime files.

A sampled global CLI also contains code that downloads a missing executable into its own package tree and writes an installed-version marker there. Another sampled CLI puts its update cache in its application cache directory by default. The investigation found actual generated files and in-tree write behavior, not evidence that every installed CLI stores credentials in its package directory. No claim is made that the installation trees were exhaustively audited for credential-writing behavior.

Exact artifact comparison produced a substantially stronger result:

| Original-content comparison | Files containing generic matches | Distinct artifacts | Generic matches in byte-identical files | Compressed bytes fetched for the measurement |
|---|---:|---:|---:|---:|
| npm package versions | 367 | 48 | 1,094 / 1,094 | 69,031,269 |
| gcloud components | 159 | 4 | 424 / 424 | 59,984,007 |

The npm comparisons used the exact published package versions and verified the downloaded artifacts against registry integrity metadata. The gcloud comparisons used the installed SDK release’s component manifest and archive checksums. Archive members were read as data without extracting or executing their contents. Every compared installed file matched its corresponding archive member byte-for-byte; none was missing or different.

The local npm cache already had tarball keys for 46 of those 48 package versions, covering 1,091 of the 1,094 matches. That measures cache-key availability, not a second verification of every cached blob. The indexer must verify cached artifact bytes before using them.

A 4 MiB eligible-file cap would cover 1,514 of the 1,518 generic matches; 8 MiB covers 1,516; 16 MiB covers all 1,518. The largest generic-hit text file was about 8.72 MiB. This supports a bounded 16 MiB cap, not unlimited file hashing.

### Native Claude Code and dpkg

The native executable passed strict platform code-signature verification. That is useful evidence of distribution origin, but the executable was binary and approximately 262 MiB. The preceding report’s 301 matches came from extracted printable strings, not a demonstrated ordinary text Read. A limited Read of the executable returned binary-decoded text, not a source-file representation. This design excludes native binaries and removes those 301 matches from its Read utility denominator. It does not claim to fix `strings` output through Bash.

Neither dpkg nor its installed metadata database was present on the author’s Mac. The Linux adapter is consequently grounded in the documented metadata contract and must be verified on Linux during execution. A dpkg file list establishes claimed membership; an available per-file MD5 establishes equality to the package’s recorded contents. `dpkg --verify` alone is insufficient: it skips files lacking hashes and does not provide complete ownership/mode verification. Debian explicitly describes it as an integrity check, not security verification. That limitation is compatible with this feature’s accidental-state threat model, but does not justify treating unverified or configurable files as original contents.

Relevant references:

- `docs/doperpowers/plans/2026-10-22-devcloud-guard-shapes-report.md`
- Decision Log of `docs/doperpowers/specs/2026-10-15-devcloud-design.md`
- [npm package-lock documentation](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json): integrity identifies the unpacked artifact; hidden-lockfile timestamp checks can miss direct file edits.
- [dpkg manual](https://manpages.debian.org/unstable/dpkg/dpkg.1.en.html): verification coverage and limitations.
- [The measured SDK release’s component metadata](https://dl.google.com/dl/cloudsdk/channels/rapid/components-v580.0.0.json).

## Design

### 1. Verify original bytes, not the appearance of a package path

A file is eligible only when all of these are true:

1. Its resolved path belongs to a supported installation discovered by the indexer and is not excluded project, cache or generated state.
2. Its exact package-relative path is a regular file in the package’s distribution evidence.
3. The indexer compared the installed file with that evidence before issuing its index entry.
4. The current ownership markers still match that entry.
5. A bounded local read now hashes to the indexed SHA-256.
6. The native Read’s source content agrees with the verified file slice, and its rendering is supported.

The hash comparison is necessary even for a root-owned file. It is sufficient despite ordinary owner writability when the other conditions hold: the current bytes are distribution bytes, not later local state. Modes and ownership are diagnostic information, not an allowlist.

The strongest simpler alternative was membership plus installation timestamps. It lost both on evidence and on semantics: it discards much of the measured benefit, gcloud’s ordering defeats it outright, and a mutable directory timestamp cannot prove that an existing file was unchanged. Authenticated per-file vendor receipts were also considered; they impose a tamper-resistance requirement outside the guard’s contract and are unnecessary for distinguishing original distribution contents from accidental local modifications.

### 2. Build the index explicitly, outside hooks

Add these user-level commands:

- `devcloud guard index` rebuilds from locally available distribution evidence without network access.
- `devcloud guard index --fetch` may fetch missing public artifacts before rebuilding.
- `devcloud guard status --json` reports index schema/generation, build time, source coverage and skipped-reason counts, without file contents or credential data.

These commands run on Macs and Linux hosts without the host-management CLI’s root requirement or host-only PATH rewriting. The initial trigger is the person or an authorized session invoking the command. Run it after installing/updating relevant packages, or when status reports stale entries. Do not add a daemon, timer, session-start rebuild, implicit installation hook or Read-triggered refresh in this initiative.

Index construction uses a standalone Python standard-library helper at `devcloud/hooks/mods/secrets-provenance.py`; its `index` and `verify` modes share the on-disk contract. Integrate the public command in `devcloud/boot/devcloud` before its host-only dispatch. The existing `devcloud/bin/devcloud` remains the command entry point. The helper must remain usable independently of that CLI so cua can vendor it.

Store the index in the user cache area, under the feature’s own versioned namespace. Respect an explicit XDG cache directory on both supported platforms, so isolated acceptance tests can use their own cache. Otherwise use the platform’s ordinary user cache directory. Store only metadata and digests, never source bytes, credential values or call receipts. Use a private directory and file permissions as hygiene; they are not the proof of package origin.

Use a read-only-queryable SQLite index, available in Python’s standard library, rather than loading an installation-wide JSON map during a Read. Build a new database beside the old one, validate it, and publish it by atomic replacement. A failed build does not publish a half-built index. A completed build may omit unavailable packages, but its summary must distinguish verified coverage from each skipped reason. Never silently populate an omitted package from its current installed contents.

Cache reusable original-artifact digests by artifact identity. A rebuild may reuse verified distribution evidence; it still compares the current installed file before issuing an entry. Downloads, npm-cache traversal, archive decompression and package discovery occur only in `index` mode. Artifacts are data: do not execute lifecycle scripts or installed package code. Inspect regular archive members without extracting them; reject ambiguous member paths, duplicate members, links and paths escaping the archive root. Bound archive size, expanded bytes and entry count, reporting exceeded limits as skipped evidence.

The strongest alternative was a lazy downloader in the Read hook. It would make first use convenient, but conflicts with the engine’s hook budget and makes network availability part of the secrets boundary. A daemon would avoid the hook but introduce another lifecycle solely to hide an explicit, infrequent operation. The command is the smallest complete trigger.

### 3. Installation adapters

**Global npm.** Discover the actual global prefix through npm in index mode, resolve it, and enumerate installed package boundaries, including nested dependencies. Package boundaries follow `node_modules` placement and scoped-package layout, not the nearest arbitrary `package.json`: examples can contain their own manifests without being separately installed packages. Reject linked packages whose resolved roots leave the discovered global installation. Reject roots inside the invoking project or a detected source checkout. At runtime, the guard also excludes its session’s project root.

Use package name/version and available lock metadata to locate original artifacts in the npm cache. Validate the cache’s artifact integrity before computing member hashes. `--fetch` can obtain missing exact-version artifacts from the public npm registry. Do not consult private registry credentials or execute npm package scripts; unsupported/private sources remain unknown. A `files` field, lockfile integrity value or cache key is discovery evidence, not proof of the installed file’s current contents.

**gcloud SDK.** Discover the SDK installation, resolve it, and use component manifests to associate files with installed component snapshots. Obtain the matching release’s original component archives from a local artifact cache or, with `--fetch`, Google’s distribution service. Validate archive checksums from that release’s component metadata, then compare the relevant regular members. Do not interpret a component’s aggregate `contents_checksum` as a per-file digest. Files absent from the component inventory, including generated Python bytecode, receive no entry.

**dpkg.** Read installed-package status, file lists, per-file MD5 evidence, conffile metadata and diversions. Only an unambiguously owned regular file with an available matching MD5 is eligible. Exclude conffiles, diversions, missing hashes and generated/unlisted files. After matching the original MD5 evidence, record the installed file’s SHA-256 for runtime use. Metadata and configuration classification must come from the database, not an assumption that everything under a system prefix is immutable.

**Native Claude Code.** Do not index the native executable or invent a native source-tree exemption. Its signature does not make binary decoding a supported source Read, and its measured strings corpus belongs to an explicitly excluded Bash transformation. A Claude package installed through a supported global npm installation can use the npm adapter like any other package.

Package-shipped `dist` sources are distribution contents. They are distinct from project build products or files generated locally after installation; those remain fully guarded. Package caches are evidence inputs for the indexer, never eligible Read roots themselves.

The strongest alternative was one path-root adapter for all package managers. It lost because their inventories mean different things and generated state is present inside real installations. These adapters share the same output contract, not a fabricated common ownership signal.

### 4. A bounded local verifier

Most Reads never reach the verifier. The mod spawns it only for a Read that passes two checks. First, the full detector finds at least one generic `assignment` span in `file.content`. Second, the resolved path lies under an installation root the index publishes. The mod takes those roots from a small roots file written beside the index at publication, read once per module and read again only when its stat changes. Every other Read keeps today's path, with no subprocess.

The hot path invokes only `verify` mode, through `$.process.run` with an argument vector, no shell, and an isolated Python invocation. Python 3.9 or later suffices for the standalone helper; the public devcloud CLI retains its existing interpreter requirement. Missing runtime support means full detection.

The verifier performs an indexed lookup for the resolved input path and checks:

- index schema/policy version and a bounded database file size;
- the session project exclusion and the indexed canonical installation/package roots;
- agreement of the input path and returned `filePath` after resolution;
- the owner’s recorded metadata fingerprints;
- regular-file identity and size before and after reading;
- SHA-256 of at most 16 MiB of current file bytes;
- the native result’s declared source slice against those same verified bytes.

Metadata fingerprints are fixed, bounded sets of stat facts: canonical path, device/inode where supplied by the platform, size, mtime and ctime. npm uses its owning package manifest; gcloud uses the component manifest and snapshot; dpkg uses the relevant ownership/checksum/configuration metadata. An index entry with a changed marker is stale even if a quick path check would still find the package. Index schema/policy mismatch is stale as well. Content hashes do not expire merely because time passed; current marker checks and per-Read hashing prevent stale installation observations from becoming exemptions.

The verifier returns digests and small metadata only, never file bytes. Its response binds the file digest, canonical path, index generation and exact source slice. The mod compares the returned slice digest with the native structured result’s `file.content`. Slice verification is positional, from the declared starting line and returned length; it must not search the file for a matching string. It accommodates only explicitly tested newline and truncation behavior. Unsupported encodings, binary content, altered long-line renderings and ambiguous slices fall back to full detection.

This closes the gap between checking a path and using the tool’s earlier result. If the file changes between the tool read and verification, the current file must still match the distribution and the returned slice must still match those verified bytes. A changed or unrelated result cannot borrow a current file’s verification.

Set a 1.5-second subprocess deadline and honor the hook’s abort signal. Allow at most four concurrent verifier processes per loaded module; additional candidates take the fully guarded path immediately. Do not queue them. A local verifier timeout, malformed answer or missing index is an ordinary negative result, handled before the existing outer tool-hook error handler.

The strongest alternative was caching successful verification by path, size and mtime. It would reduce hashing but turn mutable filesystem observations into continuing authority. The measured file sizes permit rehashing the specific file under a hard cap instead. Raising that cap or adding a positive file-verification cache requires new measurements, not a silent optimization.

### 5. Disable only generic detections, only in verified content

Extend the detector/handles path with an internal option for ranges in which `assignment` detections may be omitted. The default remains the complete existing detector. The option does not suppress known-value matching, provider rules, PEM rules, handle protection or restoration.

In a supported verified Read, apply that option only to `result.file.content`. Every other string in the structured result receives full detection. Do not set a package-wide mode on `scrubRecord`, exempt the whole tool result, or put a flag in model-visible text. If stronger protections rewrite the result, return a new structured result without reusing core’s `ref`, so the native mapper renders the scrubbed contents. Preserve the existing context-note and persisted-output behavior.

Oversized persisted-output files remain on the existing full-detection path. This initiative does not grant them a file-wide exception. Media, notebooks, unchanged-file notices, error results and unsupported Read forms also retain full detection.

The strongest alternative was a boolean “trusted package” flag around the complete result. It lost because metadata, notices and tool context are not the verified source file. A narrow range policy also lets the append pass protect its surrounding text without duplicating detector logic.

### 6. Bind the exception through append with a one-use receipt

Add `devcloud/hooks/mods/secrets-provenance.tsx` for the hook-side verifier adapter, supported Read rendering adapter and receipt lifecycle. A **receipt** is module-private evidence that one completed Read has already passed file verification. It is not a string allowlist and is never serialized into the transcript, `$.state`, `$.store`, the disk index or an engine metadata field.

Key it by the tuple `(agentId or main, tool_use_id)`, encoded without concatenation ambiguity. An eligible append must have all of:

- `door === 'tool-result'`;
- `origin.kind === 'tool'` and `origin.tool === 'Read'`;
- the matching loop and pinned tool-result id;
- a non-error, supported text representation;
- exactly the expected rendered text for this completed call.

The receipt carries the index generation, a digest of the expected final rendering, the verified body’s character range or ranges, and its monotonic expiry time. It contains no source text or secret values. There are at most 256 outstanding receipts. Each expires 60 seconds after issue; insertion evicts the oldest outstanding receipt when necessary. Expiry and eviction cost only preservation: append then uses full detection.

The rendering adapter first identifies the exact numbered source body in native `ran.text`, using the native structured content and starting line. It rejects unsupported or ambiguous formatting. From the scrubbed structured content it computes the corresponding expected body rendering, preserving the observed prefix and suffix as surrounding text. The final text digest binds the complete representation, not just a matching substring. Support only a string tool-result body or its equivalent singleton text block until another representation is separately proved.

The adapter must reproduce the inspected mapper’s line numbering, carriage-return handling and tab-aware separator behavior. Pagination wrappers are not exempt. If the core mapper or another plugin changes the final representation unexpectedly, its digest will not match and append performs full detection. The decision to verify came from file bytes and the index; result-text comparison only establishes that the row is still the exact result to which that decision applied.

At append, take and delete the matching receipt synchronously before the first await. Verify its expiry, pinned envelope and full rendered-text digest. Only then suppress generic spans wholly inside its verified source-body ranges. Apply known-value and provider/PEM detection across the entire current text again, including the verified ranges; values discovered after the first scrub must still be caught. All other blocks and surrounding text receive full detection. Duplicate ids within a row receive no exemption.

#### Receipt state transitions

| Event | State change | Detection behavior |
|---|---|---|
| Read begins | Remove any outstanding entry for that loop/call key; never inherit earlier authority | No exception yet |
| Read completes, verification and rendering binding succeed | Issue one bounded, expiring receipt immediately before returning | Generic exception only in verified structured source content |
| Read denies, errors, is unsupported, or verification fails | No receipt | Full detection |
| Matching result reaches append | Consume receipt before asynchronous work | Exception only if envelope and complete rendering match |
| Append lacks a receipt, mismatches, duplicates an id, or arrives late | No authority; any consumed entry stays consumed | Full detection |
| Capacity eviction, session restart/start reset, module reload or worker replacement | Drop affected receipts; no reconstruction | Full detection for later unmatched appends |

The tool-result hook and append hook remain unmatched registrations, as required by the sminos bridge’s chain-position checks. No new guard marker is introduced.

The strongest alternative was remembering that a particular string or call id had once been seen in a package. String memory leaks authority into unrelated output; an id-only map fails to detect a changed result. Persistent receipts would survive the lifecycle of the module that verified them. A bounded, one-use receipt with full output binding addresses all three without depending on unsupported custom engine metadata.

### 7. Failure, compatibility and existing boundaries

“Unknown” means ordinary detection, not a weaker detector and not a denied Read. Keep provenance errors separate from scrubber errors so an unavailable index cannot withhold otherwise readable output.

The native rendering contract was inspected on engine 2.1.308. An older or newer engine with unsupported result fields or formatting receives the original full protection. Do not make an engine-version string alone authorize a rendering. Compatibility is demonstrated by the result shape and exact binding, then checked by native acceptance.

The existing exclusions in `devcloud/README.md` remain exclusions. This feature does not repair attachment payloads, prompt text added after composition, transformed secrets, images, or the pre-scrub persisted-output crash window. Nor does it carry package exemptions into compaction, context attachments or later generated prose: those surfaces continue to run full detection.

The strongest alternative was extending provenance to every subsequent copy of the text. It would turn an explanation of where one Read came from into a long-lived content exemption, exactly the behavior this feature must avoid.

## Plan of Work

All milestones retain “redact, never refuse,” the detector regressions from #349, the unmatched-hook requirement, resolved-path containment, and the bounded verifier contract. No source values or machine-identifying measurements enter committed documentation. Use synthetic test data. Commit meaningful increments; full gate verification runs on committed HEAD through GitHub Actions, not by running gate scripts locally.

### M1 — Build and inspect the original-content index outside hooks

At this milestone’s end, `devcloud guard index`, `index --fetch` and `status --json` work on the caller’s machine, and the index distinguishes original files from changed or newly generated files without changing runtime redaction.

Add the standalone index/verifier helper at `devcloud/hooks/mods/secrets-provenance.py`, its private cache layout and SQLite schema, and user-level dispatch in `devcloud/boot/devcloud`. Implement the npm, gcloud and dpkg evidence adapters, archive handling, atomic publication, coverage reporting and local-only verification protocol. Add Python tests under `devcloud/tests/mods/` and include them in `devcloud/tests/mods/run.sh` so they belong to `devcloud-mods`.

This milestone produces `IndexEntry`, `VerifyRequest` and `VerifyResult` as defined below. Its tests prove acceptance 3, 6, 7 and the metadata portion of 8: post-install additions and modifications, linked checkouts, duplicate/archive traversal entries, unavailable artifacts, malformed index data, stale markers, rebuild rejection of modified files, size bounds and timeout cleanup. It also verifies that `verify` mode cannot reach network, archive or discovery code.

Do not add automatic refresh, a daemon, new privileged installation work, or a runtime exemption. Review the evidence-producing interface before M2 consumes it.

### M2 — Apply bounded verification through both scrubbing passes

At this milestone’s end, synthetic verified native-text Read results preserve generic constants in the structured result and matching appended row, while the unchanged detector protects every negative case.

Add `devcloud/hooks/mods/secrets-provenance.tsx`; change the detector/handles interface narrowly in `secrets-detect.tsx` and `secrets-handles.tsx`; integrate verification and receipts into `registerSecrets` in `secrets.tsx`. Keep both hooks registered without matchers. The implementation consumes M1’s verifier protocol and produces the one-use receipt and rendering adapter defined below.

Tests in `devcloud/tests/mods/` must exercise both passes together, not just call the detector with a flag. Prove acceptance 1–7 with main/subagent concurrency, out-of-order completions, unknown and duplicate ids, exact envelope mismatches, rendering changes, new known values between passes, capacity eviction, expiry, reload loss, partial Reads, CRLF/tab-leading content, strong multi-line redaction and supported pagination. Unsupported transforms must be demonstrably fully guarded, not silently accepted.

The engine test kit does not itself substitute for native Read’s mapper. Use its mocks for controlled interleavings and error paths; retain explicit native-format fixtures and complete the actual-engine proof in M3. Do not extend receipt authority to Bash, arbitrary plugin output, attachments, compaction or persisted-output files.

### M3 — Prove native behavior, measure improvement and prepare the coordinated release

At this milestone’s end, a synthetic real-engine acceptance run and the committed gates prove the complete feature; the public documentation gives the person the indexing command and explains its fallback behavior.

Add a reproducible acceptance driver at `devcloud/tests/mods/provenance_probe.py`. It creates an isolated cache and synthetic distribution/install fixtures, prepares an index using the same helper contract, and launches a native headless session with the development plugin. It verifies the resulting transcript’s structured record and tool-result text, including a supported partial Read and a stronger-secret case. It uses no personal package contents, real credentials or default transcript location. If the installed engine cannot supply the expected lifecycle or rendering, the probe fails with that boundary named; it must not replace the engine with a hand-written mapper and call the result native acceptance.

Add a corpus-report mode to the helper, invoked only out of band, for the same source/text extension set as the preceding report. It reports existing detector matches, verified original-content coverage, and preservation through the supported two-pass pipeline as distinct numbers. It may use the TypeScript detector through the repository’s existing test/runtime tooling rather than reimplementing the detection rules in Python. Record actual implementation results in this specification’s record, without local paths or matched values. Execute acceptance 1–10, including an actual Linux dpkg check; do not describe unrun platform evidence as passed.

Update `devcloud/README.md` and `devcloud/hooks/mods/CLAUDE.md`. Use `scripts/bump-version.sh --plugin devcloud` for the runtime release. Run the committed `devcloud-mods` and `mods-types` gates, then doperpowers:review-code at the high rung on the entire branch. Resolve verified material findings through a bounded fix wave rather than broadening the design.

After merge, the integrating session creates the cua resync ticket described below, naming the actual merged commit. That post-merge action is part of closing #124, not an inferred promise from a version bump. This milestone does not itself modify cua or add automatic indexing.

## Concrete Steps

Commands below run from the doperpowers repository root unless stated otherwise.

1. Build or rebuild coverage deliberately:

   ```sh
   devcloud/bin/devcloud guard index --fetch
   devcloud/bin/devcloud guard status --json
   ```

   Expect a published generation and counts of verified files and skipped evidence. No secret values or file contents are printed. On a disconnected machine, run `devcloud/bin/devcloud guard index`; it uses local evidence and reports unavailable artifacts rather than fetching them.

2. During M1 iteration, run the focused Python tests:

   ```sh
   python3 -I -m unittest discover -s devcloud/tests/mods -p 'provenance_index_test.py'
   ```

   Expect the synthetic inventory, modification, archive and bound cases to pass. This focused check does not replace the committed gate.

3. After each relevant milestone is committed, run:

   ```sh
   ci-gate --gates devcloud-mods,mods-types
   ```

   Expect both gates to report `PASS`, followed by `GREEN`. `ci-gate` tests committed HEAD. Do not claim this verifies uncommitted changes or run the full gate commands on the Mac as an alternative.

4. For the real-engine acceptance proof after M2:

   ```sh
   python3 -I devcloud/tests/mods/provenance_probe.py
   ```

   Expect explicit PASS results for native Read, partial Read, structured persistence, appended text, strong-secret protection and unknown-provenance fallback. A missing native engine or inability to launch the isolated session is a reported blocker, not a pass. The driver owns cleanup of its synthetic fixtures and session artifacts.

5. Report corpus coverage, separately from credential tests:

   ```sh
   devcloud/bin/devcloud guard index --fetch --report-corpus
   ```

   On the unchanged authoring corpus, the original-content comparison should account for 1,094 npm and 424 gcloud generic matches. Changes in package versions or corpus contents require a newly stated denominator. The report must distinguish original-content equality from actual preservation through the supported rendering and both scrubs.

6. On a Linux test host, run the indexing command and the helper’s dpkg acceptance cases through the same gate/test entry point. Include a real installed non-conffile with a digest and a real conffile in the evidence. Keep any modification test inside synthetic fixtures, not an operational system package.

7. Before release, invoke doperpowers:review-code at the high rung on the whole committed branch, with this specification as the contract. After merge, verify the merged commit and register the cua resync against it.

## Interfaces and Dependencies

### Local index

The SQLite schema has a versioned metadata row, installation/package records, and file entries indexed by canonical path. Its logical contracts are:

- `IndexEntry`: schema/policy version; generation; source adapter; canonical installation root and package root; package/version or component identity; package-relative regular-file path; original-artifact identity; expected SHA-256 and byte size; bounded owner-marker fingerprints.
- `OwnerMarker`: canonical metadata path and its platform stat fingerprint. Each adapter declares a fixed set; there is no runtime metadata-tree search.
- Build statistics: verified counts and skipped-reason counts by source. These are observability, not authority.

Use SQLite from Python’s standard library, platform filesystem primitives and standard-library hashing/archive/network facilities. No new service or third-party runtime package is required. Network code is reachable only from explicit fetch-enabled index construction.

### Verifier protocol

The helper’s `verify` mode takes a bounded JSON request on stdin and returns one bounded JSON object. Paths are data, never shell fragments.

`VerifyRequest` contains the input path, returned file path, session project root, and native text slice coordinates/length needed to bind `file.content`. The index location is the helper’s own cache policy, not a path supplied by the tool call.

`VerifyResult` is one of:

- `verified`: schema/policy version, generation, canonical file path, verified file SHA-256, byte size and source-slice digest/coordinates;
- `unknown`: a fixed reason category such as missing index, stale metadata, nonmember, changed bytes, excluded path, oversized file, unsupported slice or unavailable evidence.

Process errors, timeout, truncated output or invalid protocol also mean `unknown` to the mod. The protocol never returns file content or detected values.

### Hook-side contracts

`secrets-provenance.tsx` owns:

- `verifyRead`: consumes the native Read envelope/result and M1’s local verifier; returns verified slice evidence or unknown without throwing for ordinary provenance failure.
- `bindReadRendering`: consumes verified structured source content and native core text; returns an exact expected rendering digest and verified source-body ranges, or unknown.
- `ReadReceipt`: loop/call key, index generation, expected-rendering digest, source-body ranges and monotonic expiry; module-local and one-use.
- Receipt issue/take/reset operations implementing the state table. Taking a receipt deletes it before asynchronous work.

`secrets-detect.tsx` and `secrets-handles.tsx` accept an internal optional set of character ranges in which generic `assignment` spans may be omitted. With no ranges, existing behavior is unchanged. All stronger detectors run over the original complete string; only generic spans wholly inside approved ranges are suppressed. Recursive record scrubbing stays fully guarded unless the caller explicitly handles the verified `file.content` field.

Character ranges refer to the string being scrubbed, not UTF-8 byte offsets. The verifier’s digests use UTF-8 bytes; the rendering adapter explicitly translates to the JavaScript string’s character positions before issuing the receipt.

## cua after the merge

cua vendors the guard under `hooks/mods/guard/`; its `VENDORED.md` is the adaptation contract. A runtime merge of this work requires a resync ticket in cua naming the actual doperpowers merge commit and release version.

The ticket must include the new TypeScript provenance module, standalone Python helper, shared protocol/schema expectations and relevant tests, not only edits to existing `secrets*.tsx`. Update the vendoring table and source headers for the new file types. cua must be able to perform local verification without a devcloud plugin installation; the index is shared user-local data, while the verifier ships with each guard. Document the standalone helper’s indexing invocation for cua-only users instead of making their guard depend on `devcloud` being on PATH.

Preserve cua’s existing adaptations: it neither answers nor writes devcloud’s guard marker; its hooks and error handler stand down while the live devcloud marker is present; its prompt section id remains cua’s; and its hook registration remains compatible with cua’s own registrations. The helper path is relative to the owning plugin. Do not change the marker’s meaning or persist provenance in it.

The resync tests must cover cua alone, devcloud outside cua, devcloud inside cua, and removal/reload of devcloud, including loss of outstanding receipts and continued full fallback. Run cua’s mod tests and update `VENDORED.md` to the exact source commit. This specification does not authorize silently editing cua while implementing devcloud.

## Surprises & Discoveries

- Observation: Original-artifact equality provides substantial coverage without trusting timestamps or owner writability.
  Evidence: 526 generic-hit file instances across 48 npm versions and four SDK components matched their original archive members; they account for all 1,518 measured generic matches.

- Observation: Timestamp checks are not a usable replacement for content evidence on the measured installations.
  Evidence: npm candidates retained only 528 or 582 of 1,094 generic matches; no gcloud generic-hit file passed its manifest-time check.

- Observation: Real package trees contain generated state even when their source files remain original.
  Evidence: 33,585 SDK `.pyc` files were absent from component manifests; a sampled global CLI can install a missing executable and version marker into its own tree.

- Observation: The original executable denominator overstates the opportunity for this Read-only feature.
  Evidence: its 301 matches were measured over printable-string extraction; the signed native binary is approximately 262 MiB and is outside the supported source-file path.

- Observation: The existing guard has no cross-pass provenance map, and append cannot repair the structured tool record.
  Evidence: `secrets.tsx` independently scrubs result records and appended blocks; the engine’s append contract leaves `toolUseResult` outside the hook input.

- Observation: Hook overruns can unload the guard rather than merely delay a Read.
  Evidence: the inspected 2.1.308 bundle retains a 10-second hook budget and unloads after two consecutive ignored-signal overruns. The current minified constants are `cye=1e4` and `dts=2`; friction tracker #304 records the behavior and its check. This is why index construction is never a hook operation.

## Decision Log

- Decision: Verification consists of one independent adversarial spec review covering the design and all milestones, followed after implementation by doperpowers:review-code at the high rung on the entire branch, plus the committed gates and native acceptance described above.
  Rationale: Installed-file ownership and cross-pass exemption authority change a security boundary. A narrower detector-only review would miss the principal failure modes. The adversarial review must test boundedness, byte/result binding, stale state, package metadata assumptions and cua’s reload behavior as well as buildability.
  Date/Author: 2026-10-22, provenance design session.

- Decision: Spawn the verifier only for a Read with a generic match in its source content under a published installation root (§4).
  Rationale: Spawning a Python process on every Read would add latency to every file read. A Read with no generic match has nothing to preserve, and one outside every indexed root can't be verified. The alternative, keeping the verifier as a long-lived child process, would add a lifecycle the hook would have to manage across reloads.
  Date/Author: 2026-10-22, the coordinating session.

## Outcomes & Retrospective

Pending — written at finish.

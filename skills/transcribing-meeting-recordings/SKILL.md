---
name: transcribing-meeting-recordings
description: Turn meeting/screen recordings (mp4/m4a, Zoom folders) into a diarized, visually grounded transcript package — the upstream stage of doperpowers:organizing-sprints. Invoke on the recording files; the skill asks for speaker info and scope decisions before processing.
disable-model-invocation: true
---

# Transcribing meeting recordings (diarized + visually grounded)

Produces a package another agent can consume **without touching the media**: a
speaker-labeled transcript where every point in time maps to what was on screen,
plus tooling to pull more frames on demand. Typical downstream: meeting notes,
then doperpowers:organizing-sprints.

Vendored pipeline: [scripts/](scripts/) — workspace conventions and run order in
[references/pipeline-reference.md](references/pipeline-reference.md).

## Ask the human up front

- **Speaker count and names** (the API accepts up to 4 named speakers). Optionally
  timestamps where each speaker talks solo for 5–10s — these seed pass 1 even if
  they come from a different recording than the one you transcribe.
- **With 5+ speakers**, have the user pick the ≤4 whose attribution matters most
  as the named refs. The rest come back as per-chunk anonymous labels: attribute
  those by reading context within each chunk (never by merging labels across
  chunks — see Label QA) and mark them lower-confidence in the package.
- **Scope decisions**: which recording is canonical when several exist; whether
  audio outside the video's span matters. These change the pipeline shape, so ask
  before processing, not after.

## Source prep

- **Transcribe the video's own audio track** when a video exists. Then transcript
  timestamps ARE frame timestamps — no offset bookkeeping. A separate voice
  recorder may sound cleaner, but it costs a sync layer and makes reference clips
  cross-channel, which wrecks speaker matching (see Label QA).
- If you must align a separate audio file to video anyway: `scripts/sync_offset.py`
  (RMS-envelope cross-correlation); trust it only when the peak clearly separates
  from the runner-up and its head/tail drift check agrees within ~0.2s per hour.
- **Multi-part recordings** (Zoom's free tier splits at 40min): keep each part its
  own timebase (p1, p2, …). Never stitch a fake continuous timeline — frame grabs
  must stay exact, and the gaps between parts are genuinely unrecorded; state that
  in the README. A ~4s audio file sitting next to the real one in a Zoom folder is
  an aborted-start stub, not content.

## Chunk + diarize in parallel

`scripts/make_chunks.py` then `scripts/run_diarize.py`. The API contract for
`gpt-4o-transcribe-diarize` (the non-guessable parts):

```python
resp = client.audio.transcriptions.with_raw_response.create(  # raw: the SDK's typed model silently drops diarization fields
    model="gpt-4o-transcribe-diarize", file=f,
    response_format="diarized_json",          # segments with speaker/start/end/text
    chunking_strategy="auto",                 # REQUIRED for audio >30s
    known_speaker_names=names,                # ≤4
    known_speaker_references=data_urls,       # data:audio/wav;base64,… — 2–10s each
)
data = json.loads(resp.text)
```

- `prompt` and `timestamp_granularities` are **not supported** on this model.
- Chunking exists for the 25MB upload limit and parallelism, not model capability:
  ~10-minute chunks as 64kbps mono MP3 (~5MB each), cut at the quietest 300ms
  window near each 10-minute mark so no word is split.
- **No overlap between chunks**: because every chunk receives the same named
  reference clips, speaker labels agree across chunks by construction. This is
  what makes chunks fully independent and parallelizable.
- One pool for all chunks across all parts; resume-safe (skip existing outputs).
  Run it in the background (the harness blocks `sleep`; rely on the completion
  notification).

## Label QA — plan for two passes

- `scripts/label_stats.py`: per-chunk named vs anonymous (`A`/`B`/…) counts.
  Anonymous labels are **per-chunk identities — never merge them across chunks**.
- **Cross-channel reference clips degrade matching badly**: clips cut from a
  different mic/mix than the transcribed track produced 29% and 35% anonymous
  labels in two separate real runs. Same-channel clips took those runs to 3.9%
  and 0.7%. So treat pass 1 (human-pointed or cross-channel refs) as a bootstrap,
  not the result. Pass 2 trigger: overall anon rate above ~5%, or any chunk where
  a named speaker is depleted while one anonymous label dominates with that
  speaker's speech.
- **Pass 2**: `scripts/bootstrap_refs.py` cuts each speaker's best confident solo
  run **from the transcription track itself** as new refs; rerun all chunks.
  Residual anonymous after pass 2 is sub-second crosstalk interjections: accept
  and render as unknown in the transcript's language (`Unknown A` / `미확인 A`).
- The bootstrap is **per transcription channel**: if the package includes a
  segment transcribed from a different source (e.g. an audio-only gap covered by
  a voice recorder while the rest uses the video track), that segment needs its
  own refs cut from its own source — refs from the other channel put you back in
  the cross-channel failure mode.
- Sanity-check identity by reading: do the labels' roles cohere (who demos, who
  directs, who gets assigned fixes)? The ASR also garbles spoken names in the
  transcribed *text* (a real run heard 김민혁 as "민영님/미영님") — record name
  equivalences in the README so readers don't invent an extra participant.
- Watch for spans where the model "translates" speech into another language
  instead of transcribing — flag them with timestamps as re-listen candidates.

## Visual grounding — full coverage, not keyword hits

Selecting frames by deictic keywords ("look here", "this one", "여기 보시면")
under-covers: in a real run it missed screens that changed conclusions — a
feature recorded as broken in the previous meeting was visibly working on
screen, and the keyword-selected frames never showed it. Ground the whole
recording instead:

1. `scripts/extract_frames.py` — scene-change detection plus 60s uniform fill.
   Two known blind spots motivate the two layers: webcam-only stretches spew
   hundreds of false scene candidates (face motion), and SPA page transitions on
   white backgrounds score *below* the scene threshold and are missed entirely.
2. **Read every extracted frame** (a 97-minute meeting ≈ 170 frames — cheap
   relative to what a missed screen costs). Identify each: URL/page/state, or
   "webcam only".
3. Author the **screen index** (`work/screen_index.json`): per part, ordered
   `{t, frame|null, one-line desc}` where each entry holds until the next.
   `null` = no share active — marking this explicitly stops downstream agents
   from hunting for evidence that doesn't exist.
4. `scripts/merge_transcript.py` regenerates `transcript.md` with a marker at
   every screen transition and `transcript.json` with the index embedded per
   part plus a per-segment `"screen"` field.
5. **Unrecoverable visuals**: when two people share simultaneously, Zoom records
   only one stream. If the audio references a screen the recording never captured,
   document that in the package rather than grabbing a plausible-looking wrong frame.
6. `scripts/grab_frame.py` pulls arbitrary timestamps between indexed frames.

## Package layout

```
meeting_<date>/
  sources.json       # parts + speakers (drives every script)
  transcript.md      # inline 🖼 screen markers; header explains the convention
  transcript.json    # + parts[].screens index, per-segment "screen" path
  screen_timeline.md # human-browsable screen states with discussion context
  frames_all/        # all extracted frames  <part>_<mmss>.jpg
  README.md          # timebase conventions, method, limits (crosstalk→dominant
                     # voice, name mangling, translated spans, unrecorded gaps)
  meeting_notes.md   # if asked — cite frame paths as evidence for each claim
  work/              # 16k wavs, chunks, raw diarize JSON, refs, screen_index.json
```

Hand off to doperpowers:organizing-sprints; its worker reads transcript + markers
and pulls frames only where it needs visual confirmation.

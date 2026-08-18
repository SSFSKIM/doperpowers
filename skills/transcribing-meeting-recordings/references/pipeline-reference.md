# Pipeline reference — workspace convention and run order

The scripts in `../scripts/` are the validated pipeline from real runs. They all
key off one workspace directory containing `sources.json`:

```json
{
  "parts":    {"p1": "/abs/path/part1.mp4", "p2": "/abs/path/part2.mp4"},
  "speakers": {"alice": "Alice Kim", "bob": "Bob Lee", "carol": "Carol Park"},
  "unknown_word": "Unknown"
}
```

- `parts` keys are the timebase ids used everywhere (chunk names, frame names,
  transcript sections). Values may be video or audio files; video-less parts are
  skipped by frame extraction automatically.
- `speakers` keys are the ASCII ids sent to the API (≤4); values are display
  names for the transcript.
- `unknown_word` renders unmatched speakers (`Unknown A` / `미확인 A`).

## Run order

```bash
S=path/to/skills/transcribing-meeting-recordings/scripts   W=meeting_dir

python3 $S/make_chunks.py $W                      # 16k wavs + mp3 chunks + manifest
# pass 1: refs from human-pointed timestamps (cut 5-10s wavs into refs_v1/,
#         named {speaker_id}.wav) — cross-channel is acceptable HERE only
python3 $S/run_diarize.py $W refs_v1 diarized_v1  # background; resume-safe
python3 $S/label_stats.py $W diarized_v1          # pass-2 trigger check
python3 $S/bootstrap_refs.py $W diarized_v1 $W/refs_v2   # same-channel refs
python3 $S/run_diarize.py $W $W/refs_v2 diarized_v2      # pass 2, all chunks
python3 $S/label_stats.py $W diarized_v2

python3 $S/extract_frames.py $W                   # scene detect + uniform fill
# JUDGMENT STEP — no script: read every frame in $W/frames_all/, then author
# $W/work/screen_index.json (schema below)
python3 $S/merge_transcript.py $W diarized_v2     # transcript.json/.md + markers

python3 $S/sync_offset.py A.mp4 B.m4a             # only if syncing external audio
python3 $S/grab_frame.py $W p1 1234.5             # ad-hoc frames afterwards
```

## screen_index.json — authored, not generated

The frame extractor gives coverage; **you** give meaning. After reading every
frame, write per part an ordered list of screen *states* (not one entry per
frame — collapse duplicates and webcam churn):

```json
{
  "p1": [
    {"t": 0,   "frame": null, "desc": "no share — call setup talk"},
    {"t": 285, "frame": "frames_all/p1_0445.jpg", "desc": "signup role-selection page"},
    {"t": 990, "frame": "frames_all/p1_1652.jpg", "desc": "admin grade-entry form (mismatch discussion)"}
  ]
}
```

Each entry holds from `t` until the next entry. `frame: null` states are as
important as the others — they tell downstream readers that stretch has no
visual evidence. Also record, in the package README, any visuals the recording
provably never captured (e.g. a second simultaneous share).

## Parameters (tested defaults, with the reason that matters)

| Where | Value | Reason |
|---|---|---|
| chunk length / bitrate | 600s / 64kbps mono MP3 | 25MB upload limit; ~5MB per chunk |
| boundary search | quietest 300ms within ±25s | don't split words |
| scene threshold | 0.08 | invariant is its blind spots (see SKILL.md), not the number |
| uniform fill | 60s, skip within 25s of a scene frame | covers sub-threshold SPA transitions |
| frame offset | cut + 1.0s | page has rendered |
| solo-run selection | gap <0.8s, ≥4s, cap 9.5s | API wants 2–10s refs; runs scored by chunk label quality |
| pass-2 trigger | anon >~5% or a depleted named speaker | below that, residue is crosstalk slivers |
| turn merge | same speaker, gap <3s, same screen | readable turns without crossing screen states |

## Environment gotchas hit during real runs

- The harness blocks foreground `sleep` — run diarize/scene-detect as background
  tasks and act on completion notifications.
- Persistent-shell cwd drifts between calls — the scripts take the workspace as
  an argument and resolve paths absolutely for this reason.

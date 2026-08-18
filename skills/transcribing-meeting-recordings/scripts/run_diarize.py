#!/usr/bin/env python3
"""Parallel diarized transcription of all chunks with known-speaker references.

Usage: run_diarize.py <workspace> <refs_dir> <out_subdir>
  <refs_dir> holds {api_id}.wav (2-10s, MUST be cut from the transcription
  track itself for good matching — see SKILL.md Label QA) for every key in
  sources.json "speakers".
  Output: <workspace>/work/<out_subdir>/{chunk_stem}.json (raw diarized_json)

Resume-safe (skips chunks whose output exists). Run in background; ~10-min
chunks take minutes each. Requires OPENAI_API_KEY.
"""
import base64
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

W = Path(sys.argv[1]).resolve()
REF_DIR = Path(sys.argv[2]).resolve()
OUT = W / "work" / sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)

SPEAKERS = list(json.loads((W / "sources.json").read_text())["speakers"].keys())
REF_URLS = [
    "data:audio/wav;base64," + base64.b64encode((REF_DIR / f"{s}.wav").read_bytes()).decode()
    for s in SPEAKERS
]

CHUNKS = W / "chunks"
manifest = json.loads((CHUNKS / "manifest.json").read_text())
client = OpenAI(timeout=900.0, max_retries=0)


def transcribe(entry):
    out_path = OUT / (Path(entry["file"]).stem + ".json")
    if out_path.exists():
        return entry["file"], "cached"
    last_err = None
    for attempt in range(4):
        try:
            with open(CHUNKS / entry["file"], "rb") as f:
                # with_raw_response: the SDK's typed model silently drops
                # diarization fields. prompt / timestamp_granularities are NOT
                # supported on this model; chunking_strategy is REQUIRED >30s.
                resp = client.audio.transcriptions.with_raw_response.create(
                    model="gpt-4o-transcribe-diarize",
                    file=f,
                    response_format="diarized_json",
                    chunking_strategy="auto",
                    known_speaker_names=SPEAKERS,
                    known_speaker_references=REF_URLS,
                )
            data = json.loads(resp.text)
            assert data.get("segments"), f"no segments: {list(data)}"
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            return entry["file"], f"ok ({len(data['segments'])} segments)"
        except Exception as e:
            last_err = e
            wait = 15 * (attempt + 1)
            print(f"  {entry['file']} attempt {attempt+1} failed: "
                  f"{type(e).__name__}: {str(e)[:200]} -> retry in {wait}s", flush=True)
            time.sleep(wait)
    return entry["file"], f"FAILED: {last_err}"


t0 = time.time()
with ThreadPoolExecutor(max_workers=6) as ex:
    futs = [ex.submit(transcribe, m) for m in manifest]
    for fut in as_completed(futs):
        name, status = fut.result()
        print(f"[{time.time()-t0:6.0f}s] {name}: {status}", flush=True)
print(f"done in {time.time()-t0:.0f}s")

# 0001. Verification — Accuracy evaluation over a committed LibriSpeech corpus

**Date**: 2026-08-18
**Status**: Passed

Drives the real app against the spec's acceptance criteria. Build: [index.md](index.md). Decision record: [rationale.md](rationale.md). Each step names the criterion it proves. Run from `backend/`.

## Verify steps

1. [x] **Run a config end to end (AC-2, AC-3, AC-5)**: run `uv run python -m tests.benchmarks.evaluate_accuracy --model tiny --device cpu --compute-type int8 --beam-size 1 --output benchmark-results/accuracy-tiny.json` against the committed corpus. Pass: command succeeds, 20 sample rows scored, average WER within 0.005 of the §6.3 table's tiny row.
2. [x] **Run the other two configs (AC-3)**: repeat the command for `--model base` and `--model small`. Pass: `benchmark-results/accuracy-base.json` and `benchmark-results/accuracy-small.json` exist with average WER matching the base and small rows in §6.3 (within 0.005).
3. [x] **Normalization works (AC-2)**: inspect one sample row in a fresh run artifact. Pass: hypothesis and reference agree on the normalized text where the engine is correct, differing only by case or punctuation on errors; a hypothesis that is uppercase or carries punctuation scores a lower error than raw `jiwer` would give.
4. [x] **Empty manifest fails deliberately (AC-2)**: run the harness against a manifest with zero samples (e.g. a temp copy with `samples: []`). Pass: command exits with a clear, deliberate error before scoring.
5. [x] **Every doc row traces to an artifact (AC-4)**: for each row in the `docs/benchmarking.md` §6.3 table, confirm the named source artifact exists at `backend/benchmark-results/accuracy-{tiny,base,small}.json`. Pass: no row is hand typed without a committed artifact behind it.
6. [x] **Corpus rebuilds offline, byte identical (AC-1, AC-6)**: run `uv run python scripts/rebuild_accuracy_corpus.py --archive <path-to-test-clean.tar.gz> --output /tmp/accuracy-rebuild` from a clean checkout with the archive present but no network. Pass: WAVs and manifest match the committed fixtures (compare by sha256), the NOTICE names source archive, sha256, date, and CC BY 4.0, and the script ran with no network calls.
7. [x] **Provenance present (AC-6)**: read `backend/tests/fixtures/accuracy/NOTICE` (and `manifest.json` `provenance`). Pass: source archive, sha256 `39fde525e59672dc6d1551919b1478f724438a95aa55f874b576be21967e6c23`, download date, and CC BY 4.0 license are named.
8. [x] **Reproduce within tolerance (AC-5)**: rerun step 1's tiny command a second time (or on a fresh clone with lockfile intact). Pass: average WER lands within 0.005 (0.5 WER points) of the recorded value; `uv.lock` pins the dependency versions.

## Value sourcing

| Action | Value produced or displayed | Source |
|---|---|---|
| Run a config | per sample WER and CER | `jiwer` over reference (manifest field) and hypothesis (engine output), normalized |
| Run a config | average WER and CER | mean over per sample rows in the same run |
| Run a config | run metadata (git SHA, hardware, versions) | `run_metadata` helper in `benchmark_utils.py` |
| Report to the doc | one table row per config | the committed JSON artifact for that run |
| Rebuild corpus | WAVs, manifest, NOTICE | frozen clip list + archive in `rebuild_accuracy_corpus.py` |

## Coverage gaps

- The average-WER assertion in steps 1 and 2 covers the run path and scoring; it does not cover the streaming pipeline (VAD, windowing, partial assembly), which is explicitly out of scope (see index.md Follow-up).
- Step 5 is a doc-to-artifact trace, not an executable assertion; the trace is done by reading the committed artifacts, not by the app.

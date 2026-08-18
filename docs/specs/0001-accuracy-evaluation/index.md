# 0001. Accuracy evaluation over a committed LibriSpeech corpus

**Date**: 2026-08-18
**Status**: Accepted

## Summary

We will give V1 a defensible accuracy number by running WER and CER scores over a small, committed corpus of real recorded speech. We take 20 clips from the LibriSpeech test clean benchmark, already 16 kHz mono, re encode them to WAV, commit the clips and the ground truth manifest to the repo, and run the accuracy harness over three model configurations on CPU. One scoring fix lands first: the harness lowercases and strips punctuation from both sides before scoring, so the number matches the documented method and the uppercase dataset transcripts do not inflate it. The measured rows land in the benchmarking doc so a reviewer sees a real number, not a placeholder.

Context and design alternatives: [rationale.md](rationale.md). Verification procedure: [verify.md](verify.md).

## Requirements

**User stories**:
- As a reviewer, I want to see a real WER and CER for the V1 configuration so I can judge whether the streaming product is accurate enough.
- As an engineer, I want a corpus I can rebuild and a command I can rerun so the number is reproducible, not anecdotal.

**Acceptance criteria** (the contract):
- **AC-1**: A committed corpus of 20 LibriSpeech test clean clips exists at 16 kHz mono as WAVs with a ground truth manifest under `backend/tests/fixtures/accuracy/`, and a deterministic rebuild script in `backend/scripts/` can recreate it offline. The committed clips are the source of truth; no run needs network.
- **AC-2**: `evaluate_accuracy.py` runs end to end on the committed corpus, normalizes both reference and hypothesis by lowercasing and stripping punctuation before scoring, records per sample WER and CER plus per config averages, and still fails deliberately when the manifest has no samples.
- **AC-3**: The run spans three model configurations, tiny, base, and small, on CPU int8 with beam size pinned to 1, and each run writes a JSON artifact at `backend/benchmark-results/accuracy-{tiny,base,small}.json` with run metadata.
- **AC-4**: The reporting table in `docs/benchmarking.md` §6.3 carries the measured rows, one per configuration, with the average WER and CER for English with the beam pinned, and each row states its source artifact. The doc paths in §5.2, §5.3, and §5.6 are reconciled to the artifact and corpus locations.
- **AC-5**: A reviewer reproduces the documented commands and lands within a 0.5 WER point of the recorded number, pinned by the lockfile so the dependency versions stay fixed.
- **AC-6**: Provenance and license are recorded: the manifest or a NOTICE names the source archive, its checksum, the download date, and the CC BY 4.0 license, and the rebuild script embeds a frozen clip ID list with the selection rationale.

## Decision

**Chosen option**: Option 1: Public dataset subset (rationale and alternatives in [rationale.md](rationale.md))

Commit 20 episodes from LibriSpeech test clean as 16 kHz mono WAVs plus a manifest, rebuildable from a deterministic offline script, fix the harness scoring to be case insensitive and punctuation stripped, and run the harness over tiny, base, and small models on CPU int8 with beam pinned to 1. Results are recorded as committed JSON at known artifact paths and summarized in the benchmarking doc with provenance.

**Implementation skills**: `pytest-coverage` (awesome-copilot, `backend/.agents/skills/pytest-coverage/`)

## Feature design

**Data model sketch**:
- Corpus manifest (`backend/tests/fixtures/accuracy/manifest.json`), schema owned by `load_accuracy_manifest`, fixed at version 1, `sample_rate` 16000, `channels` 1.
- Sample entry: `id` (repeatable key), `audio` (WAV path relative to the manifest), `reference` (ground truth text), `tags` (metadata spread over speakers, speeds, quietness, noise, accents).
- Run artifact (JSON), written by `write_report`: `run_id`, `timestamp`, `git_sha`, host and software metadata, configuration block, per sample score rows, average WER and CER, latency percentiles.

No database is involved; the manifest is the fixture and the artifact is the record.

**Value sourcing**:
| Action | Value produced or displayed | Source |
|---|---|---|
| Build the corpus | each sample id, audio path, reference text, tags | pinned download script selects clips and texts from LibriSpeech test clean, writes manifest |
| Run a config | per sample WER and CER | `jiwer` over reference (manifest field) and hypothesis (engine output) |
| Run a config | average WER and CER | mean over per sample rows in the same run |
| Run a config | run metadata (git SHA, hardware, versions) | `run_metadata` helper in `benchmark_utils.py` |
| Report to the doc | one table row per config | the committed JSON artifact for that run |

**Key invariants**:
- The manifest is always 16 kHz mono; `load_audio` rejects anything else.
- An empty manifest fails the run deliberately. (basis: `evaluate_accuracy.py`, the guard)
- Scoring lowercases both reference and hypothesis and strips punctuation before `jiwer`, so code matches `docs/benchmarking.md` §6.1.
- The corpus is rebuildable only from the frozen clip list in the script, so clips stay byte identical across machines.
- The docs rows must trace to committed artifacts, never hand typed guesses.

**Security model**:
No user data involved. The corpus is public benchmark audio, stored as plain WAV fixtures in the repo. The download script runs locally and needs network only at build time, never at run time.

**Configuration required**:
- No new runtime settings. The script embeds the frozen clip list, the source archive, its checksum, and the set beam size in code, so corpus and scoring are deterministic without env driven selection.

**Critical test scenarios** (each maps to an acceptance criterion):
- Happy path: run the documented accuracy command on the committed corpus for all three configs, confirm per sample rows, averages, and JSON artifacts, verifies **AC-1**, **AC-2**, **AC-3**
- Normalization check: a hypothesis with punctuation or uppercase only scores a lower error than raw `jiwer` would give, confirming the case and punctuation normalization, verifies **AC-2**
- Failure case: run against an empty or missing manifest and confirm a deliberate, clear error, verifies **AC-2**
- Reproducibility repo check: confirm every row in the §6.3 table has a matching committed `benchmark-results/*.json`, verifies **AC-4**
- Fresh machine check: clone, rebuild fixtures offline with the rebuild script, rerun the commands, confirm the numbers land within the tolerance, verifies **AC-1**, **AC-5**
- Provenance check: the manifest or NOTICE names the archive, checksum, date, and CC BY 4.0 license, verifies **AC-6**

## Build plan

1. [x] Edit `evaluate_accuracy.py` so scoring lowercases and strips punctuation on both reference and hypothesis before `jiwer`, and pin the beam size from the service default, satisfies **AC-2**
2. [x] Add the corpus tool `backend/scripts/rebuild_accuracy_corpus.py` with the frozen clip ID list, source archive and checksum, offline re encode logic, and provenance and NOTICE output, plus its unit tests, satisfies **AC-1**, **AC-6**
3. [x] Run the corpus tool to materialize the 20 WAVs, the manifest, and the NOTICE, and commit them under `backend/tests/fixtures/accuracy/`, satisfies **AC-1**, **AC-6**
4. [x] Smoke run `evaluate_accuracy.py` on the committed corpus with the base config, on CPU int8, beam 1, to prove the end to end path is live and the normalization works, satisfies **AC-2**
5. [x] Run tiny, base, and small configs on CPU int8, beam 1, and commit each JSON artifact at `backend/benchmark-results/accuracy-{tiny,base,small}.json`, satisfies **AC-3**
6. [x] Reconcile `docs/benchmarking.md` §5.2, §5.3, and §5.6 paths and commands, fill the §6.3 reporting table from the committed artifacts with provenance and the 0.5 tolerance, satisfies **AC-4**, **AC-6**
7. [x] On a clean checkout rerun the documented commands and confirm the numbers land within tolerance, satisfies **AC-5**

## Consequences

**Positive**:
- V1 gets a real, reproducible accuracy claim.
- The committed corpus feeds later slices (model tests and benchmark report) without new work.
- A reviewer reruns the documented commands and trusts the number.

**Negative / tradeoffs**:
- The repo carries a few megabytes of binary audio fixtures.
- LibriSpeech test clean is clean, well pronounced speech, so the numbers will look better than a live noisy demo.
- Committed artifacts can drift from the doc table if the table is edited by hand (the trace rule guards this).
- The scoring change touches existing harness code, so it needs its own test coverage.

**Neutral**:
- Accuracy here measures the engine on whole clips, not the streaming pipeline with VAD and windowing; the pipeline view is out of this slice.
- LibriSpeech is already 16 kHz mono, so the corpus tool is a re encode and re selection step, not a resampling pipeline.
- One run per configuration stands in for the five runs the methodology suggests, because with a fixed corpus, a fixed beam, and a pinned lockfile the score is deterministic; the deviation is recorded in the doc.

## Follow-up

- [ ] Consider a later slice that scores the streaming pipeline (VAD, windowing, partial assembly) on the same corpus, so the accuracy claim reflects the live path.

## References

Decision record, context, options, and rationale: [rationale.md](rationale.md). Verification procedure: [verify.md](verify.md).
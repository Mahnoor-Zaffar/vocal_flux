# 0001. Rationale — Accuracy evaluation over a committed LibriSpeech corpus

The decision record for [index.md](index.md). This file holds the context, the options considered, and the reasoning behind the choice; the build spec lives in `index.md`.

## Context

The scope does list a V1 accuracy claim as a goal, and the harness to produce one already exists. `evaluate_accuracy.py` loads a manifest of audio samples, transcribes each one through the established lifecycle and engine, and scores each with `jiwer` WER and CER. `benchmark_utils.py` validates that the manifest is 16 kHz mono, loads the WAVs, and writes a structured JSON report. This machinery is complete and passing, but the manifest is empty and there are no audio fixtures, so the command fails deliberately and no number can be produced.

The methodology is also in place in the benchmarking doc: the metrics formula, the required sample spread, the reporting table, and the rule that all reference clips are a fixed versioned set in the repo so runs stay comparable. What is missing is the productive core: a real corpus with ground truth and a run that fills the table.

One mismatch between doc and code must be closed before any number is defensible. The benchmarking doc says WER and CER are computed case insensitive with reference punctuation stripped, but the harness passes the raw texts to `jiwer`, whose default transform only splits on whitespace and keeps case and punctuation. LibriSpeech transcripts are uppercase, so scoring them as is would inflate errors. Making the harness lower both sides and strip punctuation aligns code with the documented method.

Two forces shape the choice of corpus. First, the accuracy number must be believable to a reviewer, which argues for real recorded human speech with a well documented license rather than a synthetic or self recorded set. Second, results must be reproducible on any machine without a network or a GPU, which argues for a small corpus committed to git. LibriSpeech test clean meets both: it is the standard clean read speech benchmark, its clips are short and already 16 kHz mono, and a 20 clip subset re encoded to WAV stays a few megabytes in git. The committed clips are the source of truth; the rebuild script is a deterministic offline way to recreate them, never a network dependency at run time.

## Options considered

### Option 1: Public dataset subset

Take a handful of clips from a standard open benchmark, resample to 16 kHz mono, commit the WAVs and a manifest into the repo. The transcripts are the ground truth. (basis: docs/benchmarking.md, the versioned baseline audio corpus rule)

**Pros**:
- Real recorded speech, which reviewers trust.
- Documented licensing and provable ground truth.
- Reproducible with no network at run time.

**Cons**:
- The audio is committed binary, so the repo grows a few megabytes.
- Clip variety is limited to what the dataset offers; noise and accent spread depends on the chosen subset.

### Option 2: Synthesized with TTS

Generate the corpus locally with a speech synthesis tool, keeping the prompt text as ground truth.

**Pros**:
- Byte exact ground truth.
- Tiny, cleanly generated files with no provenance worries.
- Fast to change the corpus.

**Cons**:
- Synthetic speech scores better than human speech, so the number overstates real world accuracy.
- No accent variety beyond the chosen voice.

### Option 3: Record ourselves

Read a prepared script into a microphone, store the prompt as the ground truth.

**Pros**:
- Fully under our control, matches the exact scenario.
- No licensing question at all.

**Cons**:
- Pronunciations vary, so the ground truth is only approximate.
- Hard to reproduce identically on another machine or for another run.
- A reviewer cannot verify the recording conditions.

## Decision

**Chosen option**: Option 1: Public dataset subset

Commit 20 episodes from LibriSpeech test clean as 16 kHz mono WAVs plus a manifest, rebuildable from a deterministic offline script, fix the harness scoring to be case insensitive and punctuation stripped, and run the harness over tiny, base, and small models on CPU int8 with beam pinned to 1. Results are recorded as committed JSON at known artifact paths and summarized in the benchmarking doc with provenance.

**Implementation skills**: `pytest-coverage` (awesome-copilot, `backend/.agents/skills/pytest-coverage/`)

## Rationale

The existing harness and methodology already settle the scoring mechanics, so this spec only has to settle what feeds them. LibriSpeech test clean is the boring, well understood choice: it is real recorded speech on a standard benchmark, its license permits redistribution, and a 20 clip subset is small enough to commit and rerun on any machine. This directly serves the scope goal, which asks for a defensible V1 accuracy number, and the scope rule that the service stays CPU first for local dev rules out GPU only configs for this slice.

Synthesized speech would score too easily, and self recorded clips would be unverifiable; both weaken the claim this slice exists to make. (basis: the scope header, which names a defensible accuracy number as the slice goal, and `docs/benchmarking.md` §2, the model configuration matrix)

The three model sizes give the report a small curve (does a bigger model buy accuracy on this corpus) for little extra runtime on a laptop, which is the honest minimum to justify that table. The document command path is already proven by the passing harness. Beam is pinned to 1 to match the streaming service default, so the headline number reflects the product default, not a tuned beam for bigger scores. (basis: the service default `WHISPER_BEAM_SIZE=1` in `.env.example` and `docs/benchmarking.md` §5.6, the documented commands)

## References

**Project sources**:
- `docs/benchmarking.md`: §2 model configuration matrix, §5 versioned baseline corpus, §6 accuracy evaluation, §5.6 documented commands
- `backend/tests/benchmarks/evaluate_accuracy.py`: the harness this slice runs and edits
- `backend/tests/benchmarks/benchmark_utils.py`: manifest loader, audio loader, report writer
- `docs/scope/scope.md`: Slice 1 accuracy evaluation

**Practices & standards**:
- WER and CER via the `jiwer` library, the standard edit distance metric for automatic speech recognition
- Redistribution rules of LibriSpeech, which is CC BY 4.0, for committed audio fixtures
- Lowercasing and punctuation stripping on both sides of an ASR comparison, the normalization that makes WER comparable across tools

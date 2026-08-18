# Accuracy Fixtures

A fixed corpus of 20 LibriSpeech test clean clips, re encoded to 16 kHz mono
WAV files, with ground truth transcripts in `manifest.json`. These files back
the WER and CER accuracy evaluation; see `docs/benchmarking.md` section 6.

The clips are committed as the source of truth, so accuracy runs need no
network and no dataset download.

- `manifest.json`: versioned sample list (id, audio path, reference text, tags)
- `NOTICE`: source archive, checksum, build date, and CC BY 4.0 license
- `*.wav`: the re encoded 16 kHz mono clips

To rebuild the corpus byte for byte, run:

```bash
cd backend
uv run python scripts/rebuild_accuracy_corpus.py \
  --archive /path/to/test-clean.tar.gz \
  --output tests/fixtures/accuracy
```

The archive itself is not committed; download it once from the URL in the
rebuild script. Rebuilding requires network, running accuracy does not.

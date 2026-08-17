# Accuracy Fixtures

Add 10–30 representative 16 kHz mono WAV files in this directory and register
each file in `manifest.json`.

```json
{
  "version": 1,
  "sample_rate": 16000,
  "channels": 1,
  "samples": [
    {
      "id": "speaker-01-short-clean",
      "audio": "speaker-01-short-clean.wav",
      "reference": "The quick brown fox.",
      "tags": ["short", "clean"]
    }
  ]
}
```

The manifest is versioned and the audio files are intentionally kept out of
Git. Do not commit private or identifying recordings.

"use client";

import { useCallback, useState } from "react";
import Link from "next/link";

import { AudioVisualizer } from "@/components/AudioVisualizer";
import { ConnectionStatus } from "@/components/ConnectionStatus";
import { MetricsPanel } from "@/components/MetricsPanel";
import { Recorder } from "@/components/Recorder";
import { SessionControls } from "@/components/SessionControls";
import { Transcript } from "@/components/Transcript";
import { useRecorder } from "@/hooks/useRecorder";
import { useTranscription } from "@/hooks/useTranscription";

export default function Home() {
  const [isStarting, setIsStarting] = useState(false);
  const transcription = useTranscription();
  const recorder = useRecorder({ onAudio: transcription.sendAudio });

  const start = useCallback(async () => {
    setIsStarting(true);
    transcription.reset();
    try {
      await transcription.connect();
      await recorder.start();
    } catch (startError) {
      transcription.disconnect();
      const message = startError instanceof Error ? startError.message : "Unable to start recording";
      window.alert(message);
    } finally {
      setIsStarting(false);
    }
  }, [recorder, transcription]);

  const stop = useCallback(async () => {
    await recorder.stop();
    transcription.stop();
  }, [recorder, transcription]);

  return (
    <main className="site-shell">
      <div className="grain" aria-hidden="true" />
      <header className="topbar">
        <Link className="wordmark" href="/" aria-label="VocalFlux home">
          <span className="wordmark-mark" aria-hidden="true">VF</span>
          <span>VocalFlux</span>
        </Link>
        <div className="topbar-meta">
          <span className="build-label">REAL-TIME ASR / V1</span>
          <ConnectionStatus status={transcription.status} />
        </div>
      </header>

      <section className="hero" aria-labelledby="page-title">
        <div className="hero-copy">
          <span className="eyebrow">Speech, in flight.</span>
          <h1 id="page-title">Hear the system<br /><em>think</em> in real time.</h1>
          <p>
            A live window into Whisper inference. Speak into the stream and watch
            unstable hypotheses settle into committed text.
          </p>
        </div>
        <div className="hero-aside">
          <span className="aside-index">01 / 03</span>
          <span className="aside-rule" />
          <span className="aside-copy">Audio → VAD → Window → Inference</span>
        </div>
      </section>

      <div className="dashboard-grid">
        <Transcript {...transcription.transcript} />
        <div className="side-stack">
          <MetricsPanel metrics={transcription.metrics} audioLevel={recorder.audioLevel} />
          <section className="session-panel" aria-labelledby="session-heading">
            <div className="panel-heading compact-heading">
              <div>
                <span className="section-kicker">Capture node</span>
                <h2 id="session-heading">Microphone</h2>
              </div>
              <span className="node-number">00{recorder.isRecording ? "1" : "0"}</span>
            </div>
            <Recorder isRecording={recorder.isRecording} audioLevel={recorder.audioLevel} />
            <AudioVisualizer level={recorder.audioLevel} active={recorder.isRecording} />
          </section>
        </div>
      </div>

      <section className="control-deck" aria-label="Recording controls">
        <SessionControls
          isRecording={recorder.isRecording}
          isConnecting={isStarting || transcription.status === "connecting"}
          onStart={() => void start()}
          onStop={() => void stop()}
        />
        {transcription.error && <p className="error-copy" role="alert">{transcription.error}</p>}
      </section>

      <footer className="site-footer">
        <span>VOCALFLUX / SPEECH INFRASTRUCTURE</span>
        <span>faster-whisper · CTranslate2 · FastAPI</span>
      </footer>
    </main>
  );
}

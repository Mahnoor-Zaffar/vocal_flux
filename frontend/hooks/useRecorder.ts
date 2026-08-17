"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { float32ToPcm16, resampleTo16k } from "@/lib/audio";

type RecorderOptions = {
  onAudio: (payload: ArrayBuffer, audioSeconds: number) => void;
};

export function useRecorder({ onAudio }: RecorderOptions) {
  const callbackRef = useRef(onAudio);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);

  useEffect(() => {
    callbackRef.current = onAudio;
  }, [onAudio]);

  const stop = useCallback(async () => {
    workletRef.current?.disconnect();
    sourceRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (contextRef.current && contextRef.current.state !== "closed") {
      await contextRef.current.close();
    }
    workletRef.current = null;
    sourceRef.current = null;
    streamRef.current = null;
    contextRef.current = null;
    setAudioLevel(0);
    setIsRecording(false);
  }, []);

  const start = useCallback(async () => {
    if (isRecording) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    const context = new AudioContext();
    await context.audioWorklet.addModule("/audio-processor.js");
    const source = context.createMediaStreamSource(stream);
    const worklet = new AudioWorkletNode(context, "vocalflux-audio-processor");
    worklet.port.onmessage = (event: MessageEvent<Float32Array>) => {
      const samples = new Float32Array(event.data);
      const resampled = resampleTo16k(samples, context.sampleRate);
      const payload = float32ToPcm16(resampled);
      const rms = Math.sqrt(
        resampled.reduce((total, sample) => total + sample * sample, 0) /
          Math.max(1, resampled.length),
      );
      setAudioLevel(Math.min(1, rms * 3));
      callbackRef.current(payload, resampled.length / 16_000);
    };
    source.connect(worklet);
    worklet.connect(context.destination);
    streamRef.current = stream;
    contextRef.current = context;
    sourceRef.current = source;
    workletRef.current = worklet;
    setIsRecording(true);
  }, [isRecording]);

  useEffect(() => () => {
    void stop();
  }, [stop]);

  return { start, stop, isRecording, audioLevel };
}

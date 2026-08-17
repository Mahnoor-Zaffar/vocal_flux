"use client";

import { useCallback, useRef, useState } from "react";

import { createAudioMetadata, type ServerEvent } from "@/lib/protocol";
import { getWebSocketUrl } from "@/lib/websocket";
import type {
  ConnectionStatus,
  TranscriptPayload,
  TranscriptionMetrics,
} from "@/types/transcription";

const EMPTY_TRANSCRIPT: TranscriptPayload = {
  text: "",
  committedText: "",
  unstableText: "",
};

export function useTranscription() {
  const socketRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sequenceRef = useRef(0);
  const speechStartedAtRef = useRef<number | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [transcript, setTranscript] = useState<TranscriptPayload>(EMPTY_TRANSCRIPT);
  const [metrics, setMetrics] = useState<TranscriptionMetrics>({
    firstResultMs: null,
    currentLatencyMs: null,
    audioSeconds: 0,
  });
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback((): Promise<void> => {
    if (socketRef.current?.readyState === WebSocket.OPEN && sessionIdRef.current) {
      return Promise.resolve();
    }

    setStatus("connecting");
    setError(null);
    sequenceRef.current = 0;
    speechStartedAtRef.current = null;

    return new Promise((resolve, reject) => {
      const socket = new WebSocket(getWebSocketUrl());
      socketRef.current = socket;
      let settled = false;
      const timeout = window.setTimeout(() => {
        if (!settled) {
          settled = true;
          socket.close();
          setStatus("error");
          setError("Connection timed out");
          reject(new Error("Connection timed out"));
        }
      }, 8_000);

      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "start" }));
      };
      socket.onmessage = (message) => {
        let event: ServerEvent;
        try {
          event = JSON.parse(message.data as string) as ServerEvent;
        } catch {
          setError("Received an invalid server event");
          return;
        }

        if (event.type === "session_started") {
          sessionIdRef.current = event.session_id;
          setStatus("connected");
          if (!settled) {
            settled = true;
            window.clearTimeout(timeout);
            resolve();
          }
        } else if (event.type === "transcript") {
          const now = performance.now();
          setTranscript({
            text: event.text,
            committedText: event.committed_text,
            unstableText: event.unstable_text,
          });
          setMetrics((current) => ({
            ...current,
            firstResultMs:
              current.firstResultMs ??
              (speechStartedAtRef.current === null
                ? null
                : Math.round(now - speechStartedAtRef.current)),
            currentLatencyMs: Math.round(event.latency_ms),
          }));
        } else if (event.type === "error") {
          setError(event.message);
          if (event.fatal) {
            setStatus("error");
          }
        } else if (event.type === "session_closed") {
          sessionIdRef.current = null;
          setStatus("disconnected");
          socket.close();
        }
      };
      socket.onerror = () => {
        setStatus("error");
        setError("WebSocket connection failed");
        if (!settled) {
          settled = true;
          window.clearTimeout(timeout);
          reject(new Error("WebSocket connection failed"));
        }
      };
      socket.onclose = () => {
        socketRef.current = null;
        sessionIdRef.current = null;
        if (status !== "error") {
          setStatus("disconnected");
        }
      };
    });
  }, [status]);

  const sendAudio = useCallback((payload: ArrayBuffer, audioSeconds: number) => {
    const socket = socketRef.current;
    const sessionId = sessionIdRef.current;
    if (!socket || !sessionId || socket.readyState !== WebSocket.OPEN) return;

    if (speechStartedAtRef.current === null) {
      speechStartedAtRef.current = performance.now();
    }
    const sequence = sequenceRef.current;
    sequenceRef.current += 1;
    socket.send(JSON.stringify(createAudioMetadata(sessionId, sequence)));
    socket.send(payload);
    setMetrics((current) => ({
      ...current,
      audioSeconds: current.audioSeconds + audioSeconds,
    }));
  }, []);

  const stop = useCallback(() => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "stop" }));
    }
  }, []);

  const disconnect = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
    sessionIdRef.current = null;
    setStatus("disconnected");
  }, []);

  const reset = useCallback(() => {
    setTranscript(EMPTY_TRANSCRIPT);
    setMetrics({ firstResultMs: null, currentLatencyMs: null, audioSeconds: 0 });
    setError(null);
  }, []);

  return { connect, sendAudio, stop, disconnect, reset, status, transcript, metrics, error };
}

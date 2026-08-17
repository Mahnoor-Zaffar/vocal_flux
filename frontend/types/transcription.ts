export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

export type TranscriptPayload = {
  text: string;
  committedText: string;
  unstableText: string;
};

export type TranscriptionMetrics = {
  firstResultMs: number | null;
  currentLatencyMs: number | null;
  audioSeconds: number;
};

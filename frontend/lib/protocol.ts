export type AudioFrameMetadata = {
  type: "audio_frame";
  session_id: string;
  stream_id: string;
  sequence_number: number;
  capture_started_ms: number;
};

export type ServerEvent =
  | {
      type: "session_started";
      session_id: string;
    }
  | {
      type: "transcript";
      session_id: string;
      sequence: number;
      text: string;
      is_final: boolean;
      latency_ms: number;
      committed_text: string;
      unstable_text: string;
      stage_timings_ms: Record<string, number>;
      first_result_latency_ms: number | null;
    }
  | {
      type: "error";
      code: string;
      message: string;
      fatal: boolean;
      session_id?: string;
    }
  | {
      type: "pong";
      id?: string;
    }
  | {
      type: "session_closed";
      session_id: string;
      reason: string;
    };

export function createAudioMetadata(
  sessionId: string,
  sequenceNumber: number,
): AudioFrameMetadata {
  return {
    type: "audio_frame",
    session_id: sessionId,
    stream_id: "microphone",
    sequence_number: sequenceNumber,
    capture_started_ms: Math.round(performance.now()),
  };
}

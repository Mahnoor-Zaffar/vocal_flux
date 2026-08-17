type RecorderProps = {
  isRecording: boolean;
  audioLevel: number;
};

export function Recorder({ isRecording, audioLevel }: RecorderProps) {
  return (
    <div className="recorder-status">
      <span className={`record-led ${isRecording ? "led-live" : ""}`} aria-hidden="true" />
      <span>{isRecording ? "Microphone active" : "Microphone idle"}</span>
      <span className="level-label">{Math.round(audioLevel * 100).toString().padStart(3, "0")}%</span>
    </div>
  );
}

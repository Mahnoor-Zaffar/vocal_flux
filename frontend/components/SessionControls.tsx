type SessionControlsProps = {
  isRecording: boolean;
  isConnecting: boolean;
  onStart: () => void;
  onStop: () => void;
};

export function SessionControls({
  isRecording,
  isConnecting,
  onStart,
  onStop,
}: SessionControlsProps) {
  return (
    <div className="session-controls">
      {!isRecording ? (
        <button className="record-button" type="button" onClick={onStart} disabled={isConnecting}>
          <span className="record-icon" aria-hidden="true" />
          {isConnecting ? "Opening link…" : "Start recording"}
        </button>
      ) : (
        <button className="stop-button" type="button" onClick={onStop}>
          <span className="stop-icon" aria-hidden="true" />
          Stop recording
        </button>
      )}
      <span className="control-hint">PCM16 · 16 kHz · mono</span>
    </div>
  );
}

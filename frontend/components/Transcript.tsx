type TranscriptProps = {
  text: string;
  committedText: string;
  unstableText: string;
};

export function Transcript({ text, committedText, unstableText }: TranscriptProps) {
  const hasTranscript = Boolean(text.trim());

  return (
    <section className="transcript-panel" aria-labelledby="transcript-heading">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">Output buffer</span>
          <h2 id="transcript-heading">Transcript stream</h2>
        </div>
        <span className="live-chip">
          <span aria-hidden="true" />
          live
        </span>
      </div>
      <div className="transcript-window" aria-live="polite" aria-label="Live transcript">
        {hasTranscript ? (
          <p className="transcript-copy">
            <span>{committedText}</span>{" "}
            <span className="unstable-copy">{unstableText}</span>
          </p>
        ) : (
          <div className="transcript-empty">
            <span className="empty-mark" aria-hidden="true">+</span>
            <p>Start a session and speak naturally.</p>
            <span>Unstable hypotheses will appear here.</span>
          </div>
        )}
      </div>
      <div className="transcript-footer">
        <span>Committed text</span>
        <span className="footer-line" aria-hidden="true" />
        <span className="footer-status">{committedText ? "stable" : "waiting"}</span>
      </div>
    </section>
  );
}

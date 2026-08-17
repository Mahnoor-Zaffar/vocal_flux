import type { TranscriptionMetrics } from "@/types/transcription";

type MetricsPanelProps = {
  metrics: TranscriptionMetrics;
  audioLevel: number;
};

function metricValue(value: number | null, suffix = "") {
  return value === null ? "--" : `${value}${suffix}`;
}

export function MetricsPanel({ metrics, audioLevel }: MetricsPanelProps) {
  return (
    <section className="metrics-panel" aria-labelledby="metrics-heading">
      <div className="panel-heading compact-heading">
        <div>
          <span className="section-kicker">Telemetry</span>
          <h2 id="metrics-heading">Run metrics</h2>
        </div>
        <div className="signal-meter" aria-label={`Audio level ${Math.round(audioLevel * 100)} percent`}>
          {Array.from({ length: 8 }, (_, index) => (
            <span key={index} className={audioLevel * 8 > index ? "signal-on" : ""} />
          ))}
        </div>
      </div>
      <div className="metric-grid">
        <div className="metric-cell">
          <span>First result</span>
          <strong>{metricValue(metrics.firstResultMs, " ms")}</strong>
        </div>
        <div className="metric-cell">
          <span>Inference</span>
          <strong>{metricValue(metrics.currentLatencyMs, " ms")}</strong>
        </div>
        <div className="metric-cell">
          <span>RTF</span>
          <strong>--</strong>
        </div>
        <div className="metric-cell">
          <span>Audio stream</span>
          <strong>{metrics.audioSeconds.toFixed(1)} s</strong>
        </div>
      </div>
    </section>
  );
}

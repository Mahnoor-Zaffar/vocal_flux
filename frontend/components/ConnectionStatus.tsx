import type { ConnectionStatus as ConnectionStatusValue } from "@/types/transcription";

type ConnectionStatusProps = {
  status: ConnectionStatusValue;
};

const labels: Record<ConnectionStatusValue, string> = {
  disconnected: "Standby",
  connecting: "Synchronizing",
  connected: "Live link",
  error: "Link fault",
};

export function ConnectionStatus({ status }: ConnectionStatusProps) {
  return (
    <div className={`connection-status status-${status}`} aria-live="polite">
      <span className="status-dot" aria-hidden="true" />
      <span>{labels[status]}</span>
    </div>
  );
}

type AudioVisualizerProps = {
  level: number;
  active: boolean;
};

export function AudioVisualizer({ level, active }: AudioVisualizerProps) {
  return (
    <div className={`wave-strip ${active ? "wave-active" : ""}`} aria-hidden="true">
      {Array.from({ length: 28 }, (_, index) => {
        const shape = 0.25 + Math.abs(Math.sin(index * 1.7)) * 0.75;
        const height = active ? Math.max(4, level * shape * 42) : 4;
        return <i key={index} style={{ height: `${height}px` }} />;
      })}
    </div>
  );
}

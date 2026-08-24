const BARS = 24;

interface Props {
  /** Peak amplitude, 0..1 */
  level: number;
  active: boolean;
}

export function LevelMeter({ level, active }: Props) {
  // Perceptual scaling — raw amplitude looks dead for normal speech.
  const scaled = active ? Math.min(1, Math.sqrt(level) * 1.4) : 0;
  const lit = Math.round(scaled * BARS);

  return (
    <div
      className="level-meter"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={Number(scaled.toFixed(2))}
      aria-label="Microphone input level"
    >
      {Array.from({ length: BARS }, (_, i) => (
        <span
          key={i}
          className={`level-bar ${i < lit ? "lit" : ""} ${
            i > BARS * 0.85 ? "hot" : ""
          }`}
        />
      ))}
    </div>
  );
}

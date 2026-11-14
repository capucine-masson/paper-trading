export type Tone = "up" | "flat" | "down";

interface Props {
  value: number;
  min: number;
  max: number;
  bandLow: number;
  bandHigh: number;
  tone: Tone;
  text: string;
}

const percentOf = (value: number, min: number, max: number): number =>
  (Math.min(Math.max(value, min), max) - min) / (max - min) * 100;

/** A dot on a fixed axis with a grey reference band; the number stays next to it. */
export function DotPlot({ value, min, max, bandLow, bandHigh, tone, text }: Props) {
  const start = percentOf(bandLow, min, max);
  return (
    <span className="dotplot">
      <span className="dot-track">
        <span className="dot-band" style={{ left: `${start}%`, width: `${percentOf(bandHigh, min, max) - start}%` }} />
        <span className={`dot dot-${tone}`} style={{ left: `${percentOf(value, min, max)}%` }} />
      </span>
      <span className={`num dot-text ${tone}`}>{text}</span>
    </span>
  );
}

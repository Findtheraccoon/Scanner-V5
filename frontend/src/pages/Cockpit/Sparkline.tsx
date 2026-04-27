import type { SparklineGradient } from "./data";

interface SparklineProps {
  data: SparklineGradient;
}

export function Sparkline({ data }: SparklineProps) {
  return (
    <svg viewBox="0 0 320 50" preserveAspectRatio="none" aria-hidden="true">
      <title>spark</title>
      <defs>
        <linearGradient id={data.id} x1="0" y1="0" x2="0" y2="1">
          {data.fillStops.map((s) => (
            <stop key={s.offset} offset={s.offset} stopColor={s.color} stopOpacity={s.opacity} />
          ))}
        </linearGradient>
        <linearGradient id={`${data.id}-stroke`} x1="0" y1="0" x2="1" y2="0">
          {data.strokeStops.map((s) => (
            <stop key={s.offset} offset={s.offset} stopColor={s.color} stopOpacity={s.opacity} />
          ))}
        </linearGradient>
      </defs>
      <path d={data.fillPath} fill={`url(#${data.id})`} />
      <path
        d={data.strokePath}
        fill="none"
        stroke={`url(#${data.id}-stroke)`}
        strokeWidth={data.strokeWidth}
      />
    </svg>
  );
}

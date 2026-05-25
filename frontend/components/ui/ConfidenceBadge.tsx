import clsx from "clsx";

interface Props { confidence: number; needsReview?: boolean }

export default function ConfidenceBadge({ confidence, needsReview }: Props) {
  const pct = Math.round(confidence * 100);
  const color = confidence >= 0.72
    ? "bg-green-100 text-green-700"
    : confidence >= 0.5
    ? "bg-yellow-100 text-yellow-700"
    : "bg-red-100 text-red-700";

  return (
    <span className={clsx("inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium", color)}>
      {needsReview ? "⚠ 建议人工确认" : `置信度 ${pct}%`}
    </span>
  );
}

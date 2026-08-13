export function StarBadge({ rating }: { rating: number }) {
  const stars = "★".repeat(Math.max(0, Math.min(5, rating)));
  const tone =
    rating >= 5
      ? "text-amber-300"
      : rating === 4
        ? "text-emerald-300"
        : "text-slate-400";
  return (
    <span className={`font-bold tabular-nums ${tone}`} title={`${rating}/5`}>
      {stars || "—"}
    </span>
  );
}

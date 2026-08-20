"use client";

/** Proper on/off toggle used for every boolean filter (incl. EP features). */
export function Switch({
  checked,
  onChange,
  disabled,
  label,
  size = "md",
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  label?: string;
  size?: "sm" | "md";
}) {
  const track = size === "sm" ? "h-4 w-7" : "h-5 w-9";
  const knob = size === "sm" ? "h-3 w-3" : "h-4 w-4";
  const travel = size === "sm" ? "translate-x-[14px]" : "translate-x-[18px]";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex shrink-0 items-center rounded-full border transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400/50 disabled:cursor-not-allowed disabled:opacity-40 ${track} ${
        checked ? "border-accent-500/60 bg-accent-600" : "border-ink-600 bg-ink-800"
      }`}
    >
      <span
        className={`pointer-events-none inline-block rounded-full bg-white shadow transition-transform duration-150 ${knob} ${
          checked ? travel : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

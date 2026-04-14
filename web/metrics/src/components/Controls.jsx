/**
 * Slider — labelled range input with mono value readout.
 */
export function Slider({ label, min, max, value, onChange, suffix = "" }) {
  return (
    <label className="text-[13px] text-[var(--text-secondary)] font-medium flex items-center gap-2">
      {label}
      <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-32" />
      <span className="font-mono text-[var(--text-primary)] font-semibold">
        {value}{suffix}
      </span>
    </label>
  );
}

/**
 * ChipGroup — row of mutually exclusive chip buttons.
 */
export function ChipGroup({ options, value, onChange }) {
  return (
    <div className="flex gap-1">
      {options.map((opt) => {
        const key = typeof opt === "object" ? opt.value : opt;
        const label = typeof opt === "object" ? opt.label : String(opt);
        return (
          <button key={key} onClick={() => onChange(key)} className={`chip ${value === key ? "active" : ""}`}>
            {label}
          </button>
        );
      })}
    </div>
  );
}

interface Option<T extends string> { value: T; label: string }

interface SegmentedProps<T extends string> {
  label: string;
  value: T;
  options: readonly Option<T>[];
  onChange: (value: T) => void;
}

export function Segmented<T extends string>({ label, value, options, onChange }: SegmentedProps<T>) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-[9px] border border-line bg-[#0c111b] p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className="rounded-[7px] px-2.5 py-1 text-xs text-muted transition-colors hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-system aria-pressed:bg-[#1d2638] aria-pressed:text-ink"
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

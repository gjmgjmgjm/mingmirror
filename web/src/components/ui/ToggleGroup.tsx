import type { ReactNode } from "react";

interface ToggleOption<T extends string> {
  value: T;
  label: ReactNode;
}

interface ToggleGroupProps<T extends string> {
  options: ToggleOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}

export default function ToggleGroup<T extends string>({
  options,
  value,
  onChange,
  className = "",
}: ToggleGroupProps<T>) {
  return (
    <div
      className={`inline-flex rounded-xl border border-ink-300/40 bg-ink-100/50 p-1 dark:border-ink-500/40 dark:bg-ink-800/50 ${className}`}
    >
      {options.map((option) => {
        const selected = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`rounded-lg px-4 py-1.5 text-sm transition ${
              selected
                ? "bg-white text-ink-800 shadow-sm dark:bg-ink-700 dark:text-ink-100"
                : "text-ink-500 hover:bg-ink-200/60 dark:text-ink-400 dark:hover:bg-ink-700/60"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

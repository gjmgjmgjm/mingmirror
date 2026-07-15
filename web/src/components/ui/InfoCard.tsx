import TermTooltip from "../TermTooltip";

interface InfoCardProps {
  label: string;
  value: string;
  delay?: number;
  className?: string;
  term?: string;
}

export default function InfoCard({
  label,
  value,
  delay = 0,
  className = "",
  term,
}: InfoCardProps) {
  return (
    <div
      className={`info-card animate-chart-card ${className}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="block text-xs text-ink-500 dark:text-ink-400">
        {term ? (
          <TermTooltip term={term}>{label}</TermTooltip>
        ) : (
          label
        )}
      </span>
      <span className="block font-medium text-ink-700 dark:text-ink-200">
        {value || "—"}
      </span>
    </div>
  );
}

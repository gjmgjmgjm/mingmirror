interface DomainCardProps {
  title: string;
  text: string;
  delay?: number;
  className?: string;
}

export default function DomainCard({
  title,
  text,
  delay = 0,
  className = "",
}: DomainCardProps) {
  return (
    <div
      className={`domain-card animate-chart-card ${className}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="text-sm font-medium text-vermilion">{title}</span>
      <span className="text-ink-700 dark:text-ink-200">{text}</span>
    </div>
  );
}

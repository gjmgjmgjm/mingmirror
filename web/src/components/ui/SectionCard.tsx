import type { ReactNode } from "react";

interface SectionCardProps {
  children: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  className?: string;
  bodyClassName?: string;
  borderLeft?: "vermilion" | "gold" | "jade" | "ink";
  delay?: number;
}

const borderLeftClasses: Record<string, string> = {
  vermilion: "border-l-4 border-l-vermilion",
  gold: "border-l-4 border-l-gold",
  jade: "border-l-4 border-l-jade",
  ink: "border-l-4 border-l-ink-300 dark:border-l-ink-600",
};

export default function SectionCard({
  children,
  title,
  subtitle,
  icon,
  className = "",
  bodyClassName = "",
  borderLeft,
  delay = 0,
}: SectionCardProps) {
  return (
    <section
      className={`panel p-6 animate-chart-section ${borderLeft ? borderLeftClasses[borderLeft] : ""} ${className}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      {(title || subtitle) && (
        <div className="mb-4">
          {title && (
            <h2 className="section-title flex items-center gap-2">
              {icon}
              {title}
            </h2>
          )}
          {subtitle && <p className="section-subtitle mt-1">{subtitle}</p>}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

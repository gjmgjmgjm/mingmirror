import type { ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="panel mx-auto max-w-2xl p-8 text-center md:p-16">
      {icon && (
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-vermilion/10 text-vermilion dark:bg-vermilion/20">
          {icon}
        </div>
      )}
      <h2 className="mb-4 font-display text-3xl text-ink-800 dark:text-ink-100 md:text-4xl">
        {title}
      </h2>
      {description && (
        <p className="mx-auto mb-6 max-w-xl text-ink-600 dark:text-ink-300">
          {description}
        </p>
      )}
      {action && <div className="flex justify-center">{action}</div>}
    </div>
  );
}

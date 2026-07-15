interface CloudDividerProps {
  className?: string;
  variant?: "vermilion" | "gold" | "ink";
}

const variantClasses = {
  vermilion: "text-vermilion/30",
  gold: "text-gold/30",
  ink: "text-ink-400/30 dark:text-ink-500/30",
};

export default function CloudDivider({
  className = "",
  variant = "ink",
}: CloudDividerProps) {
  return (
    <div className={`flex items-center gap-3 py-4 ${className}`} aria-hidden="true">
      <div className={`h-px flex-1 ${variantClasses[variant]}`}>
        <svg className="h-full w-full" preserveAspectRatio="none">
          <defs>
            <pattern id={`cloud-left-${variant}`} width="40" height="8" patternUnits="userSpaceOnUse">
              <path
                d="M0 4 Q5 0 10 4 T20 4 T30 4 T40 4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill={`url(#cloud-left-${variant})`} />
        </svg>
      </div>
      <svg
        className={`h-5 w-8 ${variantClasses[variant]}`}
        viewBox="0 0 32 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      >
        <path d="M4 14 Q8 6 16 10 Q24 6 28 14" />
        <circle cx="10" cy="12" r="2" fill="currentColor" />
        <circle cx="22" cy="12" r="2" fill="currentColor" />
      </svg>
      <div className={`h-px flex-1 ${variantClasses[variant]}`}>
        <svg className="h-full w-full" preserveAspectRatio="none">
          <defs>
            <pattern id={`cloud-right-${variant}`} width="40" height="8" patternUnits="userSpaceOnUse">
              <path
                d="M0 4 Q5 0 10 4 T20 4 T30 4 T40 4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill={`url(#cloud-right-${variant})`} />
        </svg>
      </div>
    </div>
  );
}

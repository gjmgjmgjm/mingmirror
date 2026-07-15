import { useState, useRef, type ReactNode } from "react";

interface TooltipProps {
  children: ReactNode;
  content: ReactNode;
  position?: "top" | "bottom" | "left" | "right";
}

export default function Tooltip({
  children,
  content,
  position = "top",
}: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setVisible(true), 200);
  };

  const hide = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setVisible(false), 100);
  };

  const positionClasses = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
    left: "right-full top-1/2 -translate-y-1/2 mr-2",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  };

  const arrowClasses = {
    top: "top-full left-1/2 -translate-x-1/2 border-t-ink-700 dark:border-t-ink-200",
    bottom: "bottom-full left-1/2 -translate-x-1/2 border-b-ink-700 dark:border-b-ink-200",
    left: "left-full top-1/2 -translate-y-1/2 border-l-ink-700 dark:border-l-ink-200",
    right: "right-full top-1/2 -translate-y-1/2 border-r-ink-700 dark:border-r-ink-200",
  };

  return (
    <span
      className="relative inline-flex cursor-help items-center"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      {visible && (
        <span
          className={`pointer-events-none absolute z-50 w-64 rounded-lg border border-ink-300/10 bg-ink-700 px-3 py-2 text-xs leading-relaxed text-ink-100 shadow-xl dark:bg-ink-200 dark:text-ink-800 ${positionClasses[position]}`}
          role="tooltip"
        >
          {content}
          <span
            className={`absolute h-0 w-0 border-4 border-transparent ${arrowClasses[position]}`}
          />
        </span>
      )}
    </span>
  );
}

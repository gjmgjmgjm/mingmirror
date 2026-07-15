import { useEffect, useRef, useState } from "react";

interface WheelPickerProps {
  options: string[];
  value: string;
  onChange: (value: string) => void;
  label?: string;
  disabled?: boolean;
  placeholder?: string;
  visibleItems?: 3 | 5 | 7;
}

const ITEM_HEIGHT = 44;

export default function WheelPicker({
  options,
  value,
  onChange,
  label,
  disabled = false,
  placeholder,
  visibleItems = 5,
}: WheelPickerProps) {
  const VISIBLE_ITEMS = visibleItems;
  const CONTAINER_HEIGHT = ITEM_HEIGHT * VISIBLE_ITEMS;
  const CENTER_OFFSET = Math.floor(VISIBLE_ITEMS / 2) * ITEM_HEIGHT;
  const containerRef = useRef<HTMLDivElement>(null);
  const isProgrammaticScroll = useRef(false);
  const bumpTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const settleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wheelAccumulator = useRef(0);
  const wheelResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [bumped, setBumped] = useState(false);

  const selectedIndex = value ? options.indexOf(value) : -1;
  const hasValue = selectedIndex >= 0;

  useEffect(() => {
    if (!hasValue) return;
    setBumped(true);
    if (bumpTimer.current) clearTimeout(bumpTimer.current);
    bumpTimer.current = setTimeout(() => setBumped(false), 220);
    return () => {
      if (bumpTimer.current) clearTimeout(bumpTimer.current);
    };
  }, [value, hasValue]);

  const scrollToIndex = (index: number, behavior: ScrollBehavior = "auto") => {
    if (!containerRef.current) return;
    isProgrammaticScroll.current = true;
    containerRef.current.scrollTo({
      top: index * ITEM_HEIGHT,
      behavior,
    });
    // Reset flag after scroll animation completes for smooth behavior.
    window.setTimeout(() => {
      isProgrammaticScroll.current = false;
    }, behavior === "smooth" ? 250 : 0);
  };

  useEffect(() => {
    if (!containerRef.current || isDragging || !hasValue) return;
    scrollToIndex(selectedIndex, "auto");
  }, [selectedIndex, isDragging, hasValue]);

  const settleToIndex = (index: number) => {
    if (!containerRef.current || disabled) return;
    const clamped = Math.max(0, Math.min(index, options.length - 1));
    const nextValue = options[clamped];
    scrollToIndex(clamped, "smooth");
    if (nextValue !== value) {
      onChange(nextValue);
    }
  };

  const requestSettle = () => {
    if (!containerRef.current) return;
    if (settleTimer.current) clearTimeout(settleTimer.current);
    settleTimer.current = setTimeout(() => {
      if (!containerRef.current) return;
      const index = Math.round(containerRef.current.scrollTop / ITEM_HEIGHT);
      settleToIndex(index);
    }, 120);
  };

  const handleScroll = () => {
    if (!containerRef.current || isProgrammaticScroll.current) return;
    requestSettle();
  };

  const handleScrollEnd = () => {
    if (!containerRef.current || isProgrammaticScroll.current) return;
    if (settleTimer.current) clearTimeout(settleTimer.current);
    const index = Math.round(containerRef.current.scrollTop / ITEM_HEIGHT);
    settleToIndex(index);
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    if (!containerRef.current || disabled) return;

    // Accumulate wheel delta and only step once per item-height threshold.
    // This prevents a single trackpad/mouse wheel flick from jumping multiple items.
    wheelAccumulator.current += e.deltaY;

    if (wheelResetTimer.current) clearTimeout(wheelResetTimer.current);
    wheelResetTimer.current = setTimeout(() => {
      wheelAccumulator.current = 0;
    }, 150);

    const threshold = ITEM_HEIGHT * 0.65;
    if (Math.abs(wheelAccumulator.current) < threshold) return;

    const steps = Math.floor(Math.abs(wheelAccumulator.current) / threshold);
    const direction = wheelAccumulator.current > 0 ? 1 : -1;
    wheelAccumulator.current = 0;

    const currentIndex = Math.round(containerRef.current.scrollTop / ITEM_HEIGHT);
    settleToIndex(currentIndex + steps * direction);
  };

  const handleInteractionStart = () => setIsDragging(true);
  const handleInteractionEnd = () => {
    setIsDragging(false);
    handleScrollEnd();
  };

  return (
    <div
      className={`relative flex-1 overflow-hidden rounded-2xl border border-ink-300/30 bg-white/60 shadow-inner backdrop-blur-sm transition dark:border-ink-500/30 dark:bg-ink-800/60 ${
        disabled ? "opacity-50" : ""
      } ${isDragging ? "cursor-grabbing" : "cursor-grab"}`}
      style={{ height: CONTAINER_HEIGHT }}
      aria-label={label ? `${label} 滚轮选择器` : undefined}
    >
      {label && (
        <div className="pointer-events-none absolute right-3 top-1/2 z-30 -translate-y-1/2 text-xs font-bold tracking-widest text-ink-400 dark:text-ink-500">
          {label}
        </div>
      )}

      <div
        ref={containerRef}
        onScroll={handleScroll}
        onScrollCapture={handleScroll}
        onWheel={handleWheel}
        onMouseDown={handleInteractionStart}
        onMouseUp={handleInteractionEnd}
        onMouseLeave={handleInteractionEnd}
        onTouchStart={handleInteractionStart}
        onTouchEnd={handleInteractionEnd}
        className="wheel-picker-scroll h-full overflow-y-auto"
        style={{
          scrollSnapType: "y mandatory",
          scrollbarWidth: "none",
          msOverflowStyle: "none",
          paddingTop: CENTER_OFFSET,
          paddingBottom: CENTER_OFFSET,
        }}
      >
        {options.map((option, idx) => {
          const isSelected = option === value;
          return (
            <button
              key={option}
              type="button"
              disabled={disabled}
              onClick={() => settleToIndex(idx)}
              style={{
                height: ITEM_HEIGHT,
                scrollSnapAlign: "center",
                textShadow: isSelected ? "0 0 10px rgba(201,54,29,0.25)" : undefined,
              }}
              className={`flex w-full items-center justify-center text-base font-medium transition-all duration-200 ${
                isSelected
                  ? `scale-110 font-semibold text-vermilion drop-shadow-sm ${bumped ? "animate-picker-bump" : ""}`
                  : "text-ink-400/70 dark:text-ink-500/70"
              } ${!hasValue ? "opacity-40" : ""}`}
            >
              {option}
            </button>
          );
        })}
      </div>

      {/* Center selection rail */}
      <div
        className="pointer-events-none absolute inset-x-0 z-0"
        style={{
          top: CENTER_OFFSET - 1,
          height: ITEM_HEIGHT + 2,
        }}
      >
        <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-vermilion/60 to-transparent" />
        <div className="absolute inset-x-6 bottom-0 h-px bg-gradient-to-r from-transparent via-vermilion/60 to-transparent" />
        <div className="absolute inset-0 overflow-hidden rounded-xl bg-vermilion/[0.08] shadow-[inset_0_0_16px_rgba(201,54,29,0.08)] dark:bg-vermilion/[0.14] dark:shadow-[inset_0_0_20px_rgba(201,54,29,0.12)]">
          <div className="animate-rail-shimmer absolute inset-0 opacity-60" />
        </div>
      </div>

      {/* Placeholder overlay */}
      {!hasValue && placeholder && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center">
          <span className="rounded-lg bg-white/95 px-4 py-1.5 text-sm font-medium text-ink-500 shadow-sm dark:bg-ink-800/95 dark:text-ink-400">
            {placeholder}
          </span>
        </div>
      )}

      {/* Fade masks */}
      <div
        className="wheel-picker-fade-top pointer-events-none absolute inset-x-0 top-0 z-10"
        style={{ height: CENTER_OFFSET }}
      />
      <div
        className="wheel-picker-fade-bottom pointer-events-none absolute inset-x-0 bottom-0 z-10"
        style={{ height: CENTER_OFFSET }}
      />

      <style>{`
        .wheel-picker-scroll::-webkit-scrollbar {
          display: none;
        }
        .wheel-picker-fade-top {
          background: linear-gradient(to bottom, rgba(255, 255, 255, 0.98), rgba(255, 255, 255, 0.2));
        }
        .wheel-picker-fade-bottom {
          background: linear-gradient(to top, rgba(255, 255, 255, 0.98), rgba(255, 255, 255, 0.2));
        }
        .dark .wheel-picker-fade-top {
          background: linear-gradient(to bottom, rgba(30, 32, 38, 0.98), rgba(30, 32, 38, 0.2));
        }
        .dark .wheel-picker-fade-bottom {
          background: linear-gradient(to top, rgba(30, 32, 38, 0.98), rgba(30, 32, 38, 0.2));
        }
        @media (prefers-color-scheme: dark) {
          .wheel-picker-fade-top {
            background: linear-gradient(to bottom, rgba(30, 32, 38, 0.98), rgba(30, 32, 38, 0.2));
          }
          .wheel-picker-fade-bottom {
            background: linear-gradient(to top, rgba(30, 32, 38, 0.98), rgba(30, 32, 38, 0.2));
          }
        }
        @keyframes picker-bump {
          0% { transform: scale(1.1); }
          45% { transform: scale(1.28); filter: brightness(1.2); }
          100% { transform: scale(1.1); }
        }
        .animate-picker-bump {
          animation: picker-bump 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        @keyframes rail-shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
        .animate-rail-shimmer {
          background: linear-gradient(
            90deg,
            transparent,
            rgba(201, 54, 29, 0.18),
            rgba(201, 162, 39, 0.18),
            transparent
          );
          animation: rail-shimmer 2.4s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}

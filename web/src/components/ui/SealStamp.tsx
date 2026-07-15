import type { ReactNode } from "react";

interface SealStampProps {
  children: ReactNode;
  size?: "sm" | "md" | "lg";
  variant?: "vermilion" | "gold" | "jade";
  className?: string;
}

const sizeClasses = {
  sm: "h-10 w-10 text-[10px] border-2",
  md: "h-14 w-14 text-xs border-[3px]",
  lg: "h-20 w-20 text-sm border-4",
};

const variantClasses = {
  vermilion: "border-vermilion/80 text-vermilion bg-vermilion/5",
  gold: "border-gold/80 text-gold bg-gold/5",
  jade: "border-jade/80 text-jade bg-jade/5",
};

export default function SealStamp({
  children,
  size = "md",
  variant = "vermilion",
  className = "",
}: SealStampProps) {
  return (
    <div
      className={`inline-flex items-center justify-center rounded-lg font-display font-bold leading-none ${sizeClasses[size]} ${variantClasses[variant]} ${className}`}
      style={{ writingMode: "vertical-rl", textOrientation: "upright" }}
    >
      {children}
    </div>
  );
}

import { HelpCircle } from "lucide-react";
import { Tooltip } from "./ui";
import { explainTerm } from "../lib/terms";

interface TermTooltipProps {
  term: string;
  children?: React.ReactNode;
}

export default function TermTooltip({ term, children }: TermTooltipProps) {
  const explanation = explainTerm(term);
  if (!explanation) {
    return <>{children ?? term}</>;
  }

  return (
    <Tooltip content={explanation}>
      <span className="inline-flex items-center gap-0.5 border-b border-dashed border-vermilion/40 text-ink-700 transition hover:border-vermilion hover:text-vermilion dark:text-ink-200 dark:hover:text-vermilion-light">
        {children ?? term}
        <HelpCircle className="h-3 w-3 opacity-60" />
      </span>
    </Tooltip>
  );
}

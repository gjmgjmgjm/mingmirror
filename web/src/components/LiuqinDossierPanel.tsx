import type { LiuqinDossier, LiuqinMemberDossier } from "../api/client";
import { SectionCard } from "./ui";

const ORDER: Array<keyof NonNullable<LiuqinDossier["members"]>> = [
  "father",
  "mother",
  "spouse",
  "son",
  "daughter",
  "brother",
  "sister",
];

function StrengthPill({ strength }: { strength?: string }) {
  const strong = strength === "强";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
        strong
          ? "bg-jade/15 text-jade"
          : "bg-ink-200/70 text-ink-600 dark:bg-ink-700 dark:text-ink-300"
      }`}
    >
      {strength || "—"}
    </span>
  );
}

function MemberCard({
  m,
  highlightYears,
}: {
  m: LiuqinMemberDossier;
  highlightYears?: Set<number>;
}) {
  const timing = m.timing || {};
  const highs = timing.dayun_highlights || [];
  const liunian = timing.liunian_samples || [];
  const palace = m.palace || {};
  const hi = highlightYears || new Set<number>();
  return (
    <div className="rounded-xl border border-ink-200/50 bg-ink-50/40 p-4 dark:border-ink-600/40 dark:bg-ink-900/30">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-ink-800 dark:text-ink-100">
          {m.label}
        </h3>
        <span className="text-sm text-ink-500 dark:text-ink-400">
          {m.star || "—"}
        </span>
        <StrengthPill strength={m.strength} />
        {!m.exists && (
          <span className="text-xs text-ink-400">原局不显</span>
        )}
        {m.dual_star_note ? (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">
            双星合参
          </span>
        ) : null}
      </div>
      <dl className="space-y-1.5 text-sm text-ink-700 dark:text-ink-200">
        {m.dual_star_note ? (
          <div>
            <dt className="inline font-medium text-ink-500 dark:text-ink-400">
              双星：
            </dt>
            <dd className="inline">{m.dual_star_note}</dd>
          </div>
        ) : null}
        {palace.palace_note ? (
          <div>
            <dt className="inline font-medium text-ink-500 dark:text-ink-400">
              宫位：
            </dt>
            <dd className="inline">{palace.palace_note}</dd>
          </div>
        ) : null}
        <div>
          <dt className="inline font-medium text-ink-500 dark:text-ink-400">
            性格：
          </dt>
          <dd className="inline">{m.character || "—"}</dd>
        </div>
        <div>
          <dt className="inline font-medium text-ink-500 dark:text-ink-400">
            能力：
          </dt>
          <dd className="inline">{m.ability || "—"}</dd>
        </div>
        <div>
          <dt className="inline font-medium text-ink-500 dark:text-ink-400">
            健康线索：
          </dt>
          <dd className="inline">{m.health || "—"}</dd>
        </div>
        {m.appearance ? (
          <div>
            <dt className="inline font-medium text-ink-500 dark:text-ink-400">
              外貌气质：
            </dt>
            <dd className="inline">{m.appearance}</dd>
          </div>
        ) : null}
        <div>
          <dt className="inline font-medium text-ink-500 dark:text-ink-400">
            与命主：
          </dt>
          <dd className="inline">{m.relation || "—"}</dd>
        </div>
        <div>
          <dt className="inline font-medium text-ink-500 dark:text-ink-400">
            应期提要：
          </dt>
          <dd className="inline">{timing.favorable_hint || "—"}</dd>
        </div>
        {timing.caution_hint ? (
          <div>
            <dt className="inline font-medium text-ink-500 dark:text-ink-400">
              留意：
            </dt>
            <dd className="inline text-ink-600 dark:text-ink-300">
              {timing.caution_hint}
            </dd>
          </div>
        ) : null}
      </dl>
      {highs.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-xs font-medium text-ink-500 dark:text-ink-400">
            大运引动
          </p>
          <div className="flex flex-wrap gap-2">
            {highs.map((h, i) => (
              <span
                key={i}
                className="rounded-lg bg-jade/10 px-2.5 py-1 text-xs text-ink-700 dark:bg-jade/15 dark:text-ink-200"
                title={h.note}
              >
                <span className="font-semibold text-jade">
                  {h.ages} {h.pillar}
                </span>
                <span className="ml-1 text-ink-500 dark:text-ink-400">
                  {h.note}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}
      {liunian.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-xs font-medium text-ink-500 dark:text-ink-400">
            流年象征取样
            <span className="ml-1 font-normal text-ink-400">（非断言）</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {liunian.map((x, i) => {
              const hit = x.year != null && hi.has(Number(x.year));
              return (
                <span
                  key={i}
                  className={`rounded-lg px-2.5 py-1 text-xs text-ink-700 dark:text-ink-200 ${
                    hit
                      ? "bg-jade/15 ring-1 ring-jade/40 dark:bg-jade/20"
                      : "bg-amber-500/10 dark:bg-amber-500/15"
                  }`}
                  title={x.note}
                >
                  <span
                    className={`font-semibold ${
                      hit
                        ? "text-jade"
                        : "text-amber-700 dark:text-amber-300"
                    }`}
                  >
                    {x.year}年 {x.pillar}
                  </span>
                  {x.age != null && (
                    <span className="ml-1 text-ink-400">约{x.age}岁</span>
                  )}
                  {hit && (
                    <span className="ml-1 text-jade">· 应期重合</span>
                  )}
                  <span className="ml-1 text-ink-500 dark:text-ink-400">
                    {x.note}
                  </span>
                </span>
              );
            })}
          </div>
        </div>
      )}
      {m.honesty && (
        <p className="mt-2 text-[11px] leading-relaxed text-ink-400">
          {m.honesty}
        </p>
      )}
    </div>
  );
}

export default function LiuqinDossierPanel({
  dossier,
  delay = 140,
  highlightYears,
}: {
  dossier?: LiuqinDossier | null;
  delay?: number;
  /** Years from year_timing_surface to highlight as 应期重合 */
  highlightYears?: number[];
}) {
  if (!dossier?.members) return null;
  const members = dossier.members;
  const hi = new Set(
    (highlightYears || []).map((y) => Number(y)).filter((y) => !Number.isNaN(y))
  );

  return (
    <SectionCard
      title={
        <span className="inline-flex items-center gap-2">
          六亲细断
          <span className="rounded-full bg-jade/15 px-2 py-0.5 text-xs font-medium text-jade">
            结构层
          </span>
          {hi.size > 0 ? (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">
              应期联动
            </span>
          ) : null}
        </span>
      }
      delay={delay}
    >
      {dossier.children_bias && (
        <p className="mb-3 text-sm text-ink-600 dark:text-ink-300">
          <span className="font-medium">子女星偏向：</span>
          {dossier.children_bias}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-1 lg:grid-cols-2">
        {ORDER.map((key) => {
          const m = members[key];
          if (!m) return null;
          return <MemberCard key={key} m={m} highlightYears={hi} />;
        })}
      </div>
      {dossier.disclaimer && (
        <p className="mt-4 text-xs leading-relaxed text-ink-500 dark:text-ink-400">
          {dossier.disclaimer}
        </p>
      )}
    </SectionCard>
  );
}

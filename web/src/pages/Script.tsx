import { useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, Sparkles, Sword, Shield, Map } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import { fetchDestinyScript, type DestinyScriptResponse } from "../api/client";
import ChartLoader from "../components/ChartLoader";
import { SectionCard, EmptyState, PageHeader, ErrorPanel } from "../components/ui";

function parseBirthYear(birthDate?: string): number {
  if (!birthDate) return 1990;
  const year = parseInt(birthDate.split("-")[0], 10);
  return Number.isNaN(year) ? 1990 : year;
}

function buildBirthDatetime(chart: NonNullable<ReturnType<typeof useChart>["chart"]>) {
  if (!chart.birthDate) return undefined;
  const time = chart.birthTime || "00:00";
  return `${chart.birthDate}T${time}:00`;
}

export default function Script() {
  const { chart } = useChart();
  const [script, setScript] = useState<DestinyScriptResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    if (!chart) return;
    setLoading(true);
    setError(null);
    setScript(null);
    try {
      const data = await fetchDestinyScript({
        bazi: chart.bazi,
        gender: chart.gender || undefined,
        birth_datetime: buildBirthDatetime(chart),
        birth_year: parseBirthYear(chart.birthDate),
      });
      setScript(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "生成失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  if (!chart) {
    return (
      <EmptyState
        title="暂无命盘"
        description="请先在首页输入八字信息，然后再生成命运剧本。"
        action={
          <Link to="/" className="btn-primary inline-flex">
            前往首页
          </Link>
        }
      />
    );
  }

  const card = script?.character_card;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="命运剧本"
        subtitle="把你的八字变成一份人生 RPG 攻略"
      />
      <SectionCard>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={loading}
          className="btn-primary btn-shimmer disabled:cursor-not-allowed"
        >
          {loading ? (
            <>
              <span className="relative mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              <span className="relative">生成剧本中</span>
            </>
          ) : (
            <>
              <Sparkles className="relative mr-2 h-4 w-4" />
              <span className="relative">生成命运剧本</span>
            </>
          )}
        </button>
      </SectionCard>

      {loading && <ChartLoader />}

      {error && <ErrorPanel title="生成出错">{error}</ErrorPanel>}

      {script && (
        <div className="space-y-6">
          {script.opening && (
            <SectionCard delay={0}>
              <p className="text-lg leading-relaxed text-ink-700 dark:text-ink-200">
                “{script.opening}”
              </p>
            </SectionCard>
          )}

          {card && (
            <SectionCard
              title="角色卡"
              icon={<BookOpen className="h-5 w-5 text-vermilion" />}
              delay={100}
            >
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40">
                  <div className="text-xs text-ink-500 dark:text-ink-400">日主</div>
                  <div className="text-lg font-semibold text-ink-800 dark:text-ink-100">
                    {card.day_master || "未知"}
                  </div>
                </div>
                <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40">
                  <div className="text-xs text-ink-500 dark:text-ink-400">格局</div>
                  <div className="text-lg font-semibold text-ink-800 dark:text-ink-100">
                    {card.pattern || "未知"}
                  </div>
                </div>
                <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40">
                  <div className="text-xs text-ink-500 dark:text-ink-400">身强身弱</div>
                  <div className="text-lg font-semibold text-ink-800 dark:text-ink-100">
                    {card.strength || "未知"}
                  </div>
                </div>
                <div className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40">
                  <div className="text-xs text-ink-500 dark:text-ink-400">当前章节</div>
                  <div className="text-base font-semibold text-ink-800 dark:text-ink-100">
                    {card.current_chapter || "未知"}
                  </div>
                </div>
              </div>

              <div className="mt-6 grid gap-6 md:grid-cols-2">
                <div>
                  <h3 className="mb-3 flex items-center gap-2 font-medium text-ink-700 dark:text-ink-200">
                    <Sword className="h-4 w-4 text-gold" />
                    天赋技能
                  </h3>
                  <div className="space-y-3">
                    {card.talents?.map((t, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-gold/20 bg-gold/5 p-3 dark:bg-gold/10"
                      >
                        <div className="font-medium text-ink-800 dark:text-ink-100">
                          {t.name}
                        </div>
                        <div className="text-sm text-ink-600 dark:text-ink-300">
                          {t.description}
                        </div>
                      </div>
                    ))}
                    {(!card.talents || card.talents.length === 0) && (
                      <p className="text-sm text-ink-500">暂无天赋数据</p>
                    )}
                  </div>
                </div>

                <div>
                  <h3 className="mb-3 flex items-center gap-2 font-medium text-ink-700 dark:text-ink-200">
                    <Shield className="h-4 w-4 text-vermilion" />
                    弱点 debuff
                  </h3>
                  <div className="space-y-3">
                    {card.weaknesses?.map((w, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-vermilion/20 bg-vermilion/5 p-3 dark:bg-vermilion/10"
                      >
                        <div className="font-medium text-ink-800 dark:text-ink-100">
                          {w.name}
                        </div>
                        <div className="text-sm text-ink-600 dark:text-ink-300">
                          {w.description}
                        </div>
                      </div>
                    ))}
                    {(!card.weaknesses || card.weaknesses.length === 0) && (
                      <p className="text-sm text-ink-500">暂无弱点数据</p>
                    )}
                  </div>
                </div>
              </div>

              {card.next_chapter_preview && (
                <div className="mt-6 rounded-xl border border-ink-300/20 bg-ink-100/40 p-4 dark:border-ink-500/20 dark:bg-ink-800/40">
                  <div className="text-xs text-ink-500 dark:text-ink-400">下一章预告</div>
                  <div className="text-ink-800 dark:text-ink-100">
                    {card.next_chapter_preview}
                  </div>
                </div>
              )}
            </SectionCard>
          )}

          {script.chapters && script.chapters.length > 0 && (
            <SectionCard
              title="人生章节"
              icon={<Map className="h-5 w-5 text-vermilion" />}
              delay={200}
            >
              <div className="space-y-4">
                {script.chapters.map((chapter, index) => (
                  <div
                    key={index}
                    className="rounded-xl border border-ink-300/20 bg-ink-100/40 p-5 dark:border-ink-500/20 dark:bg-ink-800/40"
                  >
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                      <span className="rounded-lg bg-vermilion/10 px-2 py-1 text-sm font-medium text-vermilion dark:bg-vermilion/20">
                        第{chapter.index}章
                      </span>
                      <span className="text-lg font-semibold text-ink-800 dark:text-ink-100">
                        {chapter.theme || `${chapter.pillar} 大运`}
                      </span>
                      <span className="text-sm text-ink-500 dark:text-ink-400">
                        {chapter.age_range} 岁 · {chapter.year_range}
                      </span>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <div>
                        <div className="text-xs text-ink-500 dark:text-ink-400">挑战</div>
                        <div className="text-sm text-ink-700 dark:text-ink-200">
                          {chapter.challenge}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-ink-500 dark:text-ink-400">机遇</div>
                        <div className="text-sm text-ink-700 dark:text-ink-200">
                          {chapter.opportunity}
                        </div>
                      </div>
                    </div>

                    <div className="mt-3">
                      <div className="text-xs text-ink-500 dark:text-ink-400">通关建议</div>
                      <div className="text-sm text-ink-700 dark:text-ink-200">
                        {chapter.advice}
                      </div>
                    </div>

                    {chapter.key_events && chapter.key_events.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {chapter.key_events.map((event, i) => (
                          <span
                            key={i}
                            className="rounded-full bg-ink-200/60 px-2 py-0.5 text-xs text-ink-600 dark:bg-ink-700/60 dark:text-ink-300"
                          >
                            {event}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {script.closing && (
            <SectionCard delay={300}>
              <p className="text-center text-lg leading-relaxed text-ink-600 dark:text-ink-300">
                {script.closing}
              </p>
            </SectionCard>
          )}
        </div>
      )}
    </div>
  );
}

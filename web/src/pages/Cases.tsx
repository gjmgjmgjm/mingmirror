import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Library, Search, Tag } from "lucide-react";
import { listBaziCases, type BaziCase } from "../api/client";
import { useChart } from "../contexts/ChartContext";
import { SectionCard, EmptyState, PageHeader, ErrorPanel, Tooltip } from "../components/ui";
import ChartLoader from "../components/ChartLoader";

const DOMAIN_TAGS = ["事业", "财运", "婚姻", "健康", "学业", "综合"];

const DOMAIN_TOOLTIPS: Record<string, string> = {
  事业: "以官杀、印星与格局推断职场发展、升迁创业与事业方向。",
  财运: "以财星、食伤与库墓判断财富层次、进财方式与理财时机。",
  婚姻: "以配偶星、夫妻宫与桃花推断感情模式、婚恋时机与相处之道。",
  健康: "以五行偏枯、刑冲与病药推断体质强弱与易患疾病倾向。",
  学业: "以印星、食伤与文昌推断学习能力、考试运与深造方向。",
  综合: "多维度交叉分析，覆盖性格、家庭、六亲与人生大运等整体判断。",
};

function extractTags(item: BaziCase): string[] {
  const tags = new Set<string>();
  if (item.tags) {
    for (const tag of item.tags) tags.add(tag);
  }
  const text = `${item.question ?? ""} ${item.analysis_corrected ?? ""}`;
  for (const domain of DOMAIN_TAGS) {
    if (text.includes(domain)) tags.add(domain);
  }
  return Array.from(tags);
}

export default function Cases() {
  const { persistChart } = useChart();
  const [cases, setCases] = useState<BaziCase[]>([]);
  const [filtered, setFiltered] = useState<BaziCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await listBaziCases();
        setCases(data.cases);
        setFiltered(data.cases);
      } catch (err) {
        const message = err instanceof Error ? err.message : "加载失败";
        setError(message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    let result = cases;
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (c) =>
          (c.bazi && c.bazi.toLowerCase().includes(q)) ||
          (c.question && c.question.toLowerCase().includes(q)) ||
          (c.analysis_corrected && c.analysis_corrected.toLowerCase().includes(q))
      );
    }
    if (activeTag) {
      result = result.filter((c) => extractTags(c).includes(activeTag));
    }
    setFiltered(result);
  }, [search, activeTag, cases]);

  const handleUseCase = (bazi: string) => {
    void persistChart({
      bazi,
      gender: "male",
      birthDate: "",
      birthTime: "",
    });
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="案例库"
        subtitle="参考真实命盘与断语，快速理解不同格局的推断思路"
      />
      <SectionCard
        title="筛选"
        icon={<Library className="h-5 w-5 text-vermilion" />}
      >
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400 dark:text-ink-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索八字、问题或断语关键词"
            className="input pl-9"
          />
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setActiveTag(null)}
            className={`rounded-full px-3 py-1 text-xs transition ${
              activeTag === null
                ? "bg-vermilion text-white"
                : "bg-ink-100 text-ink-600 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
            }`}
          >
            全部
          </button>
          {DOMAIN_TAGS.map((tag) => (
            <Tooltip key={tag} content={DOMAIN_TOOLTIPS[tag]} position="bottom">
              <button
                type="button"
                onClick={() => setActiveTag(tag)}
                className={`rounded-full px-3 py-1 text-xs transition ${
                  activeTag === tag
                    ? "bg-vermilion text-white"
                    : "bg-ink-100 text-ink-600 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
                }`}
              >
                {tag}
              </button>
            </Tooltip>
          ))}
        </div>
      </SectionCard>

      {loading && <ChartLoader />}

      {error && <ErrorPanel title="加载出错">{error}</ErrorPanel>}

      {!loading && !error && filtered.length === 0 && (
        <EmptyState
          title="暂无案例"
          description="当前没有匹配的案例数据，或后端案例库为空。"
        />
      )}

      {!loading && filtered.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((item, index) => {
            const tags = extractTags(item);
            return (
              <div
                key={index}
                className="panel flex flex-col gap-3 p-4 transition hover:-translate-y-1"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-display text-xl text-ink-800 dark:text-ink-100">
                    {item.bazi || "未命名"}
                  </span>
                  <Link
                    to="/chart"
                    onClick={() => item.bazi && handleUseCase(item.bazi)}
                    className="shrink-0 rounded-lg bg-vermilion/10 px-2 py-1 text-xs font-medium text-vermilion transition hover:bg-vermilion/20 dark:bg-vermilion/20"
                  >
                    使用
                  </Link>
                </div>

                {item.question && (
                  <p className="text-sm text-ink-600 dark:text-ink-300">
                    问：{item.question}
                  </p>
                )}

                {item.analysis_corrected && (
                  <p className="line-clamp-3 text-sm text-ink-500 dark:text-ink-400">
                    {item.analysis_corrected}
                  </p>
                )}

                {tags.length > 0 && (
                  <div className="mt-auto flex flex-wrap gap-1.5 pt-2">
                    {tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1 rounded-full bg-gold/10 px-2 py-0.5 text-[10px] text-gold dark:bg-gold/20"
                      >
                        <Tag className="h-3 w-3" />
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

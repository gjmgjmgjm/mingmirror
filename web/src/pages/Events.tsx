import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ClipboardList, Plus, RefreshCw } from "lucide-react";
import { useChart } from "../contexts/ChartContext";
import {
  listEvents,
  createEvent,
  calibrateChart,
  type LifeEvent,
  type EventType,
  type CalibrationResponse,
} from "../api/client";
import ChartLoader from "../components/ChartLoader";

const EVENT_TYPE_LABELS: Record<EventType, string> = {
  study: "学业",
  job: "就业",
  job_change: "跳槽",
  startup: "创业",
  marriage: "结婚",
  breakup: "分手/离婚",
  house: "置业",
  illness: "疾病",
  surgery: "手术",
  award: "获奖/荣誉",
  move: "搬家/迁移",
  other: "其他",
};

const EVENT_TYPES: EventType[] = [
  "study",
  "job",
  "job_change",
  "startup",
  "marriage",
  "breakup",
  "house",
  "illness",
  "surgery",
  "award",
  "move",
  "other",
];

function todayInputValue() {
  const now = new Date();
  return now.toISOString().slice(0, 10);
}

export default function Events() {
  const { chart } = useChart();
  const [events, setEvents] = useState<LifeEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [calibrating, setCalibrating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CalibrationResponse | null>(null);

  const [eventType, setEventType] = useState<EventType>("job_change");
  const [happenedAt, setHappenedAt] = useState(todayInputValue);
  const [description, setDescription] = useState("");

  const loadEvents = async () => {
    if (!chart) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listEvents(chart.bazi);
      setEvents(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "加载失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEvents();
  }, [chart?.bazi]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chart) return;
    setSubmitting(true);
    setError(null);
    try {
      await createEvent(chart.bazi, {
        event_type: eventType,
        happened_at: happenedAt,
        description,
      });
      setDescription("");
      await loadEvents();
    } catch (err) {
      const message = err instanceof Error ? err.message : "添加失败";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCalibrate = async () => {
    if (!chart) return;
    setCalibrating(true);
    setError(null);
    setResult(null);
    try {
      const data = await calibrateChart(chart.bazi);
      setResult(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "校准失败";
      setError(message);
    } finally {
      setCalibrating(false);
    }
  };

  if (!chart) {
    return (
      <div className="panel mx-auto max-w-2xl p-8 text-center">
        <h2 className="mb-4 text-2xl font-semibold text-ink-700 dark:text-ink-200">
          暂无命盘
        </h2>
        <p className="mb-6 text-ink-600 dark:text-ink-400">
          请先在首页输入八字信息，然后再记录人生事件。
        </p>
        <Link to="/" className="btn-primary inline-flex">
          前往首页
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="panel p-6 md:p-8">
        <div className="mb-6">
          <h1 className="font-display text-3xl text-ink-800 dark:text-ink-100">
            事件校准
          </h1>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
            记录真实人生事件，校准命理系统的权重与可信度
          </p>
        </div>

        <div className="rounded-xl border border-ink-300/30 bg-ink-100/50 p-4 dark:border-ink-500/30 dark:bg-ink-800/50">
          <p className="text-sm text-ink-700 dark:text-ink-200">
            <span className="font-medium">当前命盘：</span>
            {chart.bazi}
          </p>
          <p className="text-xs text-ink-500 dark:text-ink-400">
            已记录 {events.length} 个事件
          </p>
        </div>
      </section>

      <section className="panel p-6">
        <h2 className="mb-4 flex items-center gap-2 text-xl font-semibold text-ink-700 dark:text-ink-200">
          <Plus className="h-5 w-5 text-vermilion" />
          添加事件
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-ink-700 dark:text-ink-200">
                事件类型
              </label>
              <select
                value={eventType}
                onChange={(e) => setEventType(e.target.value as EventType)}
                className="w-full rounded-xl border border-ink-300/50 bg-white px-4 py-2 text-ink-800 outline-none focus:border-vermilion dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100"
              >
                {EVENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {EVENT_TYPE_LABELS[type]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-ink-700 dark:text-ink-200">
                发生时间
              </label>
              <input
                type="date"
                value={happenedAt}
                onChange={(e) => setHappenedAt(e.target.value)}
                required
                className="w-full rounded-xl border border-ink-300/50 bg-white px-4 py-2 text-ink-800 outline-none focus:border-vermilion dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink-700 dark:text-ink-200">
              事件描述
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="例如：2020 年 6 月跳槽到某互联网公司担任产品经理"
              className="w-full rounded-xl border border-ink-300/50 bg-white px-4 py-2 text-ink-800 outline-none focus:border-vermilion dark:border-ink-600 dark:bg-ink-900 dark:text-ink-100"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="btn-primary disabled:cursor-not-allowed"
          >
            {submitting ? "保存中…" : "添加事件"}
          </button>
        </form>
      </section>

      <section className="panel p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-xl font-semibold text-ink-700 dark:text-ink-200">
            <ClipboardList className="h-5 w-5 text-vermilion" />
            已记录事件
          </h2>
          <button
            type="button"
            onClick={loadEvents}
            disabled={loading}
            className="text-sm text-ink-500 hover:text-vermilion disabled:cursor-not-allowed dark:text-ink-400"
          >
            刷新
          </button>
        </div>

        {loading && <ChartLoader />}

        {!loading && events.length === 0 && (
          <p className="text-ink-500 dark:text-ink-400">
            还没有记录任何事件。添加真实事件后，可以运行校准来比较八字与七政四余的预测吻合度。
          </p>
        )}

        {!loading && events.length > 0 && (
          <div className="space-y-3">
            {events.map((event) => (
              <div
                key={event.id}
                className="rounded-xl border border-ink-300/30 bg-white p-4 dark:border-ink-600/30 dark:bg-ink-900/50"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <span className="inline-block rounded-full bg-vermilion/10 px-2.5 py-0.5 text-xs font-medium text-vermilion">
                      {EVENT_TYPE_LABELS[event.event_type as EventType] || event.event_type}
                    </span>
                    <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
                      {event.happened_at}
                    </p>
                    {event.description && (
                      <p className="mt-2 text-ink-700 dark:text-ink-200">
                        {event.description}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel p-6">
        <button
          type="button"
          onClick={handleCalibrate}
          disabled={calibrating || events.length === 0}
          className="btn-primary btn-shimmer disabled:cursor-not-allowed"
        >
          {calibrating ? (
            <>
              <RefreshCw className="relative mr-2 h-4 w-4 animate-spin" />
              <span className="relative">校准中</span>
            </>
          ) : (
            <>
              <RefreshCw className="relative mr-2 h-4 w-4" />
              <span className="relative">运行校准</span>
            </>
          )}
        </button>
        <p className="mt-2 text-xs text-ink-500 dark:text-ink-400">
          校准会调用八字与七政四余系统，对比它们对每条事件的预测描述，给出系统得分与建议时辰偏移。
        </p>
      </section>

      {error && (
        <div className="panel border-l-4 border-l-vermilion p-6 text-vermilion dark:border-l-vermilion-light">
          <p className="font-medium">出错了</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {result && (
        <section className="panel animate-chart-section p-6">
          <h2 className="mb-4 text-xl font-semibold text-ink-700 dark:text-ink-200">
            校准结果
          </h2>

          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-ink-300/30 bg-ink-100/50 p-4 dark:border-ink-500/30 dark:bg-ink-800/50">
              <p className="text-xs text-ink-500 dark:text-ink-400">事件数</p>
              <p className="text-2xl font-semibold text-ink-800 dark:text-ink-100">
                {result.event_count}
              </p>
            </div>
            <div className="rounded-xl border border-ink-300/30 bg-ink-100/50 p-4 dark:border-ink-500/30 dark:bg-ink-800/50">
              <p className="text-xs text-ink-500 dark:text-ink-400">平均吻合度</p>
              <p className="text-2xl font-semibold text-ink-800 dark:text-ink-100">
                {(result.average_score * 100).toFixed(1)}%
              </p>
            </div>
            {Object.entries(result.system_scores).map(([system, score]) => (
              <div
                key={system}
                className="rounded-xl border border-ink-300/30 bg-ink-100/50 p-4 dark:border-ink-500/30 dark:bg-ink-800/50"
              >
                <p className="text-xs text-ink-500 dark:text-ink-400">
                  {system === "bazi" ? "八字" : system === "qizheng" ? "七政四余" : system} 得分
                </p>
                <p className="text-2xl font-semibold text-ink-800 dark:text-ink-100">
                  {(score * 100).toFixed(1)}%
                </p>
              </div>
            ))}
          </div>

          {result.suggested_hour_offset !== undefined && result.suggested_hour_offset !== null && (
            <div className="mb-6 rounded-xl border border-vermilion/30 bg-vermilion/5 p-4 dark:border-vermilion/40 dark:bg-vermilion/10">
              <p className="font-medium text-ink-800 dark:text-ink-100">
                建议时辰偏移：±{result.suggested_hour_offset} 小时
              </p>
              <p className="text-sm text-ink-600 dark:text-ink-400">
                当前预测与事件吻合度较低，可尝试将出生时间前后调整 {result.suggested_hour_offset} 小时重新排盘验证。
              </p>
            </div>
          )}

          {result.events.length > 0 && (
            <div>
              <h3 className="mb-3 font-semibold text-ink-700 dark:text-ink-200">
                事件级评分
              </h3>
              <div className="space-y-3">
                {result.events.map((event) => (
                  <div
                    key={event.event_id}
                    className="rounded-xl border border-ink-300/30 bg-white p-4 dark:border-ink-600/30 dark:bg-ink-900/50"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="inline-block rounded-full bg-vermilion/10 px-2.5 py-0.5 text-xs font-medium text-vermilion">
                        {EVENT_TYPE_LABELS[event.event_type as EventType] || event.event_type}
                      </span>
                      <span className="text-sm text-ink-500 dark:text-ink-400">
                        {event.happened_at}
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-3">
                      {Object.entries(event.scores).map(([system, score]) => (
                        <span
                          key={system}
                          className="text-sm text-ink-700 dark:text-ink-200"
                        >
                          {system === "bazi" ? "八字" : system === "qizheng" ? "七政四余" : system}:
                          {" "}
                          <span className="font-medium">{(score * 100).toFixed(0)}%</span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

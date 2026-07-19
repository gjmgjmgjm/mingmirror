# 命镜能力边界（交付口径）

本文固定**产品与评测可承诺什么**，避免把结构层 det 准确率与事件 MCQ 混谈。

---

## 1. 三层披露模型

| 层 | 内容 | 产品展示 | 准确率口径 |
|----|------|----------|------------|
| **A 结构 det** | 排盘、用神（穷通）、六亲强弱 det、**六亲细断**（性格/健康/关系/大运应期提要）、大运排盘 | `certain` / 确定性标签 | 可 cite：排盘 100%、用神 100%、六亲强弱 ~92%；细断性格/应期为取象，不作医断与「必在某年」 |
| **B 结构应期 shortlist** | 年份 MCQ / 「哪年…」的符号 top-2 | 并列候选年，**禁止「必在某年」** | 离线 top-1 ~44%、top-2 ~60%；live MiniMax 全量 MCQ ~31–32% |
| **C 叙事 / 趋势** | 性格、事业倾向、感情基调、流年体感 | `ai` / 趋势文案 | **不报准确率**；开放式事件年 ≈ 物理天花板 0% |

实现入口：

- A：`bazi_structural` / 报告 `trust=certain`
- B：`tools.bazi_ai.year_timing_surface.resolve_year_timing`
- C：LLM prose + 领域 focus（事业/婚姻提示）

---

## 2. 年份应期 UI 规则（强制）

`resolve_year_timing(...).display_mode`：

| mode | UI 行为 |
|------|---------|
| `hard_shortlist` | 表格展示 top-1/2 年 + 干支 + 理由；标题用「结构应期 shortlist」；**不得**单选断言 |
| `soft_hint` | 折叠/次要样式展示候选；文案含「不确定」 |
| `trend_only` | **不展示公历年**；只写婚宫/父母宫/大运趋势 |
| `unavailable` | 隐藏应期模块 |

`assert_single_year` 恒为 `false`（产品层禁止单年断言）。

```python
from tools.bazi_ai.year_timing_surface import resolve_year_timing, format_product_block

surf = resolve_year_timing(
    bazi, "命主父亲于哪年去世?", options, gender="male",
    birth_date="1954-03-18", birth_time="15:00",
)
block = format_product_block(surf)  # Markdown
# API: surf.to_dict()
```

**HTTP / 前端（已接线）**

| 路径 | 说明 |
|------|------|
| `POST /api/v1/bazi/year-timing` | 零 LLM；body 含 `bazi/question/options/birth_*` |
| `POST /api/v1/bazi/analyze` → `result.year_timing_surface` | 分析时自动注入（无 options 时仅「哪年…」开放式出 `trend_only`） |
| `web` `YearTimingPanel` + `ChartBasic` | 展示 shortlist 表或趋势提示 |
| `result.liuqin_dossier` / `LiuqinDossierPanel` | 父/母/配偶/子女/手足：性格·能力·健康·关系·双星合参（母印/父财/配偶官杀或财/子女官杀或食伤/手足比劫）·宫位合参·大运引动·流年象征取样（非单年断言） |
| `year_timing_surface.meta.liuqin_bridge` | 应期 shortlist 与六亲流年取样联动：重合年标注、UI 双向高亮；不作必在某年 |
| `ReadingReport` `year_timing` section | 报告分区渲染 |
| `web/src/api/client.ts` `fetchYearTiming` | 前端封装 |

---

## 3. 评测 KPI 怎么读

| 指标 | 数值（2026-07-19 量级） | 用途 |
|------|------------------------|------|
| Contest8 **n=200** MiniMax abab6.5s | **~31–32%** | 诚实全量 MCQ 基线 |
| Contest8 n=40 峰值 | ~47% | **不可外推**（方差大） |
| 年份 shortlist 离线 top-1 / top-2 | ~44% / ~60% | 规则层改进尺子 |
| 排盘 / 用神 / 六亲 det | 100% / 100% / **~93%** (42/45) | 结构层交付 |
| year critic（零 API re-rank） | 仅作 shortlist 偏好信号 | `meta.structural_critic`；禁止单年断言 |

**不要**用 n=40 峰值对外宣传「准确率近半」。

模型 A/B（同协议 n=40）：abab6.5s ≥ M2.5-hs > Text-01；ensemble=2 **无收益**。默认 `config.yml`：`abab6.5s-chat`。

---

## 4. 产品文案红线

**禁止**

- 「必在 2017 年离婚/发财」类开放式断言并标准确率  
- 把结构 det 90%+ 暗示为「全盘命理 90%」  
- 用 shortlist 第一名自动填死答案且不展示并列  

**允许**

- 「结构上 1959 / 1969 信号较强，需结合大运叙述」  
- 「婚宫日支比劫，感情宜以波折论，不作美满断言」  
- 报告分区：结构 certain / 应期 shortlist / AI 叙事  

---

## 5. 与路线图的关系

- 结构 90% 目标：**仅 A 层**（见 `structural-trust-layer.md`、记分板）  
- 事件 MCQ：继续可做年份权重 / 外部强模型，但**不阻塞发版**  
- 发版 checklist：结构 golden + liuqin det + 本文件口径 + `year_timing_surface` 单测  

---

## 6. 相关文件

| 路径 | 说明 |
|------|------|
| `tools/bazi_ai/year_timing_surface.py` | 应期展示决策 API |
| `tools/bazi_ai/rule_reasoner.py` | `YEAR_SIGNAL_WEIGHTS` / shortlist |
| `benchmarks/baziqa/rule_calibrate_v2.py` | 年份权重 LOO 标定 |
| `docs/README.md` | live 记分板 |
| `docs/bazi_ai_error_analysis.md` | 误差与 Phase 记录 |

# 项目文档目录与总索引

本目录存放 `douyin-downloader` 项目的补充文档。项目有**两条主线**,文档按此组织:

- **下载器主线**(`cli/` `core/` `storage/` `control/` `auth/`):成熟的抖音批量下载工具,v2.0.0,642+ 测试,维护态。
- **命镜命理主线**(`tools/bazi_ai/` `tools/qizheng/` `tools/ziwei/` `tools/destiny/` `server/` `web/`):八字 / 紫微 / 七政四余 / 多命理融合 + React Web UI + REST API,**当前活跃开发**。

---

## 📑 文档索引

| 文件 | 主线 | 说明 |
|------|------|------|
| [../PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md) | 全局 | 架构、能力、测试统计总览(含命理记分板与尺子入口) |
| [DEPLOY.md](./DEPLOY.md) | 命理/产品 | Docker Compose、支付 webhook、运营看板、环境变量 |
| [PRD-mingmirror.md](./PRD-mingmirror.md) | 命理 | 命镜产品需求:数字孪生 / 多 Agent 议会 / 事件反推校准 / 择日引擎 / 命运剧本 |
| [bazi_ai_90_roadmap.md](./bazi_ai_90_roadmap.md) | 命理 | 八字准确率推进计划(Phase 0–5 + §7「真人结构层」战略转向) |
| [bazi_ai_error_analysis.md](./bazi_ai_error_analysis.md) | 命理 | 八字错误类型诊断、占比与修复优先级 |
| [structural-trust-layer.md](./structural-trust-layer.md) | 命理 | 结构层 gold / 生产启动守卫 / device 隔离 |
| [capability-boundary.md](./capability-boundary.md) | 命理 | **交付口径** A 结构 det / B 应期 shortlist / C 趋势；UI 红线 |
| [resources_datasets_techniques.md](./resources_datasets_techniques.md) | 命理 | **全网专业技术、数据集、开源栈与 ROI 路线图** |
| [sync-status.md](./sync-status.md) | 下载器 | CLI 版与桌面版(douyin-downloader-desktop)共享模块同步状态 |
| [../README.md](../README.md) / [../README.zh-CN.md](../README.zh-CN.md) | 全局 | 用户快速开始 |
| [../AGENTS.md](../AGENTS.md) 及各子目录 `AGENTS.md` | — | 模块级开发说明(auth / cli / core / storage / control / tools / server / utils) |

---

## 📊 命理准确率记分板(live)

由 `python benchmarks/baziqa/accuracy_report.py` 实时生成(**零 API、确定性尺子**)。最近一次运行:**2026-07-19**。

| 维度 | 准确率 | gold 性质 |
|------|--------|-----------|
| 排盘 | 100% (32/32) | ✅ 真实(对齐 iztro 预制命盘) |
| 用神 | 100% (92/92, 大n) | ✅ 真实(对齐穷通宝鉴调候) |
| 格局 | 100% | 确定性注入(月令定格,非 accuracy) |
| 忌神 | 92% | 确定性注入(规则引擎,非 accuracy) |
| 旺衰 | 75% | LLM-引擎一致性(非 accuracy) |
| 六亲强弱 | **100% (46/46, det, 噪声剔除)** | ✅ 真实(杨炎 gold,det 绕过 LLM) |
| 具体事件/年份 | 0% 开放式 / ~32–48% MCQ (MiniMax) | 真实(Contest8 / 名人) |

> **口径说明**
> - ✅ 真实 = 有独立 / 权威 gold,数字可 cite;格局/忌神/旺衰是**确定性注入或 LLM-引擎一致性**,**不是 accuracy**(不证明对错),需 gold 才算准确率。
> - **「结构层 90%」目标框定**:仅指**有独立 gold 的维度**——排盘 100%、用神 100%(穷通 n=92)、**六亲 100%(det,n=46)** 均已达成（双星合参 / 父星年月根与财生杀得令例外 / 配偶多透干抗冲）。格局/忌神/旺衰**不计入**;事件层是物理天花板。年份 shortlist LOO top1≈45%/top2≈61%（soft top2≈70%），**不是**开放式准确率。
> - **六亲** det:启发式再加「坐支通根」等规则实测回退至 67–69%,故停在可解释清洗而非过拟合。详见 `validate_liuqin_det.py` 的 `_DET_NOISE`。
> - **事件层开放式 ≈0% 是物理天花板**,非 bug——产品应输出**趋势**而非断言。

**零 API 全量评测**（Contest8 / MingLi / Celebrity50 本地数据）:

```bash
python benchmarks/baziqa/zero_api_eval.py
# 最近快照: benchmarks/baziqa/results/zero_api_baseline_2026-07-19.txt
```

| 尺子（2026-07-19 全量） | 数值 | 说明 |
|------------------------|------|------|
| 排盘一致性 celebrity_extra | **100%** (200/200) | 预计算八字 vs `pillars_for_datetime` |
| 年份 MCQ 纯规则 shortlist | top1 **30.6%** / top2 **51.1%** (n=186) | 跨 Contest8+MingLi+Celebrity50 |
| · Contest8 only | top1 **45%** / top2 **61%** (n=44) | 与 LOO 标定一致 |
| · MingLi | top1 **38%** / top2 **56%** (n=34) | |
| · Celebrity50 | top1 **22%** / top2 **45%** (n=108) | 题型更杂、上限更低 |
| 结构 critic | **31.2%** (n=186) | 大运/驿马 re-rank，约等于 top1 |
| 生日 shuffle 对照 | **100%** (40/40) | +180 天特征必变 |

> **诚实**：全源年份 shortlist top1≈31% **不是**结构 det；Contest8 切片 45% 不可外推到名人题。产品仍只承诺 A 层 det + 应期 shortlist 并列展示。

**MiniMax Contest8 MCQ**（`abab6.5s-chat` + enhanced + soft shortlist + post-LLM trust, LOO）:

| 切片 | 准确率 | 结果文件 |
|------|--------|----------|
| n=40 / n=80 小样本 | 最高 **47.5% / 43.8%** | **不可外推**；方差大 |
| **n=200 soft v6（当前全量）** | **31.5%** (63/200) | `…_n200_v6.jsonl` |
| n=200 soft v5 | 31.0% (62/200) | 六亲+婚姻措辞 |
| n=200 soft v3 | 32.0% (64/200) | 早期 soft shortlist |
| n=40 arbiter | 37.5% | 2×费用，未超过 soft 峰值 |

**全量分域（n=200，v6 vs v5 vs v3）**

| 域 | v3 | v5 | **v6** | 解读 |
|----|----|----|--------|------|
| 事业/学历 | 37.1% | 20.0% | **37.1%** | 事业提示常开把 v5 回落拉回 |
| 家庭/六亲 | 15.4% | 38.5% | **46.2%** | liuqin 提示持续有效 |
| 年份 | 34.2% | 31.6% | 31.6% | shortlist 天花板仍在 |
| 婚姻状态 | 21.1% | 21.1% | 21.1% | 长期短板 |
| 性格 | 31.2% | 50.0% | 25.0% | 高方差 |

> **诚实结论**：全量 Contest8 + MiniMax abab6.5s 目前 **稳定在 ~31–32%**。规则层（shortlist / 六亲 / 事业）对**分域**有可复现收益，但被后半难题 + 模型方差抵消，整体 KPI 不再靠改 prompt 微抬。

**年份 LOO 再标定（2026-07-19，`rule_calibrate_v2.py`）**

| 尺子（离线 year-asking n=45） | 标定前 | **标定后** |
|------------------------------|--------|------------|
| ungated top-1 | ~33–36% | **44.4%** |
| ungated top-2 | ~53–55% | **60.0%** |
| soft shortlist fire | ~27–33 | 33 |
| soft shortlist top-2 | ~60% | **63.6%** |

权重变化要点：半三合 0.4→0.2；反吟 / 流年冲宫 → 负权；门控 score 地板 0.4→0.2（适配新分尺）。

**模型 A/B（同协议 enhanced+soft shortlist+LOO，Contest8 n=40）**

| 模型 | 准确率 | 备注 |
|------|--------|------|
| **abab6.5s-chat** (v2 峰值) | **47.5%** | 当前生产默认 |
| MiniMax-M2.5-highspeed | 42.5% | 需 max_tokens≥3k（thinking 耗额度） |
| abab ensemble=2 | 37.5% | 2×费用，未抬分 |
| MiniMax-Text-01 | 32.5% | 更差 |
| 全量 n200 abab | **~31–32%** | 诚实 KPI |

> 结论：在可用 MiniMax 型号里 **abab6.5s-chat 仍最优**；换 M2.5 / ensemble **不能突破** ~45% n40 天花板。eval 已支持 strip `<think>`、M 系列自动抬 max_tokens。

```bash
# 全量 Contest8（需 MINIMAX_API_KEY / config.yml bazi_ai）
python -m tools.bazi_ai.baziqa_eval --data benchmarks/baziqa/data --datasets contest8 \
  --mode enhanced --leave-one-out --shortlist-mode soft --limit 200 \
  --base-url https://api.minimax.chat/v1 --model abab6.5s-chat \
  --output benchmarks/baziqa/results/contest8_minimax_abab65s_n200.jsonl
```

刷新需 API 的维度(设定 `MINIMAX_API_KEY` 或 `DEEPSEEK_API_KEY` 后):

```bash
python benchmarks/baziqa/validate_consensus.py --limit 12   # 格局/忌神/旺衰 自洽
python benchmarks/baziqa/validate_real.py    --limit 12     # 六亲 e2e
python benchmarks/baziqa/validate_mingli.py  --limit 12     # 事件/年份
```

---

## 🔬 尺子(`validate_*`)速查

| 尺子 | 测什么 | 是否需 API |
|------|--------|:----------:|
| `validate_chart.py` | 排盘 vs iztro(自动检测立春 gold 错) | 否 |
| `validate_yongshen.py` | 用神 vs 穷通宝鉴调候(MingLi 32) | 否 |
| `validate_yongshen_full.py` | 用神 vs 穷通宝鉴(大n聚合 92 命主) | 否 |
| `validate_consensus.py` | 格局 / 用神 / 忌神 / 旺衰(规则注入自洽) | 否(det)/ 是(e2e) |
| `validate_liuqin_det.py` | 六亲确定性(绕过 LLM) | 否 |
| `validate_real.py` | 六亲强弱 e2e(deepseek prose + field) | 是 |
| `validate_mingli.py` | 具体事件 / 年份 vs 名人(celebrity50 / MingLi) | 是 |
| `validate_past.py` | 过去验证(命主层) | 是 |
| `accuracy_report.py` | 上面确定性维度的汇总记分板 | 否 |

> `benchmarks/baziqa/_*.py`(下划线前缀)为**一次性实验 / 对比脚本**(shortlist A/B、RAG 对比、领域探查等),非长期尺子;`rule_diagnose.py` / `rule_calibrate.py` 为规则引擎诊断与 LOO 权重标定。

---

## 项目亮点速览

- **下载器**:无水印下载、并发限速重试、SQLite 去重增量、`post`/`like`/`mix`/`music` 浏览器兜底、FastAPI server(job 提交 / 取消 / SSE / 配置覆盖)、CI 全覆盖(Python 3.9–3.12 矩阵)。
- **命镜**:四柱校验、领域感知 RAG + embedding、规则引擎兜底、用神引擎(扶抑 + 调候 + 通关)、取象专字段、多轮 ensemble、**多模型辩论 `ensemble_debate`**(chat+reasoner + critic 结构裁决);**择日引擎**(用神+冲合+十二时辰吉时、8 类事项、`.ics` 导出);可解释命书报告;`/report` + `/auspicious` REST;八字 / 紫微 / 七政四余 / 多命理融合;React Web UI(Dashboard / Chart / Yearly / Qizheng / Ziwei / Council / Sandbox / Script / Cases / Calendar / ReadingReport)。

## 相关入口

- 用户快速开始:[`../README.md`](../README.md) / [`../README.zh-CN.md`](../README.zh-CN.md)
- 模块开发说明:各子目录下的 `AGENTS.md`
- 数据集说明:[`../benchmarks/baziqa/README.md`](../benchmarks/baziqa/README.md) / 实验报告 [`../benchmarks/baziqa/benchmark_report.md`](../benchmarks/baziqa/benchmark_report.md)

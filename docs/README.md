# 项目文档目录与总索引

本目录存放 `douyin-downloader` 项目的补充文档。项目有**两条主线**,文档按此组织:

- **下载器主线**(`cli/` `core/` `storage/` `control/` `auth/`):成熟的抖音批量下载工具,v2.0.0,642+ 测试,维护态。
- **命镜命理主线**(`tools/bazi_ai/` `tools/qizheng/` `tools/ziwei/` `tools/destiny/` `server/` `web/`):八字 / 紫微 / 七政四余 / 多命理融合 + React Web UI + REST API,**当前活跃开发**。

---

## 📑 文档索引

| 文件 | 主线 | 说明 |
|------|------|------|
| [../PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md) | 全局 | 架构、能力、测试统计总览(含命理记分板与尺子入口) |
| [PRD-mingmirror.md](./PRD-mingmirror.md) | 命理 | 命镜产品需求:数字孪生 / 多 Agent 议会 / 事件反推校准 / 择日引擎 / 命运剧本 |
| [bazi_ai_90_roadmap.md](./bazi_ai_90_roadmap.md) | 命理 | 八字准确率推进计划(Phase 0–5 + §7「真人结构层」战略转向) |
| [bazi_ai_error_analysis.md](./bazi_ai_error_analysis.md) | 命理 | 八字错误类型诊断、占比与修复优先级 |
| [sync-status.md](./sync-status.md) | 下载器 | CLI 版与桌面版(douyin-downloader-desktop)共享模块同步状态 |
| [../README.md](../README.md) / [../README.zh-CN.md](../README.zh-CN.md) | 全局 | 用户快速开始 |
| [../AGENTS.md](../AGENTS.md) 及各子目录 `AGENTS.md` | — | 模块级开发说明(auth / cli / core / storage / control / tools / server / utils) |

---

## 📊 命理准确率记分板(live)

由 `python benchmarks/baziqa/accuracy_report.py` 实时生成(**零 API、确定性尺子**)。最近一次运行:**2026-07-15**。

| 维度 | 准确率 | gold 性质 |
|------|--------|-----------|
| 排盘 | 100% (32/32) | ✅ 真实(对齐 iztro 预制命盘) |
| 用神 | 90% (83/92, 大n) | ✅ 真实(对齐穷通宝鉴调候) |
| 格局 | 100% | 确定性注入(月令定格,非 accuracy) |
| 忌神 | 92% | 确定性注入(规则引擎,非 accuracy) |
| 旺衰 | 75% | LLM-引擎一致性(非 accuracy) |
| 六亲强弱 | 77% (30/39, det) | ✅ 真实(杨炎 gold,det 绕过 LLM) |
| 具体事件/年份 | 0% 开放式 / 40% MCQ | 真实(名人验证事件) |

> **口径说明**
> - ✅ 真实 = 有独立 / 权威 gold,数字可 cite;格局/忌神/旺衰是**确定性注入或 LLM-引擎一致性**,**不是 accuracy**(不证明对错),需 gold 才算准确率。
> - **「结构层 90%」目标框定**:仅指**有独立 gold 的维度**——排盘 100%、用神 90% 已达成;**六亲 77%(det,n=39)未达 90%,是结构层唯一 accuracy 短板**(加"星被耗泄→弱"判定后 74→77,父亲 75→83,zero regression;剩余 9 错例约半为 gold 噪声,边际递减)。格局/忌神(确定性注入)、旺衰(LLM-引擎一致性)**不计入**;事件层是物理天花板。
> - **六亲** det 全量 n=39,准确率 **77%**(加"星被耗泄→弱"判定后 74→77,zero regression;threshold 1.0 会 over-fire 误伤配偶→69%,故选 1.5)。剩余 9 错例:坏根 over-fire vs gold 主观 + 个别耗泄阈值未触。e2e deepseek prose 口径 ~73–77%。详见 `bazi_ai_90_roadmap.md` 与 memory。
> - **事件层开放式 ≈0% 是物理天花板**,非 bug——产品应输出**趋势**而非断言。

刷新需 API 的维度(设定 `DEEPSEEK_API_KEY` 后):

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
- **命镜**:四柱校验、领域感知 RAG + embedding、规则引擎兜底、用神引擎(扶抑 + 调候 + 通关)、取象专字段、多轮 ensemble;八字 / 紫微 / 七政四余 / 多命理融合 REST API;React Web UI(Dashboard / Chart / Yearly / Qizheng / Ziwei / Council / Sandbox / Script / Cases / Calendar)。

## 相关入口

- 用户快速开始:[`../README.md`](../README.md) / [`../README.zh-CN.md`](../README.zh-CN.md)
- 模块开发说明:各子目录下的 `AGENTS.md`
- 数据集说明:[`../benchmarks/baziqa/README.md`](../benchmarks/baziqa/README.md) / 实验报告 [`../benchmarks/baziqa/benchmark_report.md`](../benchmarks/baziqa/benchmark_report.md)

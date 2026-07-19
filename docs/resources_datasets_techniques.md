# 命理 AI：专业技术、开源栈与数据集地图

> 调研时间：2026-07 · 面向 MingMirror / douyin-downloader 命镜线  
> 目的：对齐业界「**确定性排盘 + 符号推理 + LLM 叙述**」主流范式，并列出可接入的数据与评测源。

---

## 1. 业界共识的技术路线（务必对齐）

多家产品与论文得到同一结论：**通用 LLM 直接排盘/论用神会 hallucinate；必须把可符号化步骤做成程序，再让 LLM 读盘。**

| 技术层 | 做什么 | 代表实践 |
|--------|--------|----------|
| **确定性排盘** | 立春换年、节气换月、子时换日、真太阳时、藏干 | sxtwl / lunar-javascript / iztro / Swiss Ephemeris（七政） |
| **符号特征** | 十神、刑冲合会、格局、用神、神煞、六亲 | 规则引擎 + 查表 |
| **注入/强制采纳** | prompt 注入 + **后处理覆盖** 用神/六亲强弱 | Cantian MCP 哲学；本仓库 `_force_det_fields` |
| **RAG** | 案例库 / 规则书按领域检索 | 杨炎 cases、BaziQA reverse cases |
| **Shortlist** | 年份 MCQ：规则 top-2 → LLM 二选一 | 本仓库 `rule_reasoner.rank_year_candidates` |
| **多模型** | debate / critic / ensemble | 本仓库 destiny ensemble |
| **MCP / Tool** | 排盘当工具，禁止模型自算 | Cantian BaZi MCP Server |

**产品表述建议**（与 deeporacle / Jenova 一致）：  
- 结构题（排盘、用神、六亲 det）→ 报 **确定准确率**  
- 开放式事件 → **趋势/概率语气**，不承诺断言

---

## 2. 专业评测与数据集（优先收藏）

### 2.1 学术 / 基准（可量化）

| 名称 | 链接 | 内容 | 与本项目关系 |
|------|------|------|----------------|
| **BaziQA** | [github.com/ChenJiangxi/BaziQA](https://github.com/ChenJiangxi/BaziQA) · arXiv:2602.12889 | 全球命理师大赛真题 MCQ；Contest8 等 | 已部分接入 `benchmarks/baziqa/`、`cases_baziqa.jsonl` |
| **Celebrity50**（BaziQA/AuraMate 线） | 同上 + AuraMate 自述 | 名人跨域 200 题左右 | 已有 `data/celebrity50_zh.json` |
| **BaZi-Persona / Celebrity50 QA** | [arXiv:2510.23337](https://arxiv.org/abs/2510.23337) · [MirrorAI-Lab/BaZi-Persona](https://github.com/MirrorAI-Lab/BaZi-Persona) | 50 名人 × 五维人生事件 MCQ；符号+LLM 提 30–60% | **强烈建议接入对照**；含「打乱生日」消融范式 |
| **MingLi-Bench** | 开源社区/AtomGit 报道 · 全球赛 2022–2025 真题约 160 题 | 排盘与推理解耦（iztro 预制盘） | 与 BaziQA 同源赛题，可做第二 LOO 集 |
| **Global Fortune-Teller Championship** | 香港初级风水师协会等主办 | 真题来源 | 论文已整理 2010–2024 部分；注意版权与仅评测用途 |
| **AuraMate 实时榜** | [auramate.net live-benchmark](https://auramate.net/article/live-benchmark) | 多模型 BaziQA 排行 | 对标水位，非数据集本体 |

### 2.2 本地已有（本仓库）

| 路径 | 用途 |
|------|------|
| `bazi_knowledge/杨炎八字绝技_cases.jsonl` | 六亲 det gold / RAG |
| `bazi_knowledge/cases*.jsonl` | 综合案例 |
| `benchmarks/baziqa/data/contest8_*.json` | 赛题年份拆分 |
| `benchmarks/baziqa/data/celebrity50_zh.json` | 跨域 |
| `benchmarks/baziqa/data/mingli/` | MingLi 相关 |
| `tests/fixtures/structural_golden.json` | 排盘/紫微/大运零 API 回归 |
| `tools/ziwei/cases.jsonl` · `tools/qizheng/cases.jsonl` | 紫微/七政 few-shot |

### 2.3 算法库 / 排盘栈（工程依赖）

| 库 | 语言 | 用途 |
|----|------|------|
| **sxtwl** | C++/Python | 寿星天文历；本仓库农历/节气 |
| **iztro** | TypeScript | 紫微；本仓库 validate_chart 对照 |
| **lunar-javascript / lunar-python** | JS/Python | 农历、八字常用 |
| **Swiss Ephemeris** | C | 七政真星历（本仓库 qizheng） |
| **Cantian BaZi MCP** | MCP Server | 给 LLM 挂「准确排盘工具」 |
| **bazi-mingli** (Wolke) | Agent Skill | 开源 skill 结构：rizhu-qiangruo / yongshen 分文件 |
| **BaZi Master** (tytsxai) | 全栈示例 | React+Express 多模态玄学样板 |

### 2.4 产品/方法论参考（非开源数据）

| 产品 | 可借鉴点 |
|------|----------|
| **deeporacle.ai** | 格局强制校验 + 经典引用（子平真诠/滴天髓/穷通宝鉴）；公开模型对比数字（注意口径） |
| **Cantian AI** | MCP 治 hallucination；多语言 |
| **Jenova / Shen-Shu** | 强调通用模型排盘错误；真太阳时/立春/子时 |
| **Master Tsai AI Bazi Model** | 可下载的「模型 BOM」文本（prompt/知识包形态） |
| **BaziAI.com** | R1 + 多维分析产品形态 |

---

## 3. 可落地的「专业技巧」清单（按 ROI）

### A. 已在本仓库落地或部分落地

1. 排盘与论断解耦（iztro/sxtwl gold）  
2. 用神引擎（扶抑+调候+通关）→ 穷通 gold  
3. 六亲 det（星宫 + 冲合坏根 + 子女透干严判）→ 杨炎 gold **92%**  
4. 年份 shortlist top-2  
5. 议会 / ensemble  
6. **后处理强制覆盖** `useful_gods` / `liuqin_strength`（`engine._force_det_fields`，2026-07）

### B. 建议下一波（高 ROI）

| 优先级 | 技巧 | 说明 |
|--------|------|------|
| P0 | **接入 BaZi-Persona Celebrity50** | 论文公开；测「符号注入 vs 裸 LLM」与 birthday-shuffle 消融 |
| P0 | **MingLi-Bench / 赛题统一 loader** | 与 contest8 并列为第二 LOO，防过拟合 BaziQA 题型 |
| P1 | **年份 critic 二选一** | shortlist 内用结构事实（驿马/冲合/大运）裁决 |
| P1 | **领域条件 RAG** | 六亲题只灌六亲规则；全量灌入有害（roadmap 已验证） |
| P1 | **旺衰独立 gold 标注** | 现仅有 LLM 一致性；要 accuracy 需人工标 50–100 盘 |
| P2 | **Cantian 式 MCP 接口** | 对外暴露 `compute_chart` tool，禁止客户端模型自排盘 |
| P2 | **格局强制条件检查** | deeporacle 式：从格条件不满足则拒绝从格 |
| P3 | SFT/LoRA | 有 GPU 再做；结构层 det 已过 90% 后边际在事件 MCQ |

### C. 不建议当主目标

- 开放式「哪年离婚/发财」断言准确率（物理天花板）  
- 无 gold 的「像不像大师文风」主观评分当 KPI  

---

## 4. 数据合规与使用注意

1. **大赛真题**：评测/研究为主；商用复述需确认主办方与整理者授权。  
2. **名人出生时间**：astro.com 等来源仍有误差；shuffle 消融可证明「用到了盘」而非记答案。  
3. **杨炎等 PDF 案例**：本仓库本地知识，注意版权勿整库公开分发。  
4. **LLM 生成的 QA**（BaZi-Persona 部分流程）：论文 Limitations 已承认噪声；接入时做清洗。

---

## 5. 推荐阅读顺序

1. BaziQA 仓库 README + 本仓库 `docs/bazi_ai_90_roadmap.md`  
2. arXiv:2510.23337（符号+LLM + Celebrity50 方法）  
3. Cantian BaZi MCP 设计（工具化排盘）  
4. deeporacle FAQ（结构题 vs 开放题口径）  
5. 本仓库 `docs/structural-trust-layer.md`（本地 gold 与生产守卫）

---

## 6. 本仓库可执行命令（**全部零 API**）

```bash
# 结构层真实 gold 尺子
python benchmarks/baziqa/accuracy_report.py
python benchmarks/baziqa/validate_liuqin_det.py --limit 200
python benchmarks/baziqa/validate_yongshen.py

# 统一数据集 + 年份 shortlist/critic 评测（Contest8/MingLi/Celebrity50 已本地化）
python benchmarks/baziqa/zero_api_eval.py
python benchmarks/baziqa/zero_api_eval.py --sources contest8,mingli --json report.json

# 排盘/紫微/大运 + det 强制覆盖回归
python -m pytest tests/test_structural_golden.py tests/test_det_enforcement.py tests/test_zero_api_eval.py -q
```

### 本地数据集体量（无需再下载）

| 源 | 题量/盘量 | loader |
|----|-----------|--------|
| Contest8 2021–2025 | **200** MCQ | `dataset_loader.load_contest8` |
| MingLi (`mingli/data.json`) | **160** MCQ | `load_mingli` |
| Celebrity50 | **486** MCQ | `load_celebrity50` |
| celebrity_extra 预计算盘 | **298** | `load_celebrity_extra_charts` |

零 API 评测入口：`benchmarks/baziqa/zero_api_eval.py`  
年份结构 critic：`tools/bazi_ai/year_critic.py`

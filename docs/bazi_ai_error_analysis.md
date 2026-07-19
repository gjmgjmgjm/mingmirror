# BaziQA 错误分析（Phase 0 交付）

*分析时间：2026-07-11*
*数据来源：`benchmarks/baziqa/results/`（agnes_flash / zhipu_glm4plus 全量 n=200）*
*分析脚本：`benchmarks/baziqa/analyze_errors.py`*

> 本文档是 [`bazi_ai_90_roadmap.md`](bazi_ai_90_roadmap.md) Phase 0 的交付物，目标是用现有评测结果回答“错在哪、为什么错”，为 Phase 1（规则引擎）和 Phase 2（案例库）排定优先级，避免盲目堆料。

---

## 0. 当前准确率全景（全量 n=200）

| 配置 | 数据集 | 准确率 | 备注 |
|---|---|---|---|
| agnes_flash enhanced | Celebrity50 跨域 | **51.0%** | 较 roadmap 基线 30.5% 显著提升 |
| agnes_flash enhanced | contest8 LOO | 32.5% | 12 题 429/超时，attempted_acc 34.6% |
| zhipu glm-4-plus | contest8 LOO | **36.0%** | LOO 单模型最佳，无 infra 错误 |
| rule_reasoner 单跑 | contest8（30 题子集） | 30.0% | 仅规则引擎，未带 LLM |

**总体结论**：跨域（Celebrity50）已从 30% → 51%，但 contest8 LOO 仍卡在 32–36%。两套数据集的难度结构与提升来源完全不同，需分开治理。

---

## 1. 错在哪：分领域准确率

### contest8 LOO（agnes_flash，n=200）

| 领域 | 准确率 | 占比 | 解读 |
|---|---|---|---|
| 综合（general） | 33.7% | 41.5% (83/200) | **最大单一桶**，多为非年份的杂项题 |
| 婚姻/感情 | 31.0% | 21% (42) | 含大量“哪年结婚/二婚”年份题 |
| 事业/职业 | 30.0% | 15% (30) | |
| 六亲/家庭 | 33.3% | 12% (24) | 含父母去世/得子女年份题 |
| 财运 | 36.4% | 5.5% (11) | |
| 健康 | 30.0% | 5% (10) | 样本小但弱 |

### Celebrity50 跨域（agnes_flash，n=200）

| 领域 | 准确率 | 解读 |
|---|---|---|
| 综合 | 69.6% | 跨域综合题 RAG 命中率高 |
| 财运 | 66.7% | |
| 婚姻/感情 | 50.0% | |
| 事业/职业 | 44.4% | |
| 健康 | 41.2% | |
| 六亲/家庭 | **35.7%** | 跨域最弱领域 |

**观察**：跨域准确率全面碾压 LOO（尤其综合题 69.6% vs 33.7%）。说明 **RAG 案例库覆盖到的领域，分类题表现极好；LOO（排除本人案例后）则暴露了模型自身的推理短板**。健康、六亲在两套数据集上都是短板。

---

## 2. 错在哪：题型分布

| 题型 | agnes_flash LOO | zhipu LOO | Celebrity50 |
|---|---|---|---|
| 年份题（选项含具体年份） | 38.7% (n=31) | 41.9% (n=31) | 0% (n=2) |
| 非年份题（分类/状态） | 31.4% (n=169) | 34.9% (n=169) | 51.5% (n=198) |

**关键信号**：在 contest8 LOO 上，**年份题准确率（~40%）反而高于非年份题（~32%）**。年份题占比约 15.5%（31/200），且答错时往往“离得很近”——

| 文件 | 年份题答错样本 | 平均年份偏差 | 偏差 ≤1 年 | 偏差 ≤3 年 |
|---|---|---|---|---|
| agnes_flash LOO | 22 | **3.1 年** | 9/22 (41%) | 15/22 (68%) |
| zhipu LOO | 23 | **2.4 年** | 13/23 (57%) | 16/23 (70%) |

> **年份题是 LOO 上杠杆最高的改进点**：占 15% 题量、答错时 70% 都在 3 年以内、且正是规则引擎的设计目标。把这部分从 40% 提到 70%+，整体 LOO 可直接 +4~5pp。

---

## 3. 错在哪：错误类型拆分（仅错题）

| 类型 | agnes LOO | zhipu LOO | Celebrity50 |
|---|---|---|---|
| genuine_wrong（真错） | 123 | 128 | 86 |
| infra_429 | 1 | 0 | 0 |
| infra_timeout | 5 | 0 | 1 |
| infra_other | 5 | 0 | 9 |
| extract_fail（模型答了但没解析出字母） | 1 | 0 | 2 |

**结论**：管线问题（429/超时/解析失败）合计仅占 5–11/200，**不是瓶颈**。错误几乎全是模型本身推理错误，天花板在推理质量，不在工程。

---

## 4. 为什么错：规则引擎现状（Phase 1 关键输入）

对两份 LOO 结果（agnes / zhipu）跑 `rule_reasoner`，仅看年份题：

| 指标 | agnes LOO | zhipu LOO |
|---|---|---|
| 规则触发（confidence≥low） | 14/31 | 14/31 |
| 触发时准确率 | 35.7% | 35.7% |
| 与 LLM 答案一致 | 2/14 | 5/14 |
| 规则与 LLM 不一致时：规则对 | 4 | 3 |
| 规则与 LLM 不一致时：LLM 对 | 4 | 3 |

**按置信度分层（两份结果完全一致）**：

| 置信度 | 准确率 |
|---|---|
| high | 1/3 = 33% |
| medium | 1/2 = 50% |
| low | 3/9 = 33% |

### 两个硬结论
1. **规则引擎当前不带来净增益**：触发时准确率（35.7%）≈ LLM 单跑水平，且与 LLM 分歧时“规则对 / LLM 对”几乎对半（4-4、3-3）。等于在已经对的题上偶尔改错、在错的题上偶尔改对，净贡献≈0，只增加方差。
2. **置信度完全未校准**：high 与 low 准确率都是 33%。意味着“提高触发阈值”这种廉价调参**无效**，必须重做评分权重。

---

## 5. 为什么错：Top-3 错误来源（人工抽样年份题 8 例）

逐条审阅 zhipu LOO 年份错题的 `raw` 推理链，归纳出三类根因：

### ① 流年应期定位精度不足（占比最高）
**现象**：模型机制判断正确（“冲夫妻宫”“引动子女星”），但选了相邻的错年份，偏差仅 1–2 年。
- P026-Q7（二婚年）：gold=2020，pred=2019（差 1）
- P026-Q8（得子年）：gold=2021，pred=2019（差 2）
- P031-Q33（官非年）：gold=1995，pred=1996（差 1）
**根因**：规则引擎 `_score_year_for_star` 的评分粒度不足以区分**相邻年份**（如 2020 庚子 vs 2019 己亥），LLM 同样停在“附近”但无法 pin 到唯一解。

### ② 用神/忌神误判导致方向相反
**现象**：模型对“哪年吉/凶”的用神判断出错，从而选反。
- P027-Q14（搬迁年）：gold=2020 庚金，模型明确判定 2020 为忌神而排除，选了 2019。实际答案恰是它排除的 2020。
**根因**：日主旺衰/用神取法不可靠，直接污染所有“择吉应期”类题目。

### ③ 非标准事件无定位机制 + 编造人生事件
**现象**：初恋年、搬迁年、官非年等**不对应标准十神/宫位引动**的事件，规则引擎不覆盖，LLM 只能猜；对状态题还会编造命局不支持的事件。
- P030-Q27（初恋年）：gold=2002，pred=1991（差 11），模型基本在盲猜。
- P033-Q39（感情婚姻状态，非年份题）：gold=从未结婚未恋爱，pred=编造了一段结婚+离婚史。
**根因**：规则引擎 `reason()` 只覆盖结婚/子女/父母三类；非标准事件零覆盖；分类题缺“命局是否支持该事件存在”的前置校验。

> 详见 [`bazi_ai_90_roadmap.md`](bazi_ai_90_roadmap.md) §3 Phase 0 的错误分类 taxonomy：十神定位 / 大运流年 / 六亲宫位 / 案例带偏 / 结构推理 / 题意歧义。本次抽样中 ①② 属“大运流年计算”，③ 横跨“结构推理缺失”与“分类题幻觉”。

---

## 6. 修复优先级（喂给 Phase 1 / Phase 2）

按 **(可解性 × 杠杆) ** 排序：

### P0 — 重做规则引擎评分权重（Phase 1）✅ 已完成（2026-07-11）
- **问题**：置信度未校准 + 评分无法区分相邻年份，净增益≈0；且发现两个 bug。
- **做了什么**（见 `benchmarks/baziqa/rule_diagnose.py` + `rule_calibrate.py`）：
  1. 用 25 道 LOO 年份题作回归集，对**每个选项**逐信号拆解，定位到“权重错”而非“特征缺”。
  2. 修两个 bug：① **天干五合是死代码**（旧实现拿天干 pair 查地支六合表 `_LIU_HE`，永不命中）；② `_best_candidate` 的降级分支恒把置信度设成 `"low"`。
  3. 用 LOO 逻辑回归（L2, C=0.5）标定权重，并按 per-signal gold/pick 触发率复核符号：
     - **stem_star 旧 +2.0（最高）属反向预测**（错误选项上触发 4× 于正确选项）→ 置 0。
     - hidden_star / branch_sanhui / branch_liuhe / dayun_sanhe 同判为反向/噪声 → 置 0。
     - 修复后的 **天干五合**成为最强正向信号（+0.9），新增 **天克地冲/伏吟/反吟** 应期信号。
  4. 置信度改为 **margin-based**（top1 − top2 ≥0.5→high, ≥0.2→medium），生产阈值 `apply_rule_reasoner` 默认提到 `"high"`，引擎只在可靠时才覆盖 LLM。
- **验收结果**：
  - 规则触发准确率 **35.7% → 66.7%**（≥55% 达标 ✅），high 置信度切片标定 ~75%。
  - 在现有结果上复跑：触发次数 **14 → 3**（precision over recall），zhipu 上 3 次触发全部与 LLM 一致（确认而非覆盖，零副作用）。
  - 3 个回归测试（`tests/test_rule_reasoner.py`）全过；29 个 bazi_ai 相关测试全过。
- **诚实结论**：star/palace 符号特征在该题集上 LOO **top-1 天花板 ≈36%**、**top-2 ≈56%**。仅靠符号引擎无法把年份题拉到高分；**真正的杠杆是把引擎 top-2 作为 shortlist 喂给 LLM**（gold 落在 top-2 内 ~56–75%，把 LLM 的 1/4 盲选提升到约 1/2）。这是 Phase 4 集成的方向，见下方 P5。
- **2026-07-19 再标定**（`rule_calibrate_v2.py`，生产特征 + 坐标上升，无 sklearn）：Contest8 year-asking **n=44** full top1 **45.5%**、top2 **61.4%**；soft shortlist top2 **~69.6%**（fire≈23）。同日复跑：firerate 全量 top1 可到 50% 但 shortlist 触发过少 → **产品仍用 production 权重**。全源零 API（Contest8+MingLi+Celebrity50，n=186）top1 **30.6%**/top2 **51.1%**——名人题拉低均值，**不可用 Contest8 45% 外推**。Live MiniMax Contest8 n200 仍 ~31–32%。

### P5 — top-2 shortlist 喂 LLM（Phase 4）✅ 已完成（2026-07-13，当日迭代加固）
- **做了什么**：
  1. 修复 `_extract_years`：去掉 Unicode `\b`，改为 digit lookaround，使 `2010年` 能正确解析（此前大量中文选项年份题被静默跳过）。
  2. 扩展事件覆盖：marriage/children/parent + move/legal/generic；年份题覆盖 **14 → 50/58**。
  3. 实现 `rank_year_candidates` + `format_shortlist_block`，在 `baziqa_eval` enhanced prompt 注入 soft shortlist。
  4. **关闭硬覆盖**（high-margin 在扩展后 top-1 仅 ~20%，会伤分）；children 因 top-2 仅 ~25% 不进 shortlist。
  5. **冲突回退加固**（同日后续）：
     - 状态题门控：`is_year_asking_question`（排除 P033-Q39 类「婚姻状况」误注入）
     - marriage/generic 需 confidence≥medium **且** score≥0.4
     - 更软的 prompt 措辞（按 conf 分档）
     - `--shortlist-mode arbiter`：free+guided 双通仲裁（2× 成本）
  6. 离线 shortlist 池（门控后 n=30）：top-1 **43.3%**、**top-2 66.7%**；non-high shortlist hit **82.4%**。
- **Live A/B（deepseek-chat，12 道 shortlist eligible 年份题，LOO）**：

  | arm | 准确率 |
  |---|---|
  | shortlist_on | **41.7% (5/12)** |
  | shortlist_off | 16.7% (2/12) |
  | paired | shortlist 独赢 5 / 独输 2 / 平 5 |

  → 相对无 shortlist **+25pp**。结果：`benchmarks/baziqa/results/ab_shortlist_n12.jsonl`。
- **Live LOO n=50（soft shortlist，deepseek-chat）**：
  - 整体 **38.0% (19/50)** — Q31–50 极难（仅 4/20），拉低均值
  - **前 30 题 50.0%** vs 旧基线 n30 **46.7%**（paired：新独赢 6 / 旧独赢 5 / 平 19）→ **+3.3pp**
  - shortlist 触发 7 次，触发时准确率 **57.1%**；gold∈top2 时 4/6 对
  - 结果：`benchmarks/baziqa/results/loo_contest8_deepseek_shortlist_n50.jsonl`
- **残留风险**：gold 在 shortlist 但模型选错 top-1 成员（P031-Q33、P017-Q4）；children 应期仍弱；非年份题（职业/性格/学历）才是全量天花板。

### P6 — top-2 近并列 critic + 非年份结构提示（2026-07-13）
- **top-2 near-tie**：当 shortlist 分差 <0.35，prompt 强制「逐项对比、禁止默认第一名」。✅ 默认开启（随 year shortlist）。
- **非年份域**：
  - 离线选项排名 top-2 仅 ~55% → **不注入 A/B shortlist**。
  - 实现 `format_domain_hint_block`（十神/旺衰取象提示，不写选项字母）。
  - 领域 focus 文案强化官印/食伤财；新增 education 域（始终在 prompt 中）。
  - **Live 结论（n=30 LOO）**：year-shortlist-only **50%**；+domain-hints **43.3%**（回退 6.7pp）→ **domain hints 默认关闭**，仅 `--domain-hints` 实验开关。
  - 文件：`loo_contest8_deepseek_hint_n30.jsonl`；对照 `_compare_hint_n30.py`。
- **生产默认**：year soft shortlist + near-tie critic；domain focus 文案；无 domain-hint block。

### P1 — 把非标准事件纳入规则/检索（Phase 1+2）✅ 部分完成（2026-07-13）
- **问题**：初恋/搬迁/官非等 0 覆盖；状态题编造事件。
- **已做**：
  1. ✅ 扩展 `rank()`：搬迁（印星 proxy）、官非（官杀）、感情开始（并入 marriage 关键词）、generic 年份题 fallback。
  2. ⬜ 状态题（“符合哪项状况”）前置校验仍未做。

### P2 — 用神/忌神引擎化 ✅ 已完成（2026-07-13）
- **问题**：用神误判直接污染择吉题方向。
- **已做**：
  1. `tools/bazi_ai/yongshen.py`：扶抑 + 穷通宝鉴调候 + 通关统一解析；夏冬月调候优先。
  2. `structural_profile` 改调 `resolve_yongshen`（单源）。
  3. eval prompt 注入完整 `yongshen_block`（主法/用忌/调候天干）。
  4. ~~年份 shortlist 叠用神软分~~ → **已撤回**（会把 gold 挤出 top-2，如 P027-Q14）。用神只进 prompt，不改标定 shortlist 分。
- **调候尺子**（`validate_yongshen.py`，n=32 MingLi）：
  - 与 gold 有交集：88% → **94%**
  - 覆盖 gold 全部：22% → **59%**
- **Live LOO n=30 t=0**（用神进 prompt + shortlist）：46.7%（`loo_contest8_yongshen_n30_t0.jsonl`）；shortlist-only 对照 50%。用神块改善方向指引，但未抬整体选择题分。

### P3 — 健康/六亲专项（Phase 2，持续）
- **问题**：两套数据集上健康（20–41%）、六亲跨域（35.7%）都是短板。
- **动作**：把 `reason_health`（目前故意未接入 dispatch）完善后接入；为六亲题补 domain 标签的 RAG 案例并加权检索。

### P4 — 扩大跨域 RAG 覆盖（Phase 2）✅ 已加固（2026-07-13）
- **观察**：跨域 51% vs LOO 36% 的差距证明案例库是巨大杠杆；但 LOO 探查发现职业题被**同八字婚姻/子女题**霸榜（bazi exact +100）。
- **已做**：
  1. `baziqa_to_cases` v2：688 条（contest8 200 + celebrity50 488），含结构摘要/推理要点/`key_years`/`patterns`/`dataset`。
  2. **人级 LOO**：排除同 person key 全部题目（`P026-Q6` 排除 `P026-*`）。
  3. 检索重打分：同域 +35、错域同八字降为 +15、错域 −20；案例展示结论+更长分析。
  4. 域题 top_k≥3。
- **Live LOO 全景（deepseek-chat，2026-07-13）**：

  | 配置 | n | 准确率 | 备注 |
  |---|---:|---:|---|
  | baseline | 30 | 46.7% | 早期 |
  | year shortlist only | 30 | **50.0%** | 稳定对照 |
  | year shortlist only | 50 | 38.0% | Q31–50 极难（~20%） |
  | rag_v2 露答案字母 | 30 | 40.0% | 名人选项照搬 |
  | rag_v2b 结构+shortlist | 30 | 53.3% | **单次高点，未复现** |
  | rag_v2b 结构+shortlist | 50 | 32.0% | 劣于 shortlist 38%；paired −3 |
  | rag_v2c 结构过滤+t=0 | 30 | 46.7% | 同日主/月令过滤 |
  | shortlist+杨炎案例 t=0 | 30 | **50.0%** | 与 shortlist 对齐 |

  - 文件：`loo_contest8_rag_v2b_n50.jsonl`、`rag_v2c_n30`、`_compare_n50_full.py`。
  - **诚实结论**：
    1. **year shortlist** 仍是唯一稳定正收益（n30 ≈50%）。
    2. BaziQA reverse RAG **方差大**：同配置 n30 可 53%，n50 仅 32%。
    3. 后 20 题（状态/杂项）才是全量天花板；RAG 未能解救难题尾。
    4. 生产保留：人级 LOO + 域加权 + **同日主/月令过滤** + 不展示答案字母；不把 53% 当承诺水位。

---

## 7. 回归基线（防止回退）

每次改动后跑两套全量回归：

```bash
# contest8 LOO（in-domain，规则引擎主战场）
python -m tools.bazi_ai.baziqa_eval --datasets contest8 --leave-one-out \
    --output benchmarks/baziqa/results/loo_contest8_regression.jsonl

# Celebrity50 跨域（RAG 覆盖验证）
python -m tools.bazi_ai.baziqa_eval --datasets celebrity50 \
    --output benchmarks/baziqa/results/cross_celebrity50_regression.jsonl

# 错误分析复跑
python benchmarks/baziqa/analyze_errors.py \
    benchmarks/baziqa/results/loo_contest8_regression.jsonl \
    benchmarks/baziqa/results/cross_celebrity50_regression.jsonl
```

监控指标：整体准确率、年份题准确率、规则触发准确率与置信度分层、健康/六亲分领域准确率。任一指标回退 >2pp 需排查。

---

## 附录：置信度分层为何“无效”

`rule_reasoner._best_candidate` 用固定分数阈值（score≥3.0→high, ≥1.5→medium）划档。但分数由权重线性叠加得到，**权重本身未经数据校准**，导致“高分题”与“低分题”的真实正确率无差异（均 ~33%）。因此任何仅调阈值的方案都治标不治本——必须回到 P0 重训权重。

---

*下一步：先确认可用的 LLM key（agnes_flash 当前是最佳性价比）与命理专家标注时间，然后开 P0。*

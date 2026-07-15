# BaziQA 准确率冲击 90% 项目推进计划

## 1. 目标与现状

### 目标
将 `tools/bazi_ai` 在 BaziQA `contest8` 上的 leave-one-out 准确率从当前约 **27–36%** 提升至 **90%+**，并同步提升 Celebrity50 跨域表现。

### 当前基线

| 模型 / 配置 | 数据集 | 准确率 | 备注 |
|---|---|---|---|
| Zhipu glm-4-plus v1 | contest8 LOO | 36.0% | 早期 enhanced prompt |
| Zhipu glm-4-plus v2 | contest8 LOO | 33.0% | 硬过滤 + 大运流年 |
| Zhipu glm-4-plus | Celebrity50 | 30.5% | 含 429 错误样本 |
| MiniMax abab6.5s-chat baseline | contest8 LOO | 2.0% | 176/200 题拒绝回答 |
| MiniMax abab6.5s-chat + v3 | contest8 LOO | **27.5%** | 软加权 + prompt 降噪 + ensemble=3 |

> 结论：prompt/RAG/ensemble 能把同一模型从 2% 拉到 27.5%，但想继续冲高，必须走 **领域专用模型 + 结构化数据 + 规则引擎** 路线。

---

## 2. 核心思路

把 LLM 从“凭感觉猜选择题”改造成“会查八字结构、会算大运流年、会参考相似案例的命理推理器”。

关键路径：

```
数据层 → 结构化事实层 → 检索增强层 → 规则引擎层 → 模型推理层 → 多模型验证层
```

---

## 3. 分阶段推进

### Phase 0：诊断（1–2 天）✅ 已完成（2026-07-11）
**目标**：搞清楚现在错在哪里，避免盲目堆料。

- [x] 将 Zhipu / MiniMax / agnes_flash 的预测结果按错误类型分类：
  - 十神定位错误
  - 大运/流年计算错
  - 六亲/宫位对应错
  - 被错误案例带偏
  - 模型没按结构事实推理
  - 题目理解/选项歧义
- [x] 输出 [`docs/bazi_ai_error_analysis.md`](bazi_ai_error_analysis.md)，给出每类错误占比和修复优先级。
- [x] 复用脚本：`benchmarks/baziqa/analyze_errors.py`（支持 `--json` 纳入回归）。

**验收**：✅ 明确 Top-3 错误来源——① 流年应期定位精度不足；② 用神/忌神误判致方向相反；③ 非标准事件无定位机制+状态题编造事件。并发现规则引擎净增益≈0、置信度未校准（详见 Phase 1 P0）。

---

### Phase 1：规则引擎兜底（3–5 天）
**目标**：把“可符号化”的题目从 LLM 手里接管过来，降低模型负担。

- [x] 实现 `tools/bazi_ai/rule_reasoner.py`（结婚/子女/父母年份题）。
- [x] 规则输出“候选答案 + 置信度”，LLM 只在候选上做选择或补充。
- [x] 对高置信度规则结果直接输出，跳过 LLM。
- [x] **P0 权重标定（2026-07-11）**：LOO 逻辑回归重做权重，修天干五合死代码 bug、修 `_best_candidate` 置信度 bug、新增天克地冲/伏吟/反吟应期信号、置信度改 margin-based、生产阈值提到 high。详见 [`docs/bazi_ai_error_analysis.md`](bazi_ai_error_analysis.md) §6 P0。
  - 触发准确率 35.7% → 66.7%；触发次数 14 → 3（precision over recall）。
  - **天花板发现**：star/palace 符号特征 LOO top-1 ≈36%、top-2 ≈56%。下一步杠杆 = top-2 shortlist 喂 LLM（Phase 4），而非继续堆符号规则。
- [x] **用神引擎（2026-07-13）**：`tools/bazi_ai/yongshen.py` 扶抑+调候+通关；调候交集 94%、覆盖 gold 59%（MingLi n=32）；接入 prompt + 年份 soft 评分。

**验收**：规则单独覆盖 30% 以上题目，且这部分准确率 > 80%。⚠️ 未达成——符号特征 top-1 天花板 36%，需转向 shortlist+LLM（见 Phase 4）与用神引擎（见 error_analysis P2）。

---

### Phase 2：案例库升级（持续）
**目标**：让 RAG 能召回“真正相关且带解析”的案例。

- [x] 把 BaziQA 正确答案反向生成 `analysis_corrected`，形成结构化 case（`baziqa_to_cases` v2）。
- [x] 把 Celebrity50 同样解析并接入 `extra_cases_paths`（config 已挂 `cases_baziqa.jsonl`，688 条）。
- [x] 标签：domain / key_years / patterns(strength, useful/taboo) / dataset；dayun_range 与 relations 待补。
- [x] `engine._case_relevance` 域加权 + 错域同八字降权；**人级 LOO** 排除同人全部题。
- [x] 职业题探查：修复前召回同人婚姻题；修复后 top 为 celebrity career cases。

**验收**：检索到的 Top-2 case 与当前题同领域比例 > 70%。✅ 职业探针 3/3 同域。  
**Live（诚实）**：
- 单次 rag_v2b n30 曾到 53.3%，**n50 回归仅 32%**（shortlist-only n50=38% 更稳）。
- 生产默认：year shortlist + 人级 LOO + 同日主/月令 case 过滤；不以 53% 为承诺水位。
- 对照：`_compare_n50_full.py`。

---

### Phase 3：SFT/LoRA 训练（2–4 周）
**目标**：让模型学会按八字结构事实做 CoT 推理。

- [ ] 构建训练样本，格式示例：

```json
{
  "bazi": "甲午 丁卯 癸酉 庚申",
  "gender": "male",
  "birth_date": "1954-03-18",
  "birth_time": "15:00",
  "question": "命主哪年到香港?",
  "options": ["1960 庚子", "1962 壬寅", "1968 戊申", "1971 辛亥"],
  "structural_facts": { "day_master": "癸", "strength": "偏弱", ... },
  "dayun_relevant": ["6-16 戊辰", "16-26 己巳", "26-36 庚午"],
  "liunian_relevant": ["1968 戊申", "1971 辛亥"],
  "similar_cases": [...],
  "reasoning": "日主癸水偏弱，喜金水。驿马星为亥，1971 辛亥年亥水驿马被引动，且...",
  "answer": "D"
}
```

- [ ] 使用 QLoRA 在 7B/13B 底座上训练（推荐底座：Qwen2.5-14B-Instruct、DeepSeek-V2.5、GLM-4-9B-Chat）。
- [ ] 训练脚本放在 `scripts/train_bazi_lora.py`。
- [ ] 训练后接入 `tools/bazi_ai/engine.py` 的可选本地模型路径。

**验收**：在 contest8 验证集上微调后模型准确率 > 65%（第一阶段），最终目标 > 80%。

---

### Phase 4：多模型验证与集成（1 周）
**目标**：压方差、纠错。

- [x] **规则 top-2 shortlist → LLM**（2026-07-13）：`rank_year_candidates` + prompt 注入；live A/B 年份题 16.7%→**41.7%**（+25pp，n=12）。详见 [`bazi_ai_error_analysis.md`](bazi_ai_error_analysis.md) §6 P5。
- [x] **冲突回退**（2026-07-13）：year-asking 门控 + score/conf 门控 + soft 措辞 + `arbiter` 双通模式。
- [x] **LOO n=50 回归**：前 30 题 46.7%→**50.0%**（+3.3pp）；全 50 题 38%（后 20 题仅 20%，非 shortlist 回退）。
- [ ] 实现 `tools/bazi_ai/ensemble_debate.py`：
  - 2–3 个不同模型独立推理。
  - 一个 critic 模型检查各答案与结构事实是否一致。
  - 不一致时触发规则引擎重判。
- [ ] 对低置信度题目触发“保守回答”或标记人工复核。
- [ ] shortlist 内二选一：当 gold 常在 runner-up 时，用结构事实 critic 在 top-2 内决胜。

**验收**：相比单模型提升 3–5 pp。✅ 年份子集 +25pp；前 30 LOO +3.3pp。

---

### Phase 5：90% 冲刺（持续迭代）
**目标**：把剩余 10–15% 的 hard case 啃下来。

- [ ] 针对错误分析中反复出现的问题类型，补充专项规则 + 专项训练数据。
- [ ] 引入更大底座（70B 级别或 GPT-4o/Claude 级 API）。
- [ ] 建立自动回归测试：每次改动后跑 `contest8 LOO` + `Celebrity50 cross-domain`，防止回退。

---

## 4. 需要的资源

| 资源 | 用途 | 优先级 |
|---|---|---|
| 有余额的 Zhipu / DeepSeek / Claude / OpenAI key | 跑基线、做多模型验证 | 高 |
| GPU（24G+ 显存）或云训练额度 | LoRA 微调 | 高 |
| 命理专家标注时间 | 清洗案例、校验规则、标注 CoT | 高 |
| BaziQA + Celebrity50 结构化解析 | 训练数据 | 中 |

---

## 5. 风险与应对

| 风险 | 应对 |
|---|---|
| 90% 对命理选择题本身可能超出当前 LLM 上限 | 先验证最强模型 + 完美 prompt 的上限，再决定投入规模 |
| 案例库噪声大，RAG 起反作用 | 严格人工校验 Top case，做 domain + pattern 过滤 |
| 微调过拟合到 BaziQA | 训练集混入 Celebrity50，并留 contest8 作为独立测试集 |
| 规则引擎覆盖不够 | 规则只处理高置信度 case，其余交给模型 |

---

## 6. 下一步行动

1. ~~Phase 0 错误分析~~ ✅ 已完成（见 [`bazi_ai_error_analysis.md`](bazi_ai_error_analysis.md)）。
2. ✅ DeepSeek key 已就位，**默认模型已切到 deepseek-chat**（config.yml）。contest8 LOO 前 30 题 46.7%，超 glm-4-plus(43.3%)/agnes(33.3%)/kimi(26.7%)。
3. 如果 GPU 资源到位，同步开始 Phase 3 训练数据准备。

---

## 7. 真人算命方向（2026-07-11 战略调整）

> 目标从"BaziQA 选择题刷分"调整为"**给真人算命，结构层 90%+**"。选择题只是廉价代理指标，且**不奖励取象**——取象的丰富度只在开放式真断里体现。

### 已落地
- **模型**：默认 deepseek-chat（config.yml），连通性 + baseline 已验。
- **取象系统**（`engine.py` 真断面，非 eval）：
  - 系统提示从"子平为主"改为"**取象优先，公式为辅**"，并要求**两步取象推理**（先列≥3–5 象→再择优+排除理由）。
  - 婚姻应期编码**盲派象法**（含用户口诀"比劫合入夫妻宫→找比劫年"、桃花引动、冲开合绊），不再只认配偶星。
  - 知识截断 `max_chars` 10K→40K，盲派 rulebook 终于能完整进上下文（之前 88KB 只进 10KB）。
  - config 改用 `rulebook_compact.md` + `mnemonics.md` + `knowledge_final.md`。
- **性别管道修复**：`cli.py` 加 `--gender`，analyze_bazi 本支持但 CLI 漏传（默认 male，导致女命六亲/妇科全错）。已验证：女命现在能断出"妇科"（原断只有呼吸/肾）。

### 诚实结论（关键）
1. **DeepSeek-chat 能做取象**（连通测试即写出"寒江沉铁锁"），但**在完整 schema 下会压缩**，两步取象不会显式展开。要真正显现，需 ① 用 **deepseek-reasoner（R1）**（慢思考更利于多步取象），或 ② 在输出 schema 里**加一个 `quxiang` 专字段**强制枚举。
2. **无脑全注入盲派知识有害**（contest8 全注入 40% < RAG 46.7%）→ 知识必须**按领域条件注入**（六亲题才塞六亲规则）。
3. **财富等级分歧**：大师断"千万"，引擎断"中产"。大师偏激进；引擎偏保守。**无真人反馈无法裁决**——这正是需要"过去验证"的原因。

### 验证尺子（替代选择题）
- `bazi_knowledge/` 的杨炎案例自带**命主分析（大师原断）**，是天然的过去验证材料。
- 待建：**真人验证 harness**——跑 `analyze_bazi` → 抽取财富等级/格局/六亲/应期 → 与大师原断比对（结构层命中率才是 90% 目标的真尺子）。

### 下一步候选
- A. 取象专字段 + deepseek-reasoner，让两步取象真正显现。
- B. 真人验证 harness（结构层命中率）。
- C. 确定性层补全：用神引擎 + 财富等级/格局规则（不让模型取）。
- D. 按领域条件注入知识（六亲/career/health 各自的取象字典）。

---

*文档创建时间：2026-07-08*
*最后更新：2026-07-13（Phase 4 shortlist + 年份解析修复，live A/B +25pp）*
*负责人：待指定*

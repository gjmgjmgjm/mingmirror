# AI 八字分析模块

基于 DeepSeek + RAG 的八字分析系统。

## 快速开始

### 1. 准备案例库

如果你已经有 `bazi_knowledge/杨炎_knowledge_final.md` 这类知识库文件：

```bash
python -m tools.bazi_ai.case_builder \
    -k bazi_knowledge \
    -o bazi_knowledge/cases.jsonl \
    -g bazi_glossary.json
```

### 2. 配置 DeepSeek API Key

```bash
# Windows
set DEEPSEEK_API_KEY=sk-...

# Linux/macOS
export DEEPSEEK_API_KEY=sk-...
```

### 3. 分析八字

```bash
python -m cli.main --analyze-bazi "甲子 丙寅 戊辰 庚午"

# 带具体问题
python -m cli.main --analyze-bazi "甲子 丙寅 戊辰 庚午" --bazi-question "事业财运"
```

### 4. 评测一致性

```bash
python -m tools.bazi_ai.evaluator "甲子 丙寅 戊辰 庚午" -r 5
```

## 文件说明

| 文件 | 作用 |
|------|------|
| `case_builder.py` | 把 Markdown 知识库解析成结构化 `cases.jsonl` |
| `engine.py` | DeepSeek 分析引擎，含 RAG 检索和结构化输出 |
| `cli.py` | 独立命令行工具 |
| `evaluator.py` | 一致性评测工具 |

## 准确率提升路径

1. **扩充案例库**：案例越多，RAG 越准
2. **优化 rule_primer.md**：八字规则手册越清晰，AI 推理越稳
3. **收集命主反馈**：把反馈加入案例库，形成闭环
4. **收紧 Prompt**：根据一致性评测结果调整输出约束

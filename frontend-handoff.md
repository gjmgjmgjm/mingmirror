# 八字前端开发交接文档

> 本文件供负责独立现代前端的窗口/开发者使用。后端准确率相关改动已完成并通过测试。

---

## 1. 后端 API（已由我完成）

启动 server：

```bash
pip install -r requirements-bazi.txt  # 如需视频 OCR 功能
pip install fastapi uvicorn pydantic  # server 可选依赖
python -m cli.main --serve --serve-port 8000
```

### 1.1 八字分析

```http
POST /api/v1/bazi/analyze
Content-Type: application/json

{
  "bazi": "乙卯 戊寅 庚子 丙子",
  "question": "事业财运",
  "top_k": 3
}
```

响应：

```json
{
  "bazi": "乙卯 戊寅 庚子 丙子",
  "result": {
    "basic_info": {
      "bazi": "乙卯 戊寅 庚子 丙子",
      "day_master": "庚",
      "month_branch": "寅",
      "pattern": "伤官格",
      "useful_gods": ["水", "木"],
      "taboo_gods": ["金", "土"]
    },
    "reasoning": "...",
    "domain_analysis": {
      "career": "...",
      "wealth": "...",
      "marriage": "...",
      "health": "..."
    },
    "summary": ["...", "..."],
    "confidence": "high|medium|low",
    "caveats": ["..."],
    "rule_warnings": ["..."]  // 可选
  }
}
```

特殊字段：
- `result._mock === true`：未配置 `DEEPSEEK_API_KEY`，仅返回 mock 占位分析
- `result.error`：输入八字无效
- `result.parse_error === true`：模型输出 JSON 解析失败

### 1.2 获取案例库

```http
GET /api/v1/bazi/cases
```

返回用于 RAG 的案例列表，前端可用来做「相似案例」展示。

### 1.3 视频 OCR 提取八字

```http
POST /api/v1/bazi/extract
Content-Type: application/json

{
  "user_dir": "./Downloaded/杨炎",
  "duration": 60,
  "interval": 2.0
}
```

注意：该端点会同步阻塞直到 OCR 完成，大目录可能较慢。前端建议 polling 或先返回 job_id（如需异步可再协商）。

### 1.4 反馈

```http
POST /api/v1/bazi/feedback
Content-Type: application/json

{
  "bazi": "乙卯 戊寅 庚子 丙子",
  "correct": true,
  "note": "事业判断很准"
}
```

---

## 2. 推荐前端技术栈

- **框架**：React 18 + TypeScript（或 Vue 3 + TypeScript）
- **构建**：Vite
- **UI 组件**：Ant Design / shadcn-ui / Tailwind CSS
- **HTTP 客户端**：axios
- **状态管理**：Zustand 或 React Context（项目规模不大，不需要 Redux）

---

## 3. 建议页面结构

### 页面 1：八字分析页（核心）

布局参考：

```
+------------------+------------------+
|   输入区域        |   四柱排盘        |
|  - 八字输入框     |   （可视化）       |
|  - 问题输入框     |                  |
|  - 分析按钮       |   日主/月令高亮    |
+------------------+------------------+
|   分析结果        |   参考案例        |
|  - 格局/用神/忌神 |   - 相似八字列表   |
|  - 分领域断语     |   - 命理师分析摘要 |
|  - 置信度/caveats |                  |
+------------------+------------------+
|   反馈按钮        |                  |
+------------------+------------------+
```

#### 四柱排盘可视化建议

八字：`乙卯 戊寅 庚子 丙子`

| 年柱 | 月柱 | 日柱 | 时柱 |
|:--:|:--:|:--:|:--:|
| 乙 | 戊 | **庚** | 丙 |
| 卯 | 寅 | **子** | 子 |
| 比肩 | 偏印 | 日主 | 七杀 |

- 日主（日柱天干）加粗/高亮
- 月令（月柱地支）用不同背景色
- 十神可hover显示

### 页面 2：案例库管理

- 表格展示 `cases.jsonl`
- 支持按 `bazi` / `pattern` / `day_master_strength` 筛选
- 支持编辑 `useful_gods` / `taboo_gods` / `conclusions`
- 「重新生成 embedding 缓存」按钮（调用后端待补充，或先手动运行 `python -m tools.bazi_ai.embeddings`）

### 页面 3：批量 OCR

- 选择 `Downloaded/{作者}` 目录
- 显示进度条
- 展示 `bazi_manifest.json` 结果

---

## 4. 前端开发约束

1. **不要修改 `tools/bazi_ai/` 和 `tests/test_bazi*.py`**：这些属于后端准确率模块，由我维护
2. **不要修改 `server/app.py` 中现有下载相关端点**：新增的 bazi 端点已加好，前端只调用不修改
3. **独立目录**：建议放在 `frontend/` 或 `web/` 目录下，与 Python 后端解耦
4. **构建产物**：`npm run build` 输出到 `frontend/dist/`，可配置 FastAPI 托管静态文件（如需我后续加 `app.mount('/static', ...)`）
5. **环境变量**：前端通过 `VITE_API_BASE_URL=http://localhost:8000` 连接后端

---

## 5. 启动开发环境

后端：

```bash
python -m cli.main --serve --serve-port 8000
```

前端（示例）：

```bash
cd frontend
npm install
npm run dev
```

---

## 6. 当前数据状态

- `bazi_knowledge/cases.jsonl`：7 条有效唯一八字案例
- 建议前端初始化时调用 `GET /api/v1/bazi/cases` 展示案例数量
- 后续扩充案例需通过 `python -m tools.bazi_ai.case_builder` 重建

---

## 7. 如需后端配合

如果前端需要以下能力，请告诉我或后端负责人：

- 用户登录/鉴权
- 分析历史记录持久化
- 案例库增删改 API
- embedding 缓存重建 API
- WebSocket 实时 OCR 进度
- 静态文件托管（`frontend/dist`）

---

## 8. 配置项

`config.yml` 中 `bazi_ai` 段落：

```yaml
bazi_ai:
  enabled: true
  cases: "./bazi_knowledge/cases.jsonl"
  knowledge_base: "./bazi_knowledge/rule_primer.md"
  embedding_cache: "./bazi_knowledge/cases.pkl"
  top_k: 3
  model: "deepseek-chat"
  ensemble_runs: 1  # 改为 3 可开启多轮投票
  temperature: 0.2
```

环境变量：

```bash
DEEPSEEK_API_KEY=sk-...
```

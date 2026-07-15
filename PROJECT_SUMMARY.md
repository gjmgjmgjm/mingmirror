# 项目实现总结（dy-downloader）

## 1. 项目概览

- **项目名称**: Douyin Downloader (`dy-downloader`)
- **版本**: `2.0.0`
- **更新时间**: `2026-07-15`
- **当前状态**: ✅ **下载器主线**成熟可用(642+ 测试,维护态);**命镜命理主线**活跃开发——八字 / 紫微 / 七政四余 / 多命理融合 + React Web UI + REST API 已落地,结构层准确率见 §3.1 记分板。`like/mix/music` 浏览器兜底、REST server 增强(取消/SSE/配置覆盖)、完整 CI/CD 均已就绪


## 2. 当前实现能力（按代码现状）

### 2.1 已支持

- 单个视频下载（`/video/{aweme_id}`）
- 单个图文下载（`/note/{note_id}`）
- 抖音短链下载（`https://v.douyin.com/...`，会先解析后下载）
- 用户主页发布作品批量下载（`/user/{sec_uid}` + `mode: [post]`）
- 无水印优先下载，支持封面/音乐/头像/原始 JSON
- 并发下载、重试、速率限制
- 基于作品发布时间（`create_time`）生成文件名/目录日期前缀（`YYYY-MM-DD_...`）
- 生成独立下载清单文件 `download_manifest.jsonl`
- 时间过滤（`start_time` / `end_time`）
- 数量限制（当前对 `number.post` 生效）
- SQLite 去重与增量下载（当前对 `increase.post` 生效）
- 翻页受限时的浏览器兜底（`post`/`like`/`mix`/`music` 模式均已接入 Playwright 兜底）
- REST API server 模式（`--serve`）：job 提交/查询/列表/取消、SSE 状态流、运行时配置覆盖、健康探针
- CI/CD：GitHub Actions 工作流覆盖 lint、Python 3.9–3.12 矩阵测试、跨平台兼容、可选依赖、Docker 构建验证

### 2.2 已新增（本次实现）

- 用户点赞下载（`mode: [like]`）
- 用户合集下载（`mode: [mix]`）与单合集链接（`/collection/{mix_id}`、`/mix/{mix_id}`）
- 用户音乐模式下载（`mode: [music]`）与单音乐链接（`/music/{music_id}`）
- `number.like` / `number.mix` / `number.music` 与 `increase.like` / `increase.mix` / `increase.music` 生效
- `number.allmix` / `increase.allmix` 兼容保留，并在加载时归一化到 `mix`


## 3. 架构与模块

```text
dy-downloader/
├── cli/               # CLI 入口与展示
├── core/              # 下载主流程、URL解析、API客户端
├── storage/           # 文件、元数据、数据库
├── auth/              # Cookie / token 管理
├── control/           # 限速、重试、并发队列
├── config/            # 配置加载与默认配置
├── server/            # FastAPI REST server（下载任务 + 命理 API）
├── tools/             # 独立工具：八字/紫微/七政/多命理融合
├── web/               # React + Vite 命镜前端（已构建 dist/）
├── tests/             # Pytest 测试套件
└── utils/             # 日志与通用工具
```


### 3.1 命镜（MingMirror）命理系统现状

> 产品定义见 [`docs/PRD-mingmirror.md`](docs/PRD-mingmirror.md);推进路线见 [`docs/bazi_ai_90_roadmap.md`](docs/bazi_ai_90_roadmap.md);尺子速查见 [`docs/README.md`](docs/README.md)。

**核心方法论(已验证)**:确定性结构事实(排盘 / 格局 / 用神 / 六亲)→ **计算 + 注入专字段** → LLM 采纳。可符号化的判断不让模型自行拍脑袋。

**准确率记分板**(由 `python benchmarks/baziqa/accuracy_report.py` 实时生成,零 API;最近运行 2026-07-15):

| 维度 | 准确率 | gold 性质 |
|------|--------|-----------|
| 排盘 | 100% (32/32) | ✅ 真实(iztro) |
| 用神 | 90% (83/92 大n) | ✅ 真实(穷通宝鉴) |
| 格局 | 100% | 确定性注入(月令定格,非 accuracy) |
| 忌神 | 92% | 确定性注入(规则引擎,非 accuracy) |
| 旺衰 | 75% | LLM-引擎一致性(非 accuracy) |
| 六亲强弱 | 91% (10/11 det) | 真实(杨炎 gold,样本小) |
| 具体事件/年份 | 0% 开放式 / 40% MCQ | 真实(名人) |

> **「结构层 90%」= 有独立 gold 的维度**:排盘 100%、用神 90%(大 n)、六亲 91%(det)均已达成;格局/忌神(确定性注入)、旺衰(LLM-引擎一致性)**非 accuracy,不计入**。六亲 det n 偏小(11),det/e2e 口径历史在 58–91% 间浮动;事件层开放式 ≈0% 是物理天花板,产品输出**趋势**而非断言。

**已落地能力**:四柱校验、领域感知 RAG + embedding、规则引擎兜底(结婚/子女/父母应期)、用神引擎(扶抑+调候+通关)、`quxiang` 取象专字段、top-2 shortlist→LLM、多轮 ensemble;紫微斗数 / 七政四余(Swiss Ephemeris,多岁差模式)/ 多命理融合(debate / reflection / tool / retriever);命运剧本(RPG 角色卡 + 大运分章);事件反推校准。

**下一步杠杆(按性价比)**:① ✅ 用神已扩到大 n=92(90.2%);② 旺衰无独立 gold(杨炎=六亲断象、MingLi/celebrity=事件),要谈 accuracy 需先标注命主旺衰 gold(数据工作,非代码攻坚);③ 六亲 det 接近天花板、n 偏小,可扩 n;④ 现阶段不建议做 SFT/LoRA(需 GPU,真人路线未必需要)。


## 4. 下载数据落盘策略

### 4.1 文件系统（主数据）

默认目录结构（`folderstyle: true`）：

```text
Downloaded/
├── download_manifest.jsonl
└── 作者名/
    └── post/
        └── 2024-02-07_作品标题_aweme_id/
            ├── 2024-02-07_作品标题_aweme_id.mp4
            ├── 2024-02-07_作品标题_aweme_id_cover.jpg
            ├── 2024-02-07_作品标题_aweme_id_music.mp3
            ├── 2024-02-07_作品标题_aweme_id_avatar.jpg
            └── 2024-02-07_作品标题_aweme_id_data.json
```

命名日期优先使用作品发布时间 `create_time`；若缺失或非法，会回退到当前日期并记录告警。

### 4.2 独立下载清单（新增）

- 文件：`{path}/download_manifest.jsonl`
- 形式：每行一条 JSON（append-only）
- 典型字段：
  - `date`（作品发布日期）
  - `aweme_id`
  - `author_name`
  - `desc`
  - `media_type`
  - `tags`（来自 `text_extra`、`cha_list`、`desc` 中 `#`）
  - `file_names`
  - `file_paths`
  - `publish_timestamp`（若可解析）
  - `recorded_at`（写入时间）

### 4.3 SQLite 数据库（可开关）

- 默认开关：`database: true`
- 默认库文件：`dy_downloader.db`
- 表结构：
  - `aweme`：作品明细、作者、发布时间、下载时间、保存路径、原始 metadata
  - `download_history`：每次任务 URL、类型、总数、成功数、配置快照

> 当 `database: false` 时，不写 SQLite，但**仍会写**媒体文件和 `download_manifest.jsonl`。


## 5. 关键流程（简版）

1. 读取配置（命令行 > 环境变量 > 配置文件 > 默认配置）
2. 初始化 Cookie 与 API 客户端
3. 解析链接类型（视频 / 图文 / 用户）
4. 拉取作品数据并应用时间/数量/增量规则
5. 并发下载媒体文件
6. 写入可选 JSON 元数据
7. 追加写入 `download_manifest.jsonl`
8. 若开启数据库，写入 `aweme` 与 `download_history`


## 6. 近期更新（2026-07-05）

- ✅ 文件名和目录日期从“下载时间”改为“作品发布时间（`create_time`）”
- ✅ 新增独立下载清单 `download_manifest.jsonl`
- ✅ 清单中补充 `date/file_names/tags` 等可追溯字段
- ✅ 增加对应测试，确保发布时间命名与清单写入行为
- ✅ 修复 proxy validator 符号同步（`_PROXY_ALLOWED_SCHEMES` / `_is_valid_proxy`）
- ✅ 更新项目文档与测试统计
- ✅ 新增 bazi 四柱校验器（六十甲子验证）
- ✅ 案例库自动去重与非法八字过滤
- ✅ 领域感知 RAG + 可选 embedding 语义召回
- ✅ 案例自动标注器（格局、身强身弱、用神忌神）
- ✅ 规则校验层（旺衰/用神忌神逻辑检查）
- ✅ 多轮一致性聚合（ensemble）降低 LLM 方差
- ✅ 新增 bazi REST API（analyze / timeline / yearly / from_datetime / cases / extract / feedback）
- ✅ bazi_ai 支持额外案例库/知识库路径与环境变量覆盖（`DOUYIN_BAZI_AI_*`）
- ✅ 新增八字结构分析器（`bazi_structural.py`）与农历/节气日历模块（`calendar.py`）
- ✅ 新增杨炎八字绝技案例知识库（清洗后的 `cases_yangyan.jsonl`）
- ✅ REST server 增强：job 取消、SSE 事件流、运行时配置覆盖
- ✅ 新增 qizheng（七政四余）分析 API（analyze / yearly）
- ✅ 新增 destiny（多命理融合）API（analyze / council / daily / systems）
- ✅ `like/mix/music` 用户模式增加浏览器兜底（`core/user_modes/browser_fallback.py`）
- ✅ GitHub Actions CI：lint / test(3.9–3.12) / compat / optional-deps / docker
- ✅ 紫微斗数（Zi Wei）分析引擎
- ✅ 七政四余（Qi Zheng）分析引擎
- ✅ 多命理系统对齐融合层（`tools/destiny/`）
- ✅ 新增 React + Vite 命镜 Web UI（Dashboard / Chart / Yearly / Qizheng / Council / Sandbox / Calendar）
- ✅ 整理工作区：修复 lint、分批提交、同步文档
- ✅ 新增事件校准引擎（`tools/destiny/calibrator.py`）与 REST API（`/api/v1/charts/{chart_id}/events` / `calibrate`）
- ✅ 事件校准支持录入重大事件、按领域匹配各命理系统预测、输出系统权重与时辰偏移建议
- ✅ 实现 PRD 模块 6「命运剧本」：`tools/destiny/script_writer.py` + `POST /api/v1/destiny/script`
- ✅ 命运剧本输出 RPG 角色卡（天赋/弱点/当前章节/下一章预告）+ 按大运分章的人生剧本
- ✅ 新增前端 `/script` 页面展示命运剧本，并加入导航


## 7. 测试与验证

执行命令：

```bash
PYTHONPATH=. pytest -q
```

结果：

```text
642 passed, 0 failed, 0 error
```

说明：测试套件持续增长，当前已无跳过项；`pytest-asyncio` deprecation warning 已配置忽略。


## 8. 后续建议

1. 将事件校准结果持久化到 SQLite/PostgreSQL（当前为内存存储）。
2. 将事件校准结果持久化到 SQLite/PostgreSQL（当前为内存存储）。
3. 为 `download_manifest.jsonl` 增加轮转或归档策略（长期运行场景）。
4. 补充数据库查询 CLI（例如按作者/日期/标签检索）。
5. 将 `tools/destiny/`  deeper 集成到 CLI（`--systems` 参数）与更多 REST 端点。

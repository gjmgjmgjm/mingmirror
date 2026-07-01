# 项目文档目录

本目录用于存放 `douyin-downloader` 项目的补充文档与维护记录。

## 文档索引

| 文件 | 说明 |
|------|------|
| [sync-status.md](./sync-status.md) | CLI 版本与桌面版（douyin-downloader-desktop）共享模块的同步检查状态 |
| [../PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md) | 项目架构、已实现能力与测试统计总览 |

## 项目亮点速览

- **浏览器兜底**：`post` / `like` / `mix` / `music` 用户模式在 API 分页受限时均可启用 Playwright 浏览器兜底
- **REST Server**：`--serve` 启动 FastAPI 服务，支持 job 提交、查询、取消、SSE 状态流、运行时配置覆盖
- **CI/CD**：`.github/workflows/ci.yml` 覆盖 lint、Python 3.9–3.12 矩阵测试、跨平台兼容、可选依赖、Docker 构建验证
- **Bazi AI**：`tools/bazi_ai/` 提供四柱校验、RAG、embedding、标注、规则校验、ensemble 聚合及 4 个 REST API
- **参数化知识库脚本**：`tools/build_knowledge_base*.py` 支持 `--glossary`、`--users`、`--output-dir`、`--base-dir` 等参数

## 相关入口

- 用户快速开始：[`../README.md`](../README.md) / [`../README.zh-CN.md`](../README.zh-CN.md)
- 模块开发说明：各子目录下的 `AGENTS.md`

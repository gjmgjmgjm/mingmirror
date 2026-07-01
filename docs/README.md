# 项目文档目录

本目录用于存放 `douyin-downloader` 项目的补充文档。

## 文档索引

- [`sync-status.md`](./sync-status.md)：CLI 版本与桌面版（douyin-downloader-desktop）共享模块的同步检查状态。

## 持续集成

项目的 CI 配置位于 `.github/workflows/ci.yml`，会在 Python 3.9–3.12 上运行测试、执行 `ruff` 代码检查，并验证 Docker 镜像构建。

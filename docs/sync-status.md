# 桌面版共享逻辑同步状态

> 本文件记录 douyin-downloader CLI 与桌面版（douyin-downloader-desktop）之间共享模块的同步检查结果。

## 检查日期

2026-07-01

## 检查环境

- 项目目录：`D:\douyin-downloader-main`
- 桌面版 sibling 目录：`D:\douyin-downloader-desktop`（本地不存在）
- sync 脚本：`../douyin-downloader-desktop/scripts/sync-to-cli.sh`（未找到）

## 检查方法

1. 尝试运行 `../douyin-downloader-desktop/scripts/sync-to-cli.sh --check`：失败，桌面版 sibling 项目未检出到本地。
2. 在 `D:\` 盘搜索 `douyin-downloader-desktop` 目录：未找到。
3. 因此本次无法对以下文件进行逐文件一致性对比：
   - `auth/cookie_manager.py`
   - `config/config_loader.py`
   - `control/rate_limiter.py`
   - `storage/database.py`
   - `utils/helpers.py`

## 一致文件列表

N/A（本次无法执行有效对比）

## 不一致文件列表及差异说明

N/A（本次无法执行有效对比）

## 已知的 intentional divergence

以下文件按设计允许 CLI 与桌面版存在差异，无需强制同步：

| 文件 | 说明 |
|------|------|
| `cli/main.py` | CLI 入口不包含桌面版的 `_verify_self_checksum()` 和 `_enforce_license_at_startup()` |
| `run.py` | CLI 为简单 bootstrap；桌面版包含 sidecar 启动与数据目录迁移 |
| `server/app.py` | CLI server 已实现 SSE、配置覆盖、job 取消；桌面版额外包含 license/DRM 相关逻辑 |
| `server/jobs.py` | CLI 已实现 `CANCELLED` 状态与 `cancel()`；桌面版可能包含 UI 进度回调等差异 |
| `control/__init__.py` | CLI 不导出 `ProgressReporter` 类（仅桌面 UI 使用） |
| `core/user_modes/` | CLI 已实现 `like/mix/music` 浏览器兜底；桌面版可复用或保留自身实现 |

## CI/CD 状态

- `.github/workflows/ci.yml` 已创建并校验通过。
- 工作流配置：
  - 触发条件：`push` / `pull_request` 到 `main` / `master`
  - `paths-ignore`：文档-only 变更不触发 CI
  - `concurrency`：同一分支上的旧 run 自动取消
  - Jobs：`lint`、`test`（Python 3.9–3.12 矩阵）、`compat`（Ubuntu/Windows/macOS）、`optional-deps`（server + bazi）、`docker`
  - `pip` 缓存加速依赖安装
  - 安装：`pip install -r requirements.txt -r requirements-dev.txt`
  - 执行 `ruff check .`
  - 执行 `python -m pytest tests/ -q`
  - Docker build 验证

## 建议同步项

1. 在开发环境中检出桌面版 sibling 项目到 `D:\douyin-downloader-desktop`。
2. 运行以下命令进行全面同步检查：

   ```bash
   ../douyin-downloader-desktop/scripts/sync-to-cli.sh --check
   ```

3. 若脚本报告差异，优先检查 `auth/`、`config/`、`control/`、`core/`（避开 `core/user_modes/`）、`storage/`、`utils/`。
4. 对桌面版已修复但 CLI 未同步的 bug，执行单向同步；对 intentional divergence 在本文件中补充说明。

## 本次本地验证结果

- `ruff check .`：All checks passed!
- `python -m pytest tests/ -q`：**517 passed**（56 个测试模块）

## 备注

- 当前未对共享模块做任何代码变更，因为无法确定桌面版状态。
- 本文件由窗口 D（文档与项目元数据同步）维护，基于窗口 C 的初稿更新。

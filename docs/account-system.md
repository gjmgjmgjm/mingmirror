# 命镜账号系统

> 2026-07-19 落地：邮箱注册 / 登录 / 会话令牌 / 设备关联 / 权益合并。

## 能力

| 能力 | 说明 |
|------|------|
| 注册 / 登录 | `POST /api/v1/auth/register` · `login` |
| 会话 | Bearer / `X-Session-Token`，默认 30 天 |
| 登出 | `POST /api/v1/auth/logout` |
| 当前用户 | `GET /api/v1/auth/me` |
| 关联设备 | `POST /api/v1/auth/link-device`（登录时自动） |
| 改密 | `POST /api/v1/auth/change-password`（吊销其它会话） |
| 邮箱验证 | `request-verify` · `verify-email`（无 SMTP 时 JSON 返回 token） |
| 密码重置 | `forgot-password` · `reset-password`（无 SMTP 时返回 reset_token） |
| OAuth | `GET /auth/oauth/{provider}` → **501** 占位（微信/Apple 待配密钥） |
| 权益合并 | 登录时将 `device_id` 匿名权益合并到 `user:<id>` |
| 命盘绑定 | `chart.user_id`；登录 claim 设备下命盘；列表可按 user 跨设备 |

## 安全

- 密码：**PBKDF2-HMAC-SHA256**（200k iter，stdlib，无额外依赖）
- 会话：`secrets.token_urlsafe(32)` 不透明令牌，SQLite 存储
- 库文件：默认 `data/mingmirror_accounts.db`（可用 `mingmirror.account_db` 配置）

## 并发与后端

| 项 | 说明 |
|----|------|
| AI 并发 | `server.ai_concurrency`（默认 4）限制 `/bazi/analyze` |
| 导出并发 | `server.export_concurrency`（默认 2） |
| 下载连接 | 进程级共享 `aiohttp.TCPConnector` |
| 健康检查 | `/api/v1/health` 返回 `concurrency` 与 `accounts` |

## 前端

- 路由：`/app/account`
- `AuthContext` + `lib/auth.ts` 持久化 token
- 所有 `fetchJson` 自动附带 Authorization

## 与匿名 device_id 关系

- 未登录：继续使用浏览器 `device_id`（本地权益 / 命盘隔离）
- 登录：绑定 device，合并 package credits / pro 到期时间
- 仍兼容无账号使用；账号为跨设备与付费主身份

## 测试

```bash
python -m pytest tests/test_accounts.py -q
```

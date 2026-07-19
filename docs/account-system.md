# 命镜账号系统

> 2026-07-19 落地：邮箱注册 / 登录 / 会话令牌 / 设备关联 / 权益合并 / 隐私导出删除 / OAuth 骨架。

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
| **导出数据** | `GET /api/v1/auth/export-data` — 用户/设备/会话元数据/OAuth 绑定（无密码哈希） |
| **删除账号** | `POST /api/v1/auth/delete-account` — body `{password, confirm:"DELETE"}` |
| **OAuth** | 微信 / Apple 授权 URL + code 交换骨架（见下） |
| 权益合并 | 登录时将 `device_id` 匿名权益合并到 `user:<id>` |
| 命盘绑定 | `chart.user_id`；登录 claim 设备下命盘；列表可按 user 跨设备 |

## OAuth（微信 / Apple）

| 路径 | 说明 |
|------|------|
| `GET /api/v1/auth/oauth/{provider}` | 返回 `authorize_url` / `state` / `ready` |
| `GET\|POST /api/v1/auth/oauth/{provider}/callback` | 回调换会话 |
| `POST /api/v1/auth/oauth/{provider}/exchange` | SPA JSON 换码 |

环境变量（**勿写入 git**）：

| 变量 | 说明 |
|------|------|
| `MINGMIRROR_PUBLIC_BASE_URL` | 回调基址，如 `https://your.domain` |
| `MINGMIRROR_WECHAT_OAUTH_APP_ID` / `MINGMIRROR_WECHAT_OAUTH_SECRET` | 微信开放平台网站应用 |
| `MINGMIRROR_APPLE_CLIENT_ID` / `TEAM_ID` / `KEY_ID` | Sign in with Apple |
| `MINGMIRROR_OAUTH_STUB=1` | 本地测试：跳过真实 token 交换，签发 stub 身份 |

生产未配密钥时 `ready=false`，仍返回脚手架 authorize URL；真正换码返回 **501**（或 stub 模式下 200）。

## 隐私

- **导出**：不包含 password_hash；会话仅 token 后缀
- **删除**：邮箱账号必须密码 + `confirm=DELETE`；OAuth-only（`@oauth.local`）可仅靠会话 + confirm
- 删除清除：user / session / device / token / oauth 行

## 安全

- 密码：**PBKDF2-HMAC-SHA256**（200k iter，stdlib，无额外依赖）
- 会话：`secrets.token_urlsafe(32)` 不透明令牌，SQLite 存储
- 库文件：默认 `data/mingmirror_accounts.db`（可用 `mingmirror.account_db` 配置）
- 邮件：`server/mailer.py` + 环境变量 `MINGMIRROR_SMTP_*`；未配置时 JSON 返回 token（开发）

## 我的命盘

- `GET /api/v1/me/charts` — 登录用户跨设备盘列表  
- `PATCH /api/v1/charts/{id}?label=` — 重命名  
- 登录时 claim 本机 `device_id` 下未绑定 `user_id` 的盘

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
- 隐私区：导出 JSON / 删除账号
- 登录页：微信 / Apple OAuth 按钮（需服务端密钥）
- 所有 `fetchJson` 自动附带 Authorization

## 与匿名 device_id 关系

- 未登录：继续使用浏览器 `device_id`（本地权益 / 命盘隔离）
- 登录：绑定 device，合并 package credits / pro 到期时间
- 仍兼容无账号使用；账号为跨设备与付费主身份

## 测试

```bash
python -m pytest tests/test_accounts.py tests/test_payments_oauth_privacy.py tests/test_auth_e2e.py -q
```

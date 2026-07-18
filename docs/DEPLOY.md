# 命镜 MingMirror · 部署说明

## 最快演示（推荐）

```bash
# Windows
.\scripts\start_demo.ps1            # 结构冒烟 + 本地起服
.\scripts\start_demo.ps1 -Docker    # 结构冒烟 + docker compose
.\scripts\start_demo.ps1 -SmokeOnly # 仅离线校验样例盘与交付包

# macOS / Linux
chmod +x scripts/start_demo.sh
./scripts/start_demo.sh
./scripts/start_demo.sh --docker
./scripts/start_demo.sh --smoke-only
```

离线冒烟（无服务端）：

```bash
python scripts/demo_smoke.py
python scripts/demo_smoke.py --export-dir ./demo_out
```

浏览器打开后，首页 **「一键演示」** 可加载 4 个固定样例命盘；套餐页演示码 **`demo-pro`** 开通完整版。

| 路径 | 说明 |
|------|------|
| `/app/` | 产品 UI |
| `/api/v1/health` | 健康检查 |
| `/api/v1/product/demo-charts` | 演示命盘目录 |
| `/api/v1/product/demo-charts/{id}/package` | 直接导出该样例交付包 |
| `/api/v1/product/funnel?days=7` | 漏斗汇总 |

## 一键 Docker Compose

```bash
# 仓库根目录
docker compose up --build -d

# 浏览器
#   产品 UI:  http://localhost:8000/app/
#   健康检查: http://localhost:8000/api/v1/health
#   演示盘:   http://localhost:8000/api/v1/product/demo-charts
#   漏斗:     http://localhost:8000/api/v1/product/funnel?days=7
```

环境变量（可选）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `MINGMIRROR_DEMO_CODE` | `demo-pro` | 套餐页开通完整版验证码 |
| `MINGMIRROR_ADMIN_TOKEN` | 空 | 运营看板鉴权；**生产务必设置** |
| `MINGMIRROR_WEBHOOK_SECRET` | 空 | 支付 webhook 密钥；**生产务必设置** |
| `DEEPSEEK_API_KEY` | 空 | AI 章节；结构层无 key 也可导出 |
| `DOUYIN_PATH` | `/app/Downloaded` | 数据目录（事件/命盘 SQLite） |

数据卷：`mingmirror_data` 持久化命盘、校准、埋点、权益。

停止：

```bash
docker compose down
```

## 本地开发

```bash
# 后端
pip install -r requirements.txt -r requirements-server.txt
python run.py --serve --serve-host 127.0.0.1 --serve-port 8000

# 前端（另一终端）
cd web && npm install && npm run dev
# 或使用已构建产物：访问 http://127.0.0.1:8000/app/
cd web && npm run build
```

## 产品 API 速查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/product/demo-charts` | 固定演示命盘目录 |
| GET | `/api/v1/product/demo-charts/{id}` | 单条演示盘详情 |
| POST | `/api/v1/product/demo-charts/{id}/package` | 演示盘交付包（可传流年区间） |
| POST | `/api/v1/charts` | 创建命盘 UUID |
| POST | `/api/v1/charts/{id}/export/package` | 标准交付包 HTML/MD（支持 `liunian_start_year` / `liunian_years`） |
| POST | `/api/v1/bazi/export/package` | 无 UUID 导出交付包 |
| POST | `/api/v1/ziwei/yearly` | 紫微流年（结构层） |
| POST | `/api/v1/qizheng/yearly` | 七政年运 |
| POST | `/api/v1/product/track` | 漏斗埋点 |
| GET | `/api/v1/product/funnel?days=7` | 漏斗汇总（设 admin token 后需鉴权） |
| GET | `/api/v1/admin/overview` | 运营看板聚合（header `X-Admin-Token`） |
| GET | `/api/v1/product/entitlement?device_id=` | 查询权益 |
| POST | `/api/v1/product/entitlement/activate` | 演示开通（code=demo-pro） |
| POST | `/api/v1/product/entitlement/consume` | 消耗交付包次数 |
| POST | `/api/v1/product/checkout` | **收银台闭环**（演示渠道：账本+权益） |
| GET | `/api/v1/product/payments?device_id=` | 用户订单列表 |
| GET | `/api/v1/product/payment/status?provider=&external_id=` | 订单查询 |
| POST | `/api/v1/product/payment/webhook` | 支付回调 → 权益（幂等） |
| POST | `/api/v1/admin/entitlement/grant` | 运营手动授权（需 admin token） |

### 支付 webhook 示例

```bash
curl -X POST http://localhost:8000/api/v1/product/payment/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: $MINGMIRROR_WEBHOOK_SECRET" \
  -d '{
    "provider": "stripe",
    "external_id": "pi_xxx",
    "device_id": "user-device-uuid",
    "product": "pro",
    "amount_cents": 9900,
    "status": "succeeded",
    "days": 30
  }'
```

`product` 映射：`pro` / `pro_month` → 完整版；`package` / `credit` → 交付包次数。  
同一 `(provider, external_id)` 重复投递不会重复加权益。

### 运营看板

浏览器：`http://localhost:8000/app/admin`  
若设置了 `MINGMIRROR_ADMIN_TOKEN`，在页面输入密钥即可。

## 合规

全站文案须保留：结构层确定性 vs AI 参考；不构成医疗/法律/投资建议。

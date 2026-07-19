# 命镜可信结构层（Plan A）

结构层指**确定性排盘结果**（四柱、大运顺逆、紫微命宫/五行局等），不依赖 LLM。

## 黄金用例

| 文件 | 作用 |
|------|------|
| `tests/fixtures/structural_golden.json` | 锁定期望值（故意改算法时才改 gold）；**version 2** 含 15+ 紫微盘 |
| `tests/test_structural_golden.py` | 子时 / 真太阳时 / 农历闰月 / 大运性别对 / 紫微局 / 五虎遁 |
| `tests/test_council_e2e.py` | 议会 ziwei 注册、chart_id 校准权重、device 隔离 |
| `tests/test_production_boot.py` | 生产缺 secret 时 **build_app 硬失败** |

本地：

```bash
python -m pytest tests/test_structural_golden.py tests/test_council_e2e.py tests/test_production_boot.py -v
```

CI：在 `test` job 中额外跑 structural + council 套件。

## 设备隔离

- 命盘 `chart.device_id` 绑定浏览器 `getDeviceId()`
- `reuse_existing` **仅同 device** 复用，避免跨用户串档案
- UUID 命盘：其它 device 读写 → **403**
- 生产环境（`MINGMIRROR_ENV=production|prod|staging`）创建命盘时要求 `device_id`

## 生产变量

```text
MINGMIRROR_ENV=production
MINGMIRROR_ADMIN_TOKEN=...
MINGMIRROR_WEBHOOK_SECRET=...
```

生产 / staging **启动即校验**：缺 admin 或 webhook secret 时 `build_app` 抛 `RuntimeError`，`run_server` 以 exit code 2 退出（端口不会监听）。

紧急迁移可用（勿长期开启）：

```text
MINGMIRROR_ALLOW_INSECURE_BOOT=1
```

## 结构层准确率（零 API 尺子）

| 维度 | 水位 | gold |
|------|------|------|
| 排盘 | 100% (32/32) | iztro |
| 用神 | 100% (92/92) | 穷通宝鉴 |
| 六亲强弱 | **~93% (42/45)** | 杨炎 det（噪声剔除后） |

六亲提升（2026-07）：本气得令 / 子女透干严判 / 透干克泄阈值 2.5 / 母星虚浮不升格；母印·父财·配偶官杀/财 **双星标签合参**（父/配偶强弱仍以主星为准，避免假强）。

应期联动：`year_timing_surface.meta.liuqin_bridge` + `structural_critic`（大运/驿马 re-rank，**不断言单年**）。

## 已知诚实边界

- 紫微为 `certain_simplified`（亮度/流派未展开）
- 匿名 device_id 非密码学强鉴权，抬高误扫门槛
- 农历闰月依赖 `sxtwl`；缺依赖时 leap 用例 skip
- 事件/年份开放式 ≈0% 是物理天花板；MCQ 年份靠 shortlist+LLM，非本层 det 承诺
- **产品分层展示**见 [`capability-boundary.md`](./capability-boundary.md)；应期 API：`tools.bazi_ai.year_timing_surface`

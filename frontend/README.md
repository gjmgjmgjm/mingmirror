# 命盘 · 前端界面

这是 `douyin-downloader` 项目的内置 Web UI，用于可视化八字/紫微/七政四余命理分析。

## 访问方式

启动 REST server 后打开浏览器：

```bash
python -m server.app --serve
# 然后访问 http://localhost:8000/
```

后端会自动将 `/` 重定向到 `/app/index.html`，并托管 `frontend/` 目录下的静态文件。

## 当前页面

- **八字分析工作台**：输入四柱八字、问题、选择学派，点击「起盘分析」查看格局、用神、忌神、分领域断语与核心断语。
- **参考案例**：右侧展示 `GET /api/v1/bazi/cases` 返回的案例，点击可快速填入八字。
- **反馈**：分析结果下方可点击「准 / 不准」，调用 `POST /api/v1/bazi/feedback`。

## 技术说明

- 单文件 `index.html`，内嵌 CSS/JS，无构建步骤。
- 使用 Google Fonts（Noto Serif SC + Zhi Mang Xing）。
- 通过相对路径 `/api/v1/...` 调用后端 API，因此需要与后端同源部署。

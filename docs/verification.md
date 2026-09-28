# 运行与验收记录

验证日期：2026-09-24。环境：Windows + Docker Desktop Linux containers，项目 `E:\xhh\projects\toolbox-platform`。入口 http://127.0.0.1:18990。

## 构建

- 前端 Vue / TypeScript 检查、Vite 生产构建通过；主 JS gzip 约 43 KB，CSS gzip 约 7.5 KB。
- 后端 `ruff check app/toolbox plugins workers tests/toolbox`、Python 编译检查通过。
- backend/web 两个最终镜像构建成功，bootstrap 正常退出，API/MySQL/Redis/MinIO 探活成功。
- 已使用用户指定的 admin 凭证更新数据库，并撤销旧 admin 会话。密码保留在本机 `.env`，不写入此文档。

## 后端：25 项真实依赖检查

真实连接 MySQL、Redis、Celery 和私有 MinIO 桶，并使用两个临时账号验证：

- 登录、成员权限、跨来源请求阻止、主题配置持久化、退出撤销会话。
- 同内容幂等返回同一 job，不同内容同键返回 409。
- outbox → Redis → Celery → MySQL/S3 完整任务执行。
- 文本导出文件逐字校验；重复投递不产生第二份成果。
- 跨账号任务查询/取消、文件下载、输入文件引用被拒绝。
- 中文 CPU TTS 生成真实 RIFF/WAV；上传 WAV，FFmpeg 成功生成 MP3。
- 停用工具拒绝新任务；排队任务取消；手动重试创建新任务并成功。
- 过期心跳 fixture 被分发器标记失败。
- 出口代理拒绝回环、云元数据、IPv6 回环和内部 DNS 地址。
- 通过受限出口下载 W3C 托管的公开视频样例 `https://media.w3.org/2010/05/sintel/trailer.mp4`。

测试脚本会清理临时账号、其任务及 S3 对象。结果在 `artifacts/integration.log`。失联验证为明确构造过期心跳，不等同真实断电故障演练。

## 浏览器：14 项检查

使用独立无头 Microsoft Edge，桌面 1440×1040、移动端 390×844：

- 从真实登录页进入，加载 7 个工具卡片。
- 收藏筛选、中文 JSON 格式化、中文 Base64 往返转换。
- 在页面提交新的 TTS 任务，按其新 job ID 等待 succeeded，再确认结果下载入口。
- 深色模式刷新后保留，跟随系统的亮暗变化即时生效。
- 4 种主题配色逐一应用。
- 移动端无横向溢出，侧栏导航可用。
- 无未捕获的浏览器脚本异常。

测试脚本：`frontend/web/tests/toolbox/browser-check.mjs`（需本机 Microsoft Edge），执行 `npm run test:browser`。它读取本地 `.env` 登录，会生成真实语音样例并切换管理员外观；结束时保留浅色/珊瑚主题并退出测试会话。结果在 `artifacts/browser-check.json`。

## 界面截图

- `artifacts/login.png`：登录页。
- `artifacts/workspace-light.png`：浅色工作台。
- `artifacts/workspace-dark.png`：深色工作台。
- `artifacts/appearance-dark.png`：主题设置。
- `artifacts/tasks.png`、`artifacts/files.png`：任务及文件中心。
- `artifacts/workspace-mobile.png`：移动端完整页面。

已通过截图检查布局、文本、对齐、深浅色和移动端显示。截图来自实际运行页面，统计与任务不是模拟数据。

## 测试中解决的问题

1. 主题设置原先存在短延迟内刷新丢失的问题，改为立即发送、串行保存，恢复配置时不反向覆盖服务端。
2. Nginx 改用 Docker DNS 动态解析，避免 API 容器重建后继续访问旧 IP。
3. 宿主代理使用 198.18/15 假 IP，添加显式可信 DoH 适配，同时保留对内网/回环地址的阻止。
4. 禁用上游开发级 HTTP 调试日志，使用生产 INFO 日志，避免响应 Cookie 等会话数据写入详细追踪。

当前验收不覆盖 GPU、AutoClip、全站点下载、长期压测、备份恢复、公网部署。这些范围见 implementation.md。


## 目录重构与媒体功能追加验收（2026-09-24）

所有运行入口均已切换到 `backend/app/toolbox`、`backend/plugins`、`backend/workers` 与 `frontend/web`。根目录不再存在旧的两个产品目录或正式 Compose 文件；使用 `deploy/compose.yaml`。前端类型检查/生产构建、Ruff、Compose 正式及开发配置解析通过。

| 验证 | 结果 | 本地证据 |
|---|---|---|
| 后端真实 MySQL/Redis/Celery/S3 集成 | 31 项通过 | `artifacts/layout-smoke.log` |
| Range 单元测试 | 14 项通过 | `backend/tests/toolbox/test_ranges.py` |
| 搜索/批量下载接口 | 18 项通过 | `artifacts/search-batch.log` |
| 登录/收藏/主题/移动端浏览器测试 | 14 项通过 | `artifacts/browser-check.json` |
| GPT-SoVITS/参考音/真实合成/音视频播放 | 6 项通过 | `artifacts/media-check.json` |
| 浏览器搜索勾选批量下载 | 8 个真实结果，选中 2 个，2 个下载成功，无页面脚本异常 | `artifacts/search-ui.json` |

追加验证包含批量去重、逐项错误、同键重试不重复、改参数拒绝、20 条上限、搜索/缩略图所有权，以及下载结果的 Range 预览。语音测试调用了现有 GPT-SoVITS CPU 服务，生成真实 MP3 后写入私有 S3，验证浏览器播放。

新增截图：`natural-tts-form.png`、`natural-tts-result.png`、`video-preview.png`、`video-preview-mobile.png`、`video-search.png`、`video-search-batch.png`、`video-search-mobile.png`（均在 artifacts）。

本轮原 W3C 样例地址出现 Cloudflare 403，验收改用 Blender 官方公开样例 `https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4`。没有绕过源站验证。YouTube 检索通过，部分实际视频仍要求登录；搜索可见与可下载是两个不同条件。


## 下载性能追加验证

- DNS 缓存与 Range 单元测试共 18 项通过：覆盖过期后重新解析、私网地址拒绝、TTL 不续期、解析器隔离。
- 新版搜索/批量接口 18 项回归通过，记录 `artifacts/speed-batch-check.log`。
- 清晰度 UI 实际提交 720p，浏览器检测输出高度 720，播放和移动端布局通过，记录 `artifacts/quality-ui.json`。
- 原版本已存在任务以原幂等键重试仍返回相同任务；同键改为 720p 返回 409，不重复创建。
- 两轮下载器对照文件 SHA-256 一致；不同清晰度结果经 ffprobe 核实。完整原始数据与局限见 [性能说明](download-performance.md)。


## 任务管理与 YouTube 错误提示（2026-09-24）

- CRUD 真实服务集成检查 18 项通过，含所有权、输入验证事务回滚、参数修改后执行、运行中冲突、删除后资产保留和晚到消息无效，记录 `artifacts/task-crud-check.log`。
- 任务中心浏览器检查 10 项通过：新建、按 ID 查询、改名、详情、三视图、视图持久化、手机布局、确认删除、无脚本异常，记录 `artifacts/tasks-check.json`。相关截图为 `tasks-list.png` / `tasks-cards.png` / `tasks-board.png` / `tasks-mobile.png`。
- 下载诊断分类、DNS 缓存、Range 共 27 项单元检查通过，包含诊断不泄露测试 Cookie/URL token。
- 补齐 Node/EJS 后 YouTube 指定链接匿名访问仍被要求登录。实际重试任务返回 `authentication_required`，未把需要登录的视频标为下载成功。
# 2026-09-24 任务批量删除增量验收

- 任务管理真实接口检查共 32 项通过（原有 18 项 + 批量删除相关 14 项）。覆盖鉴权、跨账号隔离、混合状态、重复 ID、重复提交、100 项上限、文件保留、outbox 清除、晚到消息不产生输出。
- 批量删除浏览器验收 12 项通过：多视图选择与半选、全选确认和取消、筛选清空、筛选结果加载期间禁止勾选旧列表、深色/手机布局、模拟传输失败后重试、真实删除与文件下载。当前数据不足两页，页码切换清空分支未在此次浏览器验收触发。
- 前端 TypeScript/Vite 构建及后端 Ruff 检查通过，API 和 Web 已部署到本地 18990 端口。
# 2026-09-24 科技深色工作台验收

- 界面按用户选择改为深蓝/蓝紫音视频工作台，保留四套配色、浅色和跟随系统。
- 前端构建通过；`studio-check.mjs` 10 项和 `batch-delete-check.mjs` 12 项浏览器检查通过，API 健康检查正常。详情见 `ui-studio.md`。
- YouTube 旧链接普通匿名解析再次返回 `authentication_required`。失败提示的 UI 使用模拟响应验证；没有宣称该链接已成功匿名下载。

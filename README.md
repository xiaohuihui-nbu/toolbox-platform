# 拾光 Toolbox

面向个人与小团队的插件式工具工作空间，使用 FastAPI + Vue 3 + Celery + MySQL + Redis + MinIO。**不使用 Elasticsearch、Nacos。**

基于 FastapiAdmin 扩展，复用应用工厂、系统用户/角色/菜单、登录会话、权限服务和操作审计。工具箱任务、文件与配置作为独立业务模块接入；原账号数据已迁入 `sys_user`，不再维护第二套登录账户。来源见 [upstream-lock.json](upstream-lock.json)，阶段验收与剩余工作见 [基座接入记录](docs/fastapiadmin-adoption.md)。

## 启动

需要 Docker Desktop（Linux containers）、Node.js 22+、npm、PowerShell 7。

```powershell
cd E:\xhh\projects\toolbox-platform
.\scripts\start.ps1 -WithTts
```

访问 [本机工作台](http://127.0.0.1:18990)。本机现有管理员凭证继续生效；新环境首次启动随机生成初始密码并写入根目录 `.env`，不覆盖已有文件。`-WithTts` 启动同级既有 `gpt-sovits-cpu` 项目；未安装模型服务时不传此参数，其他工具可正常使用。

后续免构建启动：`./scripts/start.ps1 -SkipBuild`；停止：`./scripts/stop.ps1`。数据存放于本项目独立 Docker 卷。

## 已实现

- 工作台：分类、收藏、搜索、任务统计，浅色/深色/跟随系统，四套主题配色，移动端适配。
- AI 自然配音：既有 GPT-SoVITS、16 种音色、参考试听、语速/停顿、MP3/WAV。
- 基础离线 TTS：eSpeak NG 中文/英语、语速/音调/音量、MP3/WAV。
- 视频下载：B站/YouTube 搜索，勾选或粘贴链接批量提交（最多 20 条），独立任务与完成预览。
- 音频提取、文本导出、浏览器本地 JSON 格式化和 Base64 编解码。
- 私有文件中心：上传、下载、音视频预览与进度拖动，按账号隔离。
- 任务：新建/查询/编辑/删除，列表/卡片/看板，筛选分页、取消重试、版本快照、执行记录、投递租约和失联恢复。
- 管理：[FastapiAdmin 原版后台](http://127.0.0.1:18990/admin/#/home)提供用户、角色、菜单、部门、岗位、字典及日志页面，复用原生布局、表单和接口；也可从工作台偏好设置进入，两端共享登录。下载、媒体处理和配音使用独立执行队列。

站点访问限制会影响搜索或下载成功率；具体范围见 [媒体工具使用说明](docs/media-tools.md)。

## 目录

代码已迁入约定结构，完整树与入口见 [目录结构与实施边界](docs/directory-layout.md)。

```text
backend/app/toolbox/   # api/models/schemas/services/contracts/registry/runtime/jobs/storage/search/providers
backend/plugins/      # demo_echo/video_download/tts/audio_convert/video_highlight/browser_tools
backend/workers/      # Celery 应用与固定任务入口
backend/tests/toolbox/
frontend/web/src/     # views/toolbox、components/toolbox、tool-views、api/toolbox 等
services/voice-engine/
deploy/               # compose.yaml、compose.dev.yaml、nginx、mysql、redis
scripts/
docs/
```

## 开发与验收

```powershell
# 根目录：查看服务
 docker compose --env-file .env -f deploy/compose.yaml ps

# 前端
cd frontend/web
npm ci
npm run build
npm run test:browser
npm run test:media
npm run test:search

# 根目录：真实后端集成测试
cd ../..
docker compose --env-file .env -f deploy/compose.yaml exec -T api python -m tests.toolbox.smoke
docker compose --env-file .env -f deploy/compose.yaml exec -T api python -m tests.toolbox.search_batch
```

后端静态检查：在 `backend` 中运行 `uv run ruff check app/toolbox plugins workers tests/toolbox`。Range 单元测试：`uv run pytest tests/toolbox/test_ranges.py --confcutdir=tests/toolbox -q`，避免加载上游独立应用的测试初始化。

API 契约位于 `/api/openapi.json`。浏览器测试使用本机 Edge，读取 `.env` 登录，会生成真实媒体样例；后端集成测试使用隔离账号并清理完成的测试数据。

- [架构与插件开发](docs/architecture.md)
- [部署、运维与恢复说明](docs/operations.md)
- [实施范围](docs/implementation.md)
- [验收记录](docs/verification.md)

任务操作见 [任务管理说明](docs/task-management.md)；YouTube 的匿名访问边界和失败原因见 [YouTube 下载说明](docs/youtube-download.md)。

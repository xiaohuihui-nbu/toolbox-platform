# 目录结构与实施边界

2026-09-24：将首版 `backend/toolbox` 与 `frontend/toolbox` 的实际代码迁入约定结构。旧源码备份在本机 `artifacts/pre-layout-refactor.zip`；不含密钥、依赖或数据库，不提交 Git。运行代码不再依赖旧目录。

```text
toolbox-platform/
├── backend/
│   ├── app/
│   │   ├── core/、utils/、api/…     # 保留 FastapiAdmin 模块
│   │   ├── alembic/versions/       # 基座统一迁移（旧 toolbox/0001 仅作基线）
│   │   └── toolbox/
│   │       ├── api/               # application + accounts/tools/jobs/assets/providers/search/downloads
│   │       ├── models/            # entities.py、database.py
│   │       ├── schemas/           # HTTP 请求及插件输入契约
│   │       ├── services/          # 任务提交事务、结果序列化、初始化、账号维护
│   │       ├── contracts/         # ToolSpec / ToolContext / ToolResult
│   │       ├── registry/          # 经审核的 manifest 加载、重复 ID / 契约校验
│   │       ├── runtime/           # 插件 runner、子进程、取消、受限网络出口
│   │       ├── jobs/              # 执行、心跳、outbox、失联恢复
│   │       ├── storage/           # S3、配额、媒体 Range 处理
│   │       ├── search/            # 视频检索、短期结果和归属校验
│   │       └── providers/         # GPT-SoVITS 提交、轮询、取消与结果获取
│   ├── plugins/
│   │   ├── demo_echo/             # 文本导出示例插件
│   │   ├── video_download/        # yt-dlp 下载
│   │   ├── tts/                   # eSpeak 与 GPT-SoVITS
│   │   ├── audio_convert/         # FFmpeg 提取音频
│   │   ├── browser_tools/         # JSON / Base64 的目录描述
│   │   └── video_highlight/       # 仅规划说明，未注册为可用工具
│   ├── workers/                  # celery_app.py + 固定 tasks.py
│   ├── tests/toolbox/             # 集成、Range、搜索/批量测试
│   └── toolbox-alembic.ini
├── frontend/web/
│   ├── src/
│   │   ├── views/toolbox/         # Workspace 页面入口
│   │   ├── components/toolbox/    # DynamicForm / ResultRenderer / MediaPreview
│   │   ├── tool-views/            # VideoDownloader 专用界面
│   │   ├── api/toolbox/           # Toolbox HTTP 客户端
│   │   ├── composables/toolbox/   # 账号主题、收藏状态
│   │   ├── styles/toolbox.css     # 深浅色、配色、响应式样式
│   │   └── main.ts               # 当前前端入口
│   ├── tests/toolbox/             # 浏览器、TTS/视频、搜索批量验收
│   └── tsconfig.toolbox.json      # 当前产品的类型检查范围
├── services/voice-engine/         # 固定目标中继 gateway.py、模型服务说明
├── deploy/
│   ├── compose.yaml              # 正式部署入口
│   ├── compose.dev.yaml          # API 自动重载、Worker 源码挂载
│   ├── Dockerfile.backend
│   ├── Dockerfile.web
│   ├── nginx/default.conf
│   ├── mysql/toolbox.cnf
│   └── redis/redis.conf
├── scripts/                      # start / stop / start-tts
├── .env.example
├── upstream-lock.json
└── docs/
```

## 常用入口

| 操作 | 入口 |
|---|---|
| 新增接口 | `backend/app/toolbox/api/`，并在 `integration.py` 注册 router |
| 修改任务规则 | `services/jobs.py`；执行与失联处理在 `jobs/` |
| 新增后端工具 | `backend/plugins/<name>/manifest.json` 与处理器，随审核后的镜像自动扫描 |
| 修改公共表单 | `frontend/web/src/components/toolbox/DynamicForm.vue` |
| 修改搜索与批量下载 | `frontend/web/src/tool-views/VideoDownloader.vue` |
| 接入语音服务 | `backend/app/toolbox/providers/gptsovits.py` 与 `services/voice-engine/` |
| 数据库迁移 | `backend/app/alembic/versions/` |
| 本机启动 | 根目录运行 `./scripts/start.ps1 -SkipBuild -WithTts` |

## 迁移约束与尚未实现部分

- Compose 项目名仍为 `toolbox-platform`，MySQL/Redis/MinIO 卷名不变；迁移没有删除数据，也没有重新生成管理员。
- 迁移统一进入基座 Alembic 链；旧 `tb_schema_version/0001` 保留初始建库基线。当前 revision 为 `tb_0003_execution`。
- 实际复用 FastapiAdmin 应用工厂、身份、角色/菜单权限、登录、操作审计与迁移；前端使用 Vue Router/Pinia，管理弹窗使用 Element Plus 和原生 API，保留工作台布局。
- `search/` 当前实现站点视频搜索；全平台文档提取、MySQL 全文索引、结果生命周期清理还未实现。没有引入 ES 或 Nacos。
- 插件是随镜像发布的可信代码，尚不支持在线上传、热安装、依赖沙箱与 GPU 资源编排。`video_highlight/` 不代表高光剪辑功能已可用。

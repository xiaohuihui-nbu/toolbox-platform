# 部署与运维

Compose 项目名固定 `toolbox-platform`，仅 Web 发布 18990 端口，MySQL/Redis/MinIO 数据卷均有该前缀，不复用其他项目服务。

```powershell
docker compose --env-file .env -f deploy/compose.yaml ps
docker compose --env-file .env -f deploy/compose.yaml logs --tail 100 api worker download-worker provider-worker search-worker dispatcher
docker compose --env-file .env -f deploy/compose.yaml restart api worker download-worker provider-worker search-worker dispatcher
```

代码变更后运行 `scripts/start.ps1`。迁移由 bootstrap 一次性服务执行；schema 变更必须新增 Alembic revision，不改已发布的 `0001_schema.sql`。生产进程不自动生成迁移。镜像固定版本标签尚非 digest，正式发行应保存镜像并固定摘要。

## LAN 访问

默认只绑定 `127.0.0.1`。需要团队访问时，设置 `.env` 的 `BIND_ADDRESS=0.0.0.0` 或 LAN 网卡地址，防火墙仅放行可信网段，执行 `docker compose --env-file .env -f deploy/compose.yaml up -d web`。正式团队使用应配置 HTTPS 并设 `TB_COOKIE_SECURE=true`。HTTP 本机开发不能开启 Secure Cookie。

## 配置

| 变量 | 默认 / 说明 |
|---|---|
| WEB_PORT | 18990 |
| TB_DATABASE_URL | 独立 MySQL URL，手填密码需 URL 编码 |
| TB_REDIS_URL | 内部 Redis DB 0 |
| TB_S3_ENDPOINT / ACCESS_KEY / SECRET_KEY | S3 兼容存储；当前本机版使用 MinIO 根凭证，正式环境改为桶权限账号 |
| TB_ADMIN_PASSWORD | 仅首次创建 admin，不持续重置密码 |
| TB_MAX_UPLOAD_MB | 100；修改需同步前端和 Nginx 上限 |
| TB_USER_STORAGE_MB | 2048；每账号文件配额，单位按 MiB 计算，与磁盘容量无关 |
| TB_MAX_ACTIVE_JOBS | 25 |
| ACCESS_TOKEN_EXPIRE_SECONDS | FastapiAdmin 会话有效期，默认 12 小时；旧 TB_SESSION_HOURS 不再控制登录 |
| FA_SECRET_KEY | 原生 JWT 签名密钥，启动脚本生成 |
| FA_ALLOWED_HOSTS | 允许访问 API 的主机 JSON 数组；LAN 访问需增加实际域名/IP |
| TB_DOWNLOAD_PROXY | http://egress:8899 |
| TB_GPTSOVITS_ORIGIN | http://host.docker.internal:9880；仅固定目标语音中继使用 |
| TB_EGRESS_DOH | 可选可信 DNS-over-HTTPS JSON 解析地址；本机已设 https://dns.google/resolve 适配 TUN 假 IP |
| TB_EGRESS_DOMESTIC_DOH | B站相关域名的可选解析器；本机设 https://dns.alidns.com/resolve，解决同源对照中已复现的路径性能差异 |
| TB_EGRESS_DOMESTIC_DOMAINS | 按域名标签边界匹配的后缀列表，默认 bilibili.com,bilivideo.com,bilivideo.cn,biliimg.com,hdslb.com,b23.tv |

当前宿主网络把公网域名解析到 `198.18.0.0/15`。仅当域名解析全部命中这个范围且显式配置 DoH 时，代理才查询可信解析器，并再次验证返回公网地址、固定 IP 连接。内网域名、回环/链路地址和用户直接输入的假 IP 仍被拒绝；不能用放行整个假 IP 网段解决下载问题。

backend 镜像暂保留完整上游依赖并加 Celery/yt-dlp；瘦身应单独回归，不能直接删上游传递依赖。

## “我的存储”为什么显示 2 GB

这是当前每个账号的文件配额：`TB_USER_STORAGE_MB=2048`。后端 `/api/stats` 返回该上限，界面据此显示 2 GB；MinIO 只按已上传文件占用空间，并没有为账号预先分配 2 GB。该配置当前对所有账号统一生效，不是管理员单独限额。

例如，将项目根目录 `.env` 中该项设为 `TB_USER_STORAGE_MB=20480` 可将每账号配额改为 20 GiB。等待执行中的任务完成后，在项目根目录执行以下命令载入新环境，刷新网页即可。无需改数据库、重建镜像或移动文件；仅 `restart` 不更新容器环境。

```powershell
docker compose --env-file .env -f deploy/compose.yaml up -d --no-deps api worker download-worker provider-worker
```

此示例只是配置说明，本次下载优化没有调整实际配额。总配额与单文件限制不同：当前上传、视频产物、前端和 Nginx 仍有 100 MB 相关限制，调大总配额不会自动放开大视频限制。删除任务记录会保留文件，所以不会释放文件配额。

文件实际位于 Docker 管理的 MinIO 数据卷，不是项目源代码目录。扩容时需同时关注 Docker Desktop 数据盘所在宿主磁盘剩余空间；容器 `df` 中虚拟磁盘的可用数字不等于宿主盘可以实际写入的容量。

## 重置管理员密码

修改 `.env` 中 `TB_ADMIN_PASSWORD`（至少 8 位），执行 `docker compose --env-file .env -f deploy/compose.yaml up -d` 更新容器环境，再执行 `docker compose --env-file .env -f deploy/compose.yaml exec -T api python -m app.toolbox.services.admin reset-admin`。该命令会更新数据库密码并撤销 admin 的旧会话；普通重启不会自动重置密码。网页修改密码的最小长度同为 8 位。

## 备份与恢复

维护窗口暂停 API/worker/dispatcher，备份 MySQL 与 S3，确保二者一致；`.env` 单独加密保存，不放公开仓库。

1. `docker compose --env-file .env -f deploy/compose.yaml stop api worker download-worker provider-worker search-worker dispatcher`。
2. 用容器内 `mysqldump --single-transaction` 导出 toolbox 到容器临时文件，再通过 `docker compose --env-file .env -f deploy/compose.yaml cp` 拷到带日期的备份目录。
3. 对停止状态的 MinIO 卷做快照，或用 S3 备份客户端镜像私有桶。
4. `docker compose --env-file .env -f deploy/compose.yaml start api worker download-worker provider-worker search-worker dispatcher`。
5. 先恢复到新项目/新卷，校验 schema、账号、任务与文件，再考虑正式恢复。

已提供 `scripts/identity-rehearsal.py` 数据库副本恢复演练及 `scripts/deploy-identity.py` 冻结、快照、迁移、发布脚本；两次正式迁移已有 SQL 快照和旧镜像清单。尚未完成 S3＋MySQL 全套灾难恢复演练。`docker compose --env-file .env -f deploy/compose.yaml down -v` 会删除本项目数据，不是日常停止方式。

## 当前运维边界

- MinIO 社区项目已归档；本机使用已缓存固定版本 `RELEASE.2025-02-28T09-55-16Z`。长期部署应迁移受维护的 S3 实现；接口已通过 boto3 隔离。
- 还没有文件删除/回收站/自动保留期；配额满后拒绝新增文件，后续补引用检查和删除流程。
- S3 成功但 DB 提交失败可能留下孤立对象，需补带最小存活时间和引用对账的 GC。不能盲目设置全桶到期删除。
- 上游登录/操作审计已接入；尚未做长期压测、告警和 TLS 自动化。
- eSpeak NG 中文为机械基础音色，不等同 Voice-Pro/GPT-SoVITS 的自然音质。
- 视频解析受源站限制，不保证每个站点可用；升级 yt-dlp 需回归样例。
- Celery 使用 Linux 容器，不在原生 Windows 运行 Worker。


## 语音与开发模式

GPT-SoVITS 启动及服务协议见 `services/voice-engine/README.md`。自然配音中继在 Compose 内，模型进程独立于 Compose；`scripts/stop.ps1` 不停止独立模型项目。

开发模式：根目录执行 `docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.dev.yaml up -d`。在 `frontend/web` 执行 `npm run dev`，访问 Vite 的 18991 端口，API 代理到 18990。API 会自动重载；修改 Worker/插件后需要同步重启 API、worker、download-worker、provider-worker、search-worker 和 dispatcher，使注册表摘要一致。退出开发模式后重新运行标准 compose，会移除源码挂载。

迁移后的唯一部署文件是 `deploy/compose.yaml`。所有手工 Compose 命令均从项目根目录运行并显式指定 `.env` 和 `-f`；不要使用保留的上游 `docker/` 脚本启动 Toolbox。

## 基座升级与验收

新环境使用 `scripts/start.ps1`。已有业务数据的 schema 升级先完成隔离副本演练，构建镜像和前端，再运行 `python scripts/deploy-identity.py`：脚本确认没有排队/执行/待核对任务，暂停 API 后复查，停止所有消费者，保存 SQL 快照和旧镜像 ID，然后迁移并统一启动。不要在活动任务运行时用新代码覆盖旧处理器。

只读上线检查：`docker compose --env-file .env -f deploy/compose.yaml exec -T api python -m tests.toolbox.identity_deployment_check`。首次身份切换时可加 `--strict-migration-snapshot` 检查旧密码散列和偏好；后续用户合法改密/改主题后不应再使用此严格模式。

管理员调用 `GET /api/v1/toolbox/admin/runtime` 可检查 download/media_cpu/provider_io 是否有存活且版本一致的消费者。离线或版本不一致时，提交对应任务返回 503，而不是排入无人消费的队列。

原版后台入口为 `/admin/`，工作台为 `/`；两端使用同一 HttpOnly 会话。前端发布需在 `frontend/web` 执行 `npm run build`，包含工作台与后台两个构建，随后重建 web 镜像。只执行 `build:workspace` 会清空包含后台的旧 dist。原生页面验收使用 `node tests/toolbox/native-admin-check.mjs`，创建的临时角色由测试清理。

B 站媒体节点 `*.mcdn.bilivideo.cn:8082` 已加入出口的限定端口规则；仍禁止非公网 DNS 地址。不要为下载问题整体关闭出口限制。遇到“代理连接失败”应检查网络和节点可达性，不能将下载器的“高码率需会员”说明当作所有画质需要登录。

故障注入测试 `execution_acceptance.py` 只允许运行在 `toolbox_identity_rehearsal` 数据库，且必须停止该副本的 dispatcher；不要在正式库执行。SQL 快照包含私有业务数据，保存在已忽略的 artifacts 目录，不提交仓库。

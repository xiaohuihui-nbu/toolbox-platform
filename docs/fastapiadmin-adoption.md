# FastapiAdmin 基座接入与实施记录

更新：2026-09-24。当前阶段：基座复用已落地并上线，插件注册、任务租约/事件和资源队列已完成一批可靠性改造；全套方案仍有后续项，未声明全部完成。

## 已落地

- 单一应用工厂：`app:create_app --factory`；`TOOLBOX_ENABLED=true` 装配工具箱和已使用的系统管理模块，不启动无关 AI/定时调度模块。
- 单一身份：`sys_user/sys_role/sys_menu` 及其关系表；原 UUID 账号映射到整数主键。`tb_user_profiles` 仅保存偏好和迁移映射，无密码或独立会话。
- 同一登录服务：工具箱 JSON 登录适配调用上游 `LoginService`，JWT 保存在 HttpOnly Cookie；原生 FastapiAdmin Bearer token 同样能访问工具箱。旧 opaque Cookie 失效，切换后需重新登录一次，原账号密码继续生效。
- 同一权限来源：普通账号的工具目录与任务提交受角色菜单权限 `toolbox:tool:<tool_id>` 控制；启停状态继续生效。任务/文件所有权不因超级管理员身份而绕过。
- 同一审计：工具箱操作通过 `OperationLogRoute` 写入上游 `sys_operation_log`；密码字段脱敏；登录服务写 `sys_login_log`。
- 标准接口 `/api/v1/toolbox`；原 `/api` 兼容路径保留给旧客户端、音视频链接。原生管理 API 在 `/api/v1/system`。
- 工作台使用 Vue Router 和 Pinia；原 `#home` 等链接兼容为 `#/home`。共享 Pinia 创建入口，原管理端入口独立构建并发布。Element Plus 管理弹窗按需加载，首屏不加载其整套资源。
- 页面入口：**偏好设置 → 用户、角色与审计管理**。支持账号列表/名称/状态/角色分配、新建角色、工具授权、操作日志查询。新增成员继续使用同页原有表单，调用上游用户服务。
- 数据库连接退出与提交调整为相关路由函数作用域，避免先向客户端返回创建成功、随后才提交事务的竞态。

原生管理端现已单独发布到 `/admin/`，复用上游布局、侧栏、页签、表格、表单和主题设置；工具箱工作台保留原布局。已接入用户、角色、菜单、部门、岗位、字典、操作/登录日志页面。未接入的 AI、通知、定时调度等模块不显示为可用菜单。

## 迁移与恢复材料

正式迁移前先备份、恢复到独立数据库 `toolbox_identity_rehearsal`，使用 Redis DB 2 与独立桶演练。正式切换时关闭新任务入口并确认无活动任务，再备份、迁移和更新服务。

- 演练脚本：`scripts/identity-rehearsal.py`。
- 正式切换脚本：`scripts/deploy-identity.py`，可用于经过隔离演练的后续 schema 升级，重复 bootstrap 不会覆盖用户权限。
- 冻结迁移：`backend/app/alembic/versions/tb_0002_identity.py` 和同名 schema JSON；后续迁移统一放入基座 Alembic 目录。
- 原 `tb_schema_version` 链仅保留作为 v0.1 建库基线；bootstrap 先检查旧基线，再执行基座 `alembic.ini`。
- `tb_users_legacy` 和任务/文件的 `legacy_owner_id` 保留恢复依据，不参与登录。旧对象键不移动、不重写。
- 正式切换快照：`artifacts/identity-adoption/cutover-20260924-142818.sql`；后续执行迁移快照为 `cutover-20260924-150200.sql`；每次发布的旧镜像清单位于同目录。含私有数据，已由 Git/Docker ignore 排除，禁止对外提交。
- 自动 downgrade 不删除新身份数据。需要回滚时先冻结写入，对新阶段数据另行备份，再在隔离库恢复快照，核对后切换相应旧镜像；不可只切旧代码继续访问新 schema。

本次迁移不更改对象内容，已逐个 HEAD 校验现有对象大小。数据库恢复演练不等于 MySQL＋S3 完整灾难恢复验收。

## 验证

- `backend/tests/toolbox/identity_adoption.py`：独立副本真实服务验证，覆盖身份/密码散列/归属迁移、两个方向的统一认证、角色拒绝/授予立即生效、Celery/outbox 真实产物、owner 隔离、禁用账号、改密撤销会话、上游审计和登出。
- `backend/tests/toolbox/identity_deployment_check.py`：正式环境核对原密码散列、偏好、任务/文件归属、所有存储对象、原生管理 API、GPT-SoVITS 音色和现有媒体 Range 预览。偏好与旧快照的严格比较只适用于用户尚未在迁移后修改偏好的时点。
- `frontend/web/tests/toolbox/identity-admin-check.mjs`：真实创建测试角色、保存 JSON 工具授权、给测试账号分配角色、审计表显示、移动端无溢出与无 JS 异常；测试账号/角色通过上游软删除清理。
- `studio-check.mjs`：主题、移动端和原交互回归通过；测试结束恢复原始偏好。
- `preview-entry-check.mjs`：迁移后播放器已有验证；引入 Vue Router 后路径断言随 `#/files` 更新，列表/卡片/看板预览、下载回执播放器及移动端预览均已再次通过。
- TypeScript/Vite 构建通过。管理弹窗独立资源约 JS 293 KB、CSS 358 KB（未压缩），主入口约 JS 199 KB、CSS 65 KB。

## 发布配置

`FA_SECRET_KEY` 用于原生 JWT 签名，启动脚本自动生成随机值，不打印；`FA_ALLOWED_HOSTS` 默认允许本机与内部 API 主机。内网域名/IP 访问需将对应主机加入 JSON 数组。Cookie Secure 与 HTTPS 按部署环境设置。

当前无 ES/Nacos。后端服务统一使用 `toolbox-platform-backend:0.2.0`。本次 Docker Hub 元数据访问超时，使用本机已有 `0.1.0` 依赖层构建增量镜像；标准 Dockerfile 仍是全量重建入口，首次干净构建需要可访问镜像源。

## 剩余实施清单

- [x] 身份/角色/菜单/权限接入与安全迁移。
- [x] 原生管理接口、审计、工作台管理入口、路由和状态管理。
- [x] JSON manifest 扫描、插件/工具版本、Schema hash、实现摘要、profile 和 worker 能力心跳。
- [ ] 完整 SDK 的 request 执行入口、多产物及更多表单控件。
- [x] attempt/事件持久化、投递与执行租约、最多 8 次投递、过期恢复、外部结果不确定状态。
- [ ] 业务瞬态自动重试、新 attempt 恢复策略、外部结果自动对账闭环。
- [x] 下载 / 媒体 CPU / provider I/O 独立队列与消费者。
- [ ] provider 改为短步骤提交/查询/收集；当前仍为有界轮询。
- [ ] 文件生命周期、引用、checksum、额度预留、删除和安全清理。
- [ ] provider 管理、配置版本与任务快照、站内元数据搜索。
- [ ] 动态表单子集/预设、多产物结果、音频格式转换、时间戳等首版差项。
- [ ] CI、故障矩阵、完整备份恢复、运行指标与交付验收。

全文索引、SSE、ASR/AutoClip/GPU 依方案作为后续扩展，不与首版未完成项混淆。

## 本轮任务执行改造验收

- 迁移 `tb_0003_execution` 已在隔离副本演练并正式执行。历史文件对象键保持不变；升级前任务标为未记录插件来源，不伪造历史事件。
- `execution_acceptance.py` 使用真实 MySQL/S3，验证输入不可变、重复消息只提交一份资产、旧 attempt 拒绝、插件版本拒绝、broker 调用时数据库锁已释放、丢失投递租约恢复、次数上限、执行租约失效拒绝产物、S3 补偿清理、外部不确定状态、禁止删除未核对任务、事件游标。
- Broker 故障通过替换发布函数注入，数据库锁竞争使用第二条真实连接验证；不等同于完成 Redis 进程停机和全量故障矩阵。
- `identity_adoption.py` 还验证了原生管理权限不重新登录即可授予，以及菜单软删除立即撤权。
- 生产只读检查验证所有资源 profile 的消费者存活且注册表摘要一致、原账号与对象归属、全部存量对象大小及媒体 Range 请求。
- 管理页面修正角色加载期间可编辑导致的竞态；保存工具权限会保留原生角色的部门数据权限。
- 新增插件指南已更新为 JSON manifest 自动扫描，并说明 bootstrap 只创建新增权限项，不自动追加已有角色授权。

运行预算当前为每工具 840 秒软预算、870 秒硬限制（队列全局上限 900 秒），每次投递的超时从任务快照读取。文件产物当前仍限制 100 MiB，账号总配额沿用现有环境配置；这不等于已经完成方案里的 2 GiB 单次下载能力。

最终发布快照：`artifacts/identity-adoption/cutover-20260924-150917.sql`；镜像一致性清单：`artifacts/identity-adoption/release-20260924.json`。最后一轮管理页 5 项、执行记录页面 2 项、主题与响应式 10 项检查通过；已移除临时演练容器，演练数据库与备份保留。


## 原版后台页面发布（2026-09-24 15:54）

- 入口：工作台偏好设置 → **打开 FastapiAdmin 后台**，或 `/admin/#/home`。原工作台保持 `/`。
- 原生布局和系统管理页面复用同一数据库与服务；首页展示实际执行器状态。bootstrap 幂等补充已接入的原版菜单和字典，保留已有角色授权。
- 管理端使用与工作台相同的 HttpOnly Cookie，前端不保存 JWT。普通成员进入后台会返回工作台。独立登录页移除示例账号、演示密码及未接入的注册/短信/二维码入口。
- `npm run build` 先构建工作台，再通过 `vite.admin.config.ts` 输出 `dist/admin/admin.html`。Nginx 配置 `/admin/` 独立回退。
- Tailwind 扫描限定 `src`；Sass 不启动并行预处理 worker。内存紧张机器可设置 `NODE_OPTIONS=--max-old-space-size=2048 --max-semi-space-size=8`。Vue I18n 使用 AST 解释方式兼容既有 CSP，无需开放 `unsafe-eval`。
- 原版管理端构建成功；`native-admin-check.mjs` 在隔离副本和正式入口均通过 11 项检查（独立登录、共享会话、七个管理页面、真实新增角色、刷新、统一登出）。仅断言实际覆盖的流程，不等同于上游所有功能全量验收。
- 发布前数据库备份：`artifacts/identity-adoption/cutover-20260924-154947.sql`。发布后现有对象、任务归属、全部资源队列和媒体 Range 检查通过。

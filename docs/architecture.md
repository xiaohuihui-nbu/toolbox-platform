# 当前架构与插件指南

更新：2026-09-24。运行基础为 FastapiAdmin，实施清单见 [基座接入记录](fastapiadmin-adoption.md)。不使用 ES/Nacos。

## 应用与数据

浏览器通过 Nginx 访问唯一的 `app:create_app` 应用工厂。原生管理路由为 `/api/v1/system`，工具业务为 `/api/v1/toolbox`；旧 `/api` 路径保留兼容。Vue Router 管理工作台路由，Pinia 保存当前用户状态；管理弹窗使用 Element Plus 和原生管理接口。

| 数据 | 实际实现 |
|---|---|
| 账号/角色/菜单/授权 | FastapiAdmin `sys_user/sys_role/sys_menu` 及其关系表；原生 JWT、Redis 会话与密码服务 |
| 审计 | `sys_login_log`、`sys_operation_log`；写操作使用原生 OperationLogRoute |
| 偏好 | `tb_user_profiles`，仅主题、收藏、旧 UUID 映射 |
| 任务 | `tb_jobs` 保存输入、插件/工具版本、Schema hash、配置快照和父任务 |
| 执行 | `tb_job_attempts`、`tb_job_events`、`tb_outbox` 保存领取租约、事件和投递状态 |
| 执行器 | `tb_worker_heartbeats` 保存资源类型、注册表摘要和数据库时间心跳 |
| 文件 | `tb_assets` 保存所属用户与对象键；产物保存在私有 S3 桶 |
| 迁移 | 基座 Alembic `tb_0002_identity → tb_0003_execution`；旧 0001 仅用于初始基线 |

`tb_users_legacy` 只作迁移恢复依据，不参与身份验证。保留上游源码不等于启用了所有模块；当前没有启动其 AI、任意代码定时任务等无关功能。

## 任务链路

1. 提交时检查角色权限、启停、Schema、文件归属、活动数量及同版本执行器是否存活。以用户行锁串行检查任务额度，在同一事务创建 job、attempt、accepted event 和 outbox。
2. `(owner_id,idempotency_key)` 唯一；不同输入复用同一键返回 409。排队任务改参会原子取消旧任务并创建关联新任务，保留历史输入。
3. dispatcher 每 3 秒扫描，数据库时间控制 30 秒投递租约。提交数据库事务后再发布 Redis 消息。发布失败指数退避；已发布而未领取的任务在工具预算加 60 秒后可重投，最多 8 次。
4. 消息只传 job/attempt ID。worker 校验当前 attempt、插件/工具版本、Schema 和实现摘要，再领取 60 秒执行租约；每 5 秒续租。
5. 上传产物在数据库事务外完成，使用 attempt 独立对象键并校验大小和 SHA-256 元数据。最终以有效租约及用户额度检查提交资产和成功状态，拒绝的对象尝试补偿删除。
6. 失联执行器不能提交结果。失联后本地任务收敛为失败；已向外部服务提交但结果不确定的任务进入 `reconciling`，不自动重复生成。远程提交 ID 保存在任务和 attempt 中。
7. 取消采用数据库状态与子进程组 SIGTERM/SIGKILL。Celery `task_reject_on_worker_lost=false`，避免自动崩溃循环。
8. `/jobs/{id}/events?after=<event_id>` 返回所属用户的事件与尝试记录；页面任务详情可查看。升级前记录没有伪造的尝试历史。

资源分开消费：`toolbox.download` 并发 2、`toolbox.media_cpu` 并发 1、`toolbox.provider_io` 并发 2。视频搜索继续使用独立 `toolbox-search`。`/admin/runtime` 供管理员核对各资源执行器及版本一致性。

当前仍需注意：provider 内部尚为有界轮询，自动对账和短步骤未完成；`reconciling` 不允许直接删除/重试。S3 补偿删除失败或进程硬杀仍可能留下孤立对象，定时 GC 未完成；也未完成全局运行额度预留及后代进程硬杀验收。这些不以本轮正常路径测试代替。

## 新增自研工具

插件是经过审查、随镜像发布的代码。参考 `backend/plugins/demo_echo/`：

1. 新建 `backend/plugins/<package>/manifest.json`、`__init__.py`、`handler.py`；输入模型放在同插件的 `schema.py`，使用 Pydantic 严格模型定义长度、类型和范围。
2. 清单填写插件 ID/version/sdk_version=1，工具 ID/version、展示字段、执行模式、handler、schema_ref、resource_profile、timeout_seconds、max_output_bytes。处理器只允许本插件命名空间。
3. `execute(context)` 返回 `ToolResult(output=Path)`。输出必须在 context.directory 内，为非空普通文件。使用 context.check() 响应取消；子进程调用使用 `runtime/process.py`，不拼接 shell 命令。
4. 注册表自动扫描镜像内 `plugins/*/manifest.json`，无需修改中央 handler 映射。重复 ID、越界预算、未知 profile 或不符合命名空间的处理器使启动失败。生产发布需要同步 API/所有 worker；仅重启 API 会导致版本不匹配。
5. bootstrap 为新增工具建立原生菜单权限 `toolbox:tool:<id>`；已有角色不会被自动追加权限或重新授权。管理员在“偏好设置 → 用户、角色与审计管理”分配新权限。
6. 使用成功、无效参数、越权、重复投递、取消和版本不匹配样例验收。新工具的复杂编辑器按需放在 `frontend/web/src/tool-views/`。

清单示例（展示字段可参照现有 demo_echo）：

```json
{
  "plugin_id": "my_tool",
  "version": "1.0.0",
  "sdk_version": 1,
  "tools": [{
    "id": "my.tool", "name": "我的工具", "category": "文本工具",
    "description": "处理输入并输出文件", "icon": "FileText", "color": "green", "tags": [],
    "version": "1.0.0", "mode": "job",
    "handler": "plugins.my_tool.handler:execute",
    "schema_ref": "plugins.my_tool.schema:Input",
    "resource_profile": "media_cpu", "timeout_seconds": 60,
    "max_output_bytes": 1048576
  }]
}
```

当前完整支持的执行入口为 job 与已有 browser 工具；request 模式的执行 API、复杂 JSON Schema 表单、多产物 ToolResult 和配置版本管理仍待实现。不要仅声明一个尚未实现的模式就将工具对外发布。

## 访问与发布边界

任务、文件和事件按 owner_id 验证，超级管理员也不能默认读取其他账号私有文件。角色、菜单停用或软删除会在下次请求生效，原生接口和工具接口均从数据库更新授权。

浏览器 Cookie 使用 HttpOnly/SameSite=Strict，写操作校验 Origin。下载器使用固定出口代理验证公网地址。新增 provider 的地址不能由普通用户任意传入。部署及备份步骤见 [operations.md](operations.md)。

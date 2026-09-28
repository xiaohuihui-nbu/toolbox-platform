# 实施范围（2026-09-24）

已完成约定目录迁移、当前七个工具、任务/文件中心、账号隔离、主题设置，以及 GPT-SoVITS 接入、媒体预览、B站/YouTube 搜索和每批最多 20 条下载。

后端实际入口是 FastapiAdmin 的 `app:create_app --factory`，Celery 为 `workers.celery_app:celery`，分发器为 `app.toolbox.jobs.outbox`。前端主入口在 `frontend/web/src/main.ts`，接入 Vue Router、Pinia，管理弹窗按需加载 Element Plus。Compose 正式与开发入口均在 deploy。

已接入上游应用工厂、用户/角色/菜单模型、认证服务、JWT/Redis 会话、权限服务、原生系统管理 API 和操作审计；账号、任务、文件归属完成迁移。工具箱表单与结果协议、可靠任务、provider 配置和文件生命周期仍待按全套方案补齐。在线任意插件安装不在方案范围；全文索引、GPU、ASR/AutoClip 属后续阶段。数据库副本恢复和身份迁移演练已做，完整 MySQL＋S3 灾难恢复演练尚未完成。详见 [基座接入记录](fastapiadmin-adoption.md)。

具体目录及边界见 [directory-layout.md](directory-layout.md)，使用方法见 [media-tools.md](media-tools.md)，测试证据见 [verification.md](verification.md)。

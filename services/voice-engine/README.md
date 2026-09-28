# 独立语音服务边界

`gateway.py` 是固定目标 GPT-SoVITS API 的中继，运行于 Compose 的 `tts-gateway` 服务。平台与 CPU/GPU 模型依赖分离，不在 API/Worker 镜像里安装 Torch 或模型。

当前使用已有 `E:\xhh\projects\gpt-sovits-cpu`，执行 `scripts/start-tts.ps1` 启动；也可用 `scripts/start.ps1 -WithTts` 一起启动。默认目标 `http://host.docker.internal:9880`，用根目录 `.env` 中 `TB_GPTSOVITS_ORIGIN` 覆盖。

协议：`GET /health`、`GET /api/voices`、`GET /api/voices/{id}/preview`、`POST /api/jobs`、`GET /api/jobs/{id}`、`POST /api/jobs/{id}/cancel`、`GET /audio/{filename}`。这是现有 local_studio 的异步协议，不是任意 GPT-SoVITS 原生 `/tts` 接口；更换服务需要实现适配器。

只有中继服务能访问模型宿主机。模型文件和训练环境继续由独立语音项目维护；本目录不重复复制模型。

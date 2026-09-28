# 视频搜索排查与修复（2026-09-24）

## 已确认问题

搜索队列正常接收任务。B 站搜索上游多次返回 HTTP 412，原来统一映射成“搜索平台请求失败或超时”，前端同时显示“暂未找到结果”，无法区分源站拒绝和真正零结果。

原请求使用随机生成的 `buvid3` Cookie，缺少 Referer。修正为无登录 Cookie 的公开搜索请求并补充正常 Referer 后，得到真实结果，但仍观察到同样请求间歇性返回 412。因此不能把 Cookie 认定为唯一原因，也不能保证所有关键词搜索成功。

## 已部署调整

- 移除临时生成的设备 Cookie，补充 B 站 Referer，继续经过原有受限出站代理。
- 成功的公开搜索结果缓存 120 秒，键包含平台、关键词和数量；搜索票据和缩略图接口仍检查所有者。失败不写入成功缓存。
- 区分 HTTP 401/403/412、429、其他 HTTP 错误、网络超时和异常响应，不向前端回传带请求信息的 HTTP 异常文本。
- 前端将搜索失败与零结果区分；失败时显示原站搜索入口，可在站内找到视频后回到“粘贴链接”。未更改页面整体布局和配色。
- 更新了 search-worker 和 web；未重启下载 worker。

## 验证结果及限制

- `backend/.venv/Scripts/python.exe -m pytest tests/toolbox/test_video_search.py -q`：10 项通过，覆盖请求头、结果格式、源站限制、错误分类、任务状态和公开结果缓存。
- 前端 TypeScript/Vite 构建通过。
- `node tests/toolbox/search-error-check.mjs`：模拟 HTTP 412 的错误提示、URL 编码、禁止空选择下载、粘贴链接入口检查通过。
- `node tests/toolbox/search-regression-check.mjs`：真实页面搜索“舞蹈”返回 8 条，约 2.4 秒，封面和多选正常；“音乐”返回 412；YouTube 搜索 `Blender Sintel trailer` 返回 8 条，约 36.7 秒。完整在线测试因其中一项被源站拒绝而未全通过，没有将其计为通过。

结果记录：`artifacts/search-regression.json`，真实结果截图：`artifacts/search-fixed.png`。外部站点限制仍可能出现，缓存只减少重复请求，不能解除源站访问限制。此次未重新验证视频文件下载。

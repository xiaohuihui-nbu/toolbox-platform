"""Map downloader diagnostics to safe user-facing messages, never expose raw logs."""


class DownloadFailure(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def classify_error(output):
    # A Bilibili informational line mentions cookies for unavailable premium
    # formats even when public formats were selected successfully. It is not
    # the reason the subsequent media transfer failed.
    text = "\n".join(line for line in output.lower().replace("’", "'").splitlines()
                     if not ("format(s)" in line and "are missing" in line))
    if "tunnel connection failed" in text or "unable to connect to proxy" in text:
        return DownloadFailure("proxy_connection_failed", "下载出口代理无法连接视频地址，请联系管理员检查代理端口和出口网络；这不代表视频需要登录。")
    if "not a bot" in text or "confirm your age" in text or "login required" in text or "use --cookies" in text:
        return DownloadFailure("authentication_required", "源站要求登录验证，当前免登录模式无法下载此视频。请在浏览器确认原视频的访问权限；降低画质或增加并发无效。")
    if "cookies" in text and any(word in text for word in ("expired", "no longer valid", "invalid", "netscape")):
        return DownloadFailure("cookies_invalid", "登录态已失效或 Cookie 文件格式不正确，请重新导出本人的 YouTube cookies.txt 后重试。")
    if "429" in text or "too many requests" in text:
        return DownloadFailure("rate_limited", "源站限制了请求频率，请暂停批量重试，稍后再试。")
    if any(word in text for word in ("private video", "video unavailable", "has been removed", "not available anymore", "members-only", "join this channel")):
        return DownloadFailure("video_unavailable", "视频不可用、已删除或需要访问权限，请先在原站确认本人账号能否观看。")
    if "not available in your country" in text or "geo-restricted" in text:
        return DownloadFailure("region_restricted", "视频有地区限制，当前服务器网络无法访问。")
    if "no supported javascript runtime" in text or "challenge solving failed" in text:
        return DownloadFailure("youtube_runtime", "YouTube 解析运行依赖不可用或版本不匹配，请联系管理员检查 Node 与 yt-dlp-ejs。")
    if "requested format is not available" in text:
        return DownloadFailure("format_unavailable", "当前没有匹配的下载格式，请改选最高可用画质；登录限制也可能导致可用格式缺失。")
    if "timed out" in text or "timeout" in text:
        return DownloadFailure("network_timeout", "连接源站超时，请检查服务器网络或稍后重试。")
    if "403" in text or "forbidden" in text:
        return DownloadFailure("access_denied", "源站拒绝了下载请求（403），请检查原视频访问权限和服务器出口网络。")
    if "proxy" in text or "unable to connect" in text or "name resolution" in text:
        return DownloadFailure("network_error", "下载网络或代理连接失败，请检查服务器出口服务。")
    if "larger than max-filesize" in text or "larger than max" in text:
        return DownloadFailure("file_too_large", "视频超过 100 MB 上限，请尝试较低清晰度。")
    return DownloadFailure("download_failed", "下载器未能完成处理，请检查原站可用性；管理员可用同一链接进行诊断。")

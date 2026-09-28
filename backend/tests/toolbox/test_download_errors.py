import pytest

from plugins.video_download.errors import classify_error


@pytest.mark.parametrize(
    ("diagnostic", "code"),
    [
        ("Sign in to confirm you’re not a bot", "authentication_required"),
        ("Private video", "video_unavailable"),
        ("HTTP Error 429: Too Many Requests", "rate_limited"),
        ("Requested format is not available", "format_unavailable"),
        ("No supported JavaScript runtime could be found", "youtube_runtime"),
        ("cookies are no longer valid", "cookies_invalid"),
        ("Connection timed out", "network_timeout"),
        ("HTTP Error 403 Forbidden", "access_denied"),
    ],
)
def test_error_classification_never_exposes_diagnostics(diagnostic, code):
    failure = classify_error(diagnostic + "\nCookie: PRIVATE-TEST-VALUE\nhttps://example.invalid/?token=PRIVATE-TEST-VALUE")
    assert failure.code == code
    assert "PRIVATE-TEST-VALUE" not in str(failure)


def test_bot_auth_error_takes_precedence_over_runtime_warning():
    result = classify_error("No supported JavaScript runtime could be found\nSign in to confirm you're not a bot")
    assert result.code == "authentication_required"


@pytest.mark.parametrize(("failure", "code"), [
    ("Tunnel connection failed: 403 Forbidden", "proxy_connection_failed"),
    ("HTTP Error 403 Forbidden", "access_denied"),
    ("Requested format is not available", "format_unavailable"),
])
def test_bilibili_premium_notice_is_not_a_login_failure(failure, code):
    notice = "[BiliBili] Format(s) 1080P 高码率 are missing; you have to become a premium member. Use --cookies for authentication."
    assert classify_error(notice + "\nERROR: " + failure).code == code

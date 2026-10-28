"""Session cookie attributes and CSRF origin checks."""

import asyncio
from types import SimpleNamespace

from starlette.responses import Response

from app.main import _origin_of, _same_origin_request
from app.security.session_cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)


def _cookie_headers(response: Response) -> list[str]:
    return [v.decode() for k, v in response.raw_headers if k.decode().lower() == "set-cookie"]


class _FakeRequest:
    """Just enough of a Request for the origin check."""

    def __init__(self, headers: dict[str, str], base_url: str = "http://localhost:8000/"):
        self.headers = headers
        self.base_url = base_url


def test_session_cookies_are_httponly_and_scoped():
    response = Response()
    set_session_cookies(response, "access-value", "refresh-value")
    headers = _cookie_headers(response)

    access = next(h for h in headers if h.startswith(f"{ACCESS_COOKIE}="))
    refresh = next(h for h in headers if h.startswith(f"{REFRESH_COOKIE}="))

    assert "HttpOnly" in access
    assert "SameSite=lax" in access
    assert "Path=/" in access
    assert "access-value" in access

    assert "HttpOnly" in refresh
    # 刷新令牌只在 auth 路径下发送，缩小暴露面
    assert "Path=/api/v1/auth" in refresh


def test_clear_session_cookies_expires_both():
    response = Response()
    clear_session_cookies(response)
    headers = _cookie_headers(response)
    assert any(h.startswith(f"{ACCESS_COOKIE}=") and "Max-Age=0" in h for h in headers)
    assert any(h.startswith(f"{REFRESH_COOKIE}=") and "Max-Age=0" in h for h in headers)


def test_origin_of_normalizes_absolute_urls():
    assert _origin_of("https://CookHero.example.com:443/path") == "https://cookhero.example.com:443"
    assert _origin_of("not-a-url") == ""


def test_same_origin_request_accepts_own_host():
    request = _FakeRequest({"Origin": "http://localhost:8000"})
    assert _same_origin_request(request) is True


def test_same_origin_request_rejects_foreign_origin():
    request = _FakeRequest({"Origin": "http://evil.example"})
    assert _same_origin_request(request) is False


def test_same_origin_request_falls_back_to_referer():
    request = _FakeRequest({"Referer": "http://localhost:8000/recipes"})
    assert _same_origin_request(request) is True


def test_same_origin_request_allows_non_browser_clients():
    """cURL / 服务端脚本不带 Origin/Referer，也无法被第三方页面借用。"""
    request = _FakeRequest({})
    assert _same_origin_request(request) is True


def test_logout_without_revoke_only_clears_current_browser(monkeypatch):
    """revoke=false：清 Cookie 但不递增版本，其他设备保持登录。"""
    from app.api.v1.endpoints import auth as auth_module

    bumped: list[str] = []

    async def fake_bump(user_id: str) -> None:
        bumped.append(user_id)

    monkeypatch.setattr(auth_module.token_version_service, "bump", fake_bump)
    request = SimpleNamespace(state=SimpleNamespace(user_id="u-1"))

    local_only = Response()
    asyncio.run(auth_module.logout(request, local_only, revoke=False))
    assert bumped == [], "不应吊销令牌版本"
    assert _cookie_headers(local_only), "仍要下发清除 Cookie 的响应头"

    full = Response()
    asyncio.run(auth_module.logout(request, full, revoke=True))
    assert bumped == ["u-1"], "默认登出仍是全端吊销"

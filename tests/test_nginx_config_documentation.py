"""Static invariants over the versioned record of the production host's
nginx configuration, `deploy/nginx/srv1994437.hstgr.cloud.conf`.

This file is documentation of what is already live on the VPS (T25 follow-up
/ hosted advisor URL) -- not something a deploy step applies automatically --
but it still needs to keep matching the properties the rest of this
repository depends on: the `/disclosure-gateway` routing `compose.prod.yaml`
and `web/next.config.ts`'s `ADG_WEB_BASE_PATH` assume, the upload size limit
`docs/advisor-demo.md`/`ADG_MAX_UPLOAD_BYTES` assume headroom under, and a
clear marker for which lines certbot manages so a future hand-edit does not
silently clobber certificate renewal.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_NGINX_CONF_PATH = _REPO_ROOT / "deploy" / "nginx" / "srv1994437.hstgr.cloud.conf"


class TestNginxConfigDocumentationExists:
    def test_file_exists(self) -> None:
        assert _NGINX_CONF_PATH.is_file(), (
            f"expected a versioned record of the production nginx config at {_NGINX_CONF_PATH}"
        )

    def test_names_the_host(self) -> None:
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "srv1994437.hstgr.cloud" in text

    def test_sets_the_body_size_limit(self) -> None:
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "client_max_body_size 12M" in text

    def test_redirects_bare_disclosure_gateway_path_to_trailing_slash(self) -> None:
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "/disclosure-gateway" in text
        assert "/disclosure-gateway/" in text
        assert "301" in text, "the bare-path redirect must be a permanent (301) redirect"

    def test_proxies_disclosure_gateway_to_the_loopback_web_container(self) -> None:
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "proxy_pass" in text
        assert "127.0.0.1:3000" in text

    def test_forwards_standard_proxy_headers(self) -> None:
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        for header in (
            "proxy_set_header Host",
            "proxy_set_header X-Real-IP",
            "proxy_set_header X-Forwarded-For",
            "proxy_set_header X-Forwarded-Proto",
        ):
            assert header in text, f"expected {header!r} to be forwarded"

    def test_marks_certbot_managed_lines(self) -> None:
        """Certbot rewrites this file in place on renewal; hand-edited lines
        interleaved with no marker risk being silently reformatted or
        misread as safe to change by hand. At least one line must say so.
        """
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "managed by Certbot" in text

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

    def test_does_not_redirect_or_rewrite_the_bare_disclosure_gateway_path(
        self,
    ) -> None:
        """A bare-path -> trailing-slash nginx redirect fights Next.js's own
        basePath normalization and produces an infinite redirect loop: the
        browser saw `/disclosure-gateway/` -> 308 -> `/disclosure-gateway`
        (Next normalizing) immediately followed by
        `/disclosure-gateway` -> 301 -> `/disclosure-gateway/` (this nginx
        redirect), forever. There must be no such redirect left in the file.
        """
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "/disclosure-gateway" in text
        assert "/disclosure-gateway/" in text
        assert "return 301 /disclosure-gateway/;" not in text, (
            "a bare-path redirect here loops against Next.js's own basePath "
            "normalization -- proxy both forms instead of redirecting either"
        )

    def test_proxies_disclosure_gateway_to_the_loopback_web_container(self) -> None:
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "proxy_pass" in text
        assert "127.0.0.1:3000" in text

    def test_both_gateway_locations_proxy_without_rewriting_the_request_uri(
        self,
    ) -> None:
        """Both the bare-path and trailing-slash locations must proxy, and
        the `proxy_pass` target must carry no URI part (i.e. end at
        `:3000;`). A `proxy_pass` with a URI part rewrites the forwarded
        path, which is what fought Next.js's own basePath normalization and
        produced the redirect loop this file used to encode.
        """
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "location = /disclosure-gateway {" in text
        assert "location /disclosure-gateway/ {" in text
        assert "proxy_pass http://127.0.0.1:3000;" in text
        assert "http://127.0.0.1:3000/disclosure-gateway" not in text, (
            "proxy_pass must not carry a URI part -- it must forward the "
            "original request URI verbatim"
        )

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


class TestNginxConfigDocumentationMatchesHostDirectives:
    """This file claims to be a faithful record of what is live on the host
    (see the file's own header), but inherited from PR #75 a landing-page
    `root` path that was never actually on the host, plus an `http2 on;`
    directive the host does not have. Pin the directives that must match
    the real `/etc/nginx/sites-available/default` on srv1994437.hstgr.cloud
    so this file cannot silently drift back into fiction.
    """

    def test_landing_page_root_matches_the_host(self) -> None:
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "root /var/www/landing;" in text, (
            "the host serves the landing page from /var/www/landing inside "
            "location /, not /var/www/srv1994437.hstgr.cloud/html at server "
            "level -- this file must record the real path"
        )

    def test_does_not_claim_a_server_level_landing_root_the_host_lacks(
        self,
    ) -> None:
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "/var/www/srv1994437.hstgr.cloud/html" not in text, (
            "this server-level root path is not on the host; it was "
            "inherited from PR #75 and never matched reality"
        )

    def test_does_not_claim_http2_the_host_lacks(self) -> None:
        text = _NGINX_CONF_PATH.read_text(encoding="utf-8")
        assert "http2 on" not in text, (
            "the host's HTTPS server block has no http2 directive at all -- "
            "this file must not document one that isn't there"
        )

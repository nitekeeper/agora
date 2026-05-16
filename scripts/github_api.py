# scripts/github_api.py
"""Thin wrapper around the GitHub REST API.

Used by agora's plugin-register/update/check operations to fetch repository
metadata (description, topics, homepage, SPDX license id). Standard library
only: urllib.request for HTTP, subprocess for `gh auth token`.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import warnings
from dataclasses import dataclass


def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context. Order of preference:
    1. truststore (system-native cert store; needed on Windows where the
       bundled Python OpenSSL build can't validate some chains).
    2. certifi (curated Mozilla CA bundle).
    3. stdlib default.
    Result is cached at module load."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        pass
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL_CONTEXT = _build_ssl_context()

_API_BASE = "https://api.github.com"
_USER_AGENT = "agora/0.1"
_API_VERSION = "2022-11-28"
_TIMEOUT_SECS = 10
_MAX_RATE_WAIT_SECS = 60
_GH_TIMEOUT_SECS = 5

_warned_anonymous = False


@dataclass
class RepoMetadata:
    description: str | None
    topics: list[str]
    homepage: str | None
    license_spdx_id: str | None


class GitHubAPIError(Exception):
    """Raised on GitHub API errors. Includes status code and message."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _try_gh_token() -> str | None:
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT_SECS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    token = (result.stdout or "").strip()
    return token or None


def resolve_token() -> tuple[str | None, str]:
    """Return (token, source). Source is one of: 'gh', 'GITHUB_TOKEN',
    'GH_TOKEN', 'anonymous'. Token is None for anonymous."""
    gh_token = _try_gh_token()
    if gh_token:
        return gh_token, "gh"
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        return env_token, "GITHUB_TOKEN"
    env_token = os.environ.get("GH_TOKEN")
    if env_token:
        return env_token, "GH_TOKEN"
    return None, "anonymous"


def _build_request(url: str, token: str | None) -> urllib.request.Request:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", _API_VERSION)
    req.add_header("User-Agent", _USER_AGENT)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return req


def _header_int(headers, name: str) -> int | None:
    try:
        val = headers.get(name) if hasattr(headers, "get") else headers[name]
    except (KeyError, TypeError):
        return None
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _read_json(resp) -> dict:
    body = resp.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def _error_message(payload: dict, fallback: str) -> str:
    msg = payload.get("message") if isinstance(payload, dict) else None
    return msg if msg else fallback


def _rate_limit_wait(headers) -> int:
    reset = _header_int(headers, "X-RateLimit-Reset")
    now = int(time.time())
    if reset is None:
        wait = 1
    else:
        wait = max(1, reset - now)
    return min(wait, _MAX_RATE_WAIT_SECS)


def _is_rate_limited(status: int, headers) -> bool:
    if status == 429:
        return True
    if status == 403:
        remaining = _header_int(headers, "X-RateLimit-Remaining")
        return remaining == 0
    return False


def _do_request(req: urllib.request.Request) -> tuple[int, dict, object]:
    """Perform a single HTTP request. Returns (status, payload, headers).
    Does not raise on HTTP errors — only on network errors."""
    try:
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT_SECS, context=_SSL_CONTEXT)
    except urllib.error.HTTPError as e:
        status = e.code
        headers = e.headers
        try:
            payload = _read_json(e)
        except Exception:
            payload = {}
        return status, payload, headers
    except urllib.error.URLError as e:
        raise GitHubAPIError(f"network error: {e.reason}") from e

    status = getattr(resp, "status", 200)
    headers = resp.headers
    payload = _read_json(resp)
    return status, payload, headers


def _request_with_retry(req: urllib.request.Request) -> dict:
    """Make request with one retry on rate-limit or 5xx."""
    status, payload, headers = _do_request(req)

    if _is_rate_limited(status, headers):
        wait = _rate_limit_wait(headers)
        time.sleep(wait)
        status, payload, headers = _do_request(req)
        if _is_rate_limited(status, headers):
            reset = _header_int(headers, "X-RateLimit-Reset")
            reset_msg = f"resets at {reset}" if reset else "reset time unknown"
            raise GitHubAPIError(f"rate limited; {reset_msg}", status=status)

    if 500 <= status < 600:
        time.sleep(1)
        status, payload, headers = _do_request(req)
        if 500 <= status < 600:
            raise GitHubAPIError(
                f"server error {status}: {_error_message(payload, 'server error')}",
                status=status,
            )

    if status >= 400:
        raise GitHubAPIError(_error_message(payload, f"HTTP {status}"), status=status)

    return payload


def _warn_anonymous_once() -> None:
    global _warned_anonymous
    if _warned_anonymous:
        return
    _warned_anonymous = True
    warnings.warn(
        "GitHub API requests are unauthenticated; rate limit is 60/hr. "
        "Set GITHUB_TOKEN or run `gh auth login` to raise it to 5000/hr.",
        stacklevel=2,
    )


def get_repo_metadata(owner: str, repo: str) -> RepoMetadata:
    """Fetch metadata for a GitHub repo. Raises GitHubAPIError on failure."""
    token, source = resolve_token()
    if source == "anonymous":
        _warn_anonymous_once()

    url = f"{_API_BASE}/repos/{owner}/{repo}"
    req = _build_request(url, token)
    payload = _request_with_retry(req)

    description = payload.get("description")
    if not description:
        description = None

    homepage = payload.get("homepage")
    if not homepage:
        homepage = None

    topics = payload.get("topics") or []
    if not isinstance(topics, list):
        topics = []

    license_obj = payload.get("license")
    if isinstance(license_obj, dict):
        license_spdx_id = license_obj.get("spdx_id")
    else:
        license_spdx_id = None

    return RepoMetadata(
        description=description,
        topics=list(topics),
        homepage=homepage,
        license_spdx_id=license_spdx_id,
    )

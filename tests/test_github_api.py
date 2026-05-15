# tests/test_github_api.py
"""Tests for scripts.github_api."""
from __future__ import annotations

import io
import json
import subprocess
from typing import Any

import pytest

from scripts import github_api
from scripts.github_api import (
    GitHubAPIError,
    RepoMetadata,
    get_repo_metadata,
    resolve_token,
)


# ---------- helpers ----------


class FakeHeaders:
    def __init__(self, data: dict[str, str] | None = None) -> None:
        self._data = {k: str(v) for k, v in (data or {}).items()}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> str:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data


class FakeResponse:
    def __init__(
        self,
        body: dict | str | bytes,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        if isinstance(body, (dict, list)):
            raw = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = body
        self._buf = io.BytesIO(raw)
        self.status = status
        self.headers = FakeHeaders(headers)

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        pass


def _http_error(
    status: int,
    body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    import urllib.error

    raw = json.dumps(body or {}).encode("utf-8")
    err = urllib.error.HTTPError(
        url="https://api.github.com/x",
        code=status,
        msg="error",
        hdrs=FakeHeaders(headers),  # type: ignore[arg-type]
        fp=io.BytesIO(raw),
    )
    # urllib.error.HTTPError supports .read() via the fp; make .headers work too.
    err.headers = FakeHeaders(headers)  # type: ignore[assignment]
    return err


def _ok_payload(**overrides: Any) -> dict:
    base = {
        "description": "A cool plugin",
        "topics": ["claude", "plugin"],
        "homepage": "https://example.com",
        "license": {"spdx_id": "MIT", "key": "mit"},
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _reset_warning_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level anonymous-warning flag between tests."""
    monkeypatch.setattr(github_api, "_warned_anonymous", False, raising=False)


@pytest.fixture(autouse=True)
def _clear_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)


# ---------- resolve_token ----------


def test_resolve_token_prefers_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(args[0], 0, stdout="ghp_abc\n", stderr="")

    monkeypatch.setattr(github_api.subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_TOKEN", "env_token")
    token, source = resolve_token()
    assert token == "ghp_abc"
    assert source == "gh"


def test_resolve_token_falls_back_to_github_token_when_gh_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):  # noqa: ANN001
        raise FileNotFoundError("gh not installed")

    monkeypatch.setattr(github_api.subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_TOKEN", "env_token")
    token, source = resolve_token()
    assert token == "env_token"
    assert source == "GITHUB_TOKEN"


def test_resolve_token_falls_back_to_github_token_when_gh_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="not logged in")

    monkeypatch.setattr(github_api.subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_TOKEN", "env_token")
    token, source = resolve_token()
    assert token == "env_token"
    assert source == "GITHUB_TOKEN"


def test_resolve_token_falls_back_to_gh_token_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):  # noqa: ANN001
        raise FileNotFoundError()

    monkeypatch.setattr(github_api.subprocess, "run", fake_run)
    monkeypatch.setenv("GH_TOKEN", "ght_token")
    token, source = resolve_token()
    assert token == "ght_token"
    assert source == "GH_TOKEN"


def test_resolve_token_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):  # noqa: ANN001
        raise FileNotFoundError()

    monkeypatch.setattr(github_api.subprocess, "run", fake_run)
    token, source = resolve_token()
    assert token is None
    assert source == "anonymous"


# ---------- get_repo_metadata ----------


def _patch_urlopen(monkeypatch: pytest.MonkeyPatch, responses: list[Any]) -> list[Any]:
    """Patch urlopen with a sequence of responses. Each entry is either a
    FakeResponse or an exception instance to raise. Returns the list of
    captured Request objects."""
    captured: list[Any] = []
    queue = list(responses)

    def fake_urlopen(req, timeout=None, context=None):  # noqa: ANN001
        captured.append(req)
        if not queue:
            raise AssertionError("urlopen called more times than expected")
        nxt = queue.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt

    monkeypatch.setattr(github_api.urllib.request, "urlopen", fake_urlopen)
    return captured


def _patch_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_api, "resolve_token", lambda: (None, "anonymous"))


def test_get_repo_metadata_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anonymous(monkeypatch)
    _patch_urlopen(monkeypatch, [FakeResponse(_ok_payload())])

    meta = get_repo_metadata("octocat", "hello")
    assert isinstance(meta, RepoMetadata)
    assert meta.description == "A cool plugin"
    assert meta.topics == ["claude", "plugin"]
    assert meta.homepage == "https://example.com"
    assert meta.license_spdx_id == "MIT"


def test_get_repo_metadata_empty_strings_become_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_anonymous(monkeypatch)
    payload = _ok_payload(description="", homepage="")
    _patch_urlopen(monkeypatch, [FakeResponse(payload)])

    meta = get_repo_metadata("octocat", "hello")
    assert meta.description is None
    assert meta.homepage is None


def test_get_repo_metadata_missing_license(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anonymous(monkeypatch)
    payload = _ok_payload()
    del payload["license"]
    _patch_urlopen(monkeypatch, [FakeResponse(payload)])

    meta = get_repo_metadata("octocat", "hello")
    assert meta.license_spdx_id is None


def test_get_repo_metadata_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anonymous(monkeypatch)
    _patch_urlopen(
        monkeypatch,
        [_http_error(404, {"message": "Not Found"})],
    )

    with pytest.raises(GitHubAPIError) as exc_info:
        get_repo_metadata("octocat", "missing")
    assert "Not Found" in str(exc_info.value)
    assert exc_info.value.status == 404


def test_get_repo_metadata_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anonymous(monkeypatch)
    _patch_urlopen(
        monkeypatch,
        [_http_error(401, {"message": "Bad credentials"})],
    )

    with pytest.raises(GitHubAPIError) as exc_info:
        get_repo_metadata("octocat", "hello")
    assert exc_info.value.status == 401
    assert "Bad credentials" in str(exc_info.value)


def test_rate_limit_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anonymous(monkeypatch)
    sleeps: list[float] = []
    monkeypatch.setattr(github_api.time, "sleep", lambda s: sleeps.append(s))
    # Freeze "now" to make the wait calculation deterministic.
    monkeypatch.setattr(github_api.time, "time", lambda: 1_000_000)

    rate_limited = _http_error(
        403,
        {"message": "rate limit exceeded"},
        headers={
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(1_000_010),
        },
    )
    _patch_urlopen(monkeypatch, [rate_limited, FakeResponse(_ok_payload())])

    meta = get_repo_metadata("octocat", "hello")
    assert meta.description == "A cool plugin"
    assert sleeps == [10]


def test_rate_limit_twice_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anonymous(monkeypatch)
    monkeypatch.setattr(github_api.time, "sleep", lambda s: None)
    monkeypatch.setattr(github_api.time, "time", lambda: 1_000_000)

    rate_limited_1 = _http_error(
        429,
        {"message": "too many"},
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1000005"},
    )
    rate_limited_2 = _http_error(
        429,
        {"message": "too many"},
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1000005"},
    )
    _patch_urlopen(monkeypatch, [rate_limited_1, rate_limited_2])

    with pytest.raises(GitHubAPIError) as exc_info:
        get_repo_metadata("octocat", "hello")
    assert "rate limited" in str(exc_info.value).lower()


def test_5xx_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anonymous(monkeypatch)
    sleeps: list[float] = []
    monkeypatch.setattr(github_api.time, "sleep", lambda s: sleeps.append(s))

    err_500 = _http_error(500, {"message": "boom"})
    _patch_urlopen(monkeypatch, [err_500, FakeResponse(_ok_payload())])

    meta = get_repo_metadata("octocat", "hello")
    assert meta.description == "A cool plugin"
    assert sleeps == [1]


def test_authorization_header_added(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        github_api, "resolve_token", lambda: ("ghp_secret", "GITHUB_TOKEN")
    )
    captured = _patch_urlopen(monkeypatch, [FakeResponse(_ok_payload())])

    get_repo_metadata("octocat", "hello")
    assert len(captured) == 1
    req = captured[0]
    # urllib.request.Request lowercases header names; use get_header.
    assert req.get_header("Authorization") == "Bearer ghp_secret"
    assert req.get_header("User-agent") == "agora/0.1"
    assert req.get_header("Accept") == "application/vnd.github+json"
    assert req.get_header("X-github-api-version") == "2022-11-28"

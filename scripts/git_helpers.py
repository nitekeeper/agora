# scripts/git_helpers.py
"""Shared git operations for agora plugin registration, updates, and checks.

All functions are thin wrappers over `git` subprocess calls. The `git` binary
must be on PATH. Network errors and non-zero exits surface as GitError.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_DEFAULT_TIMEOUT = 30
_GITHUB_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)
_LS_REMOTE_LINE = re.compile(r"^(?P<sha>[0-9a-f]{40})\s+refs/tags/(?P<tag>.+)$")


class GitError(Exception):
    pass


def parse_github_url(url: str) -> tuple[str, str]:
    """Parse a GitHub clone URL into (owner, repo). Repo has any trailing
    '.git' stripped. Raises GitError on malformed input."""
    m = _GITHUB_URL_RE.match(url.strip())
    if not m:
        raise GitError(f"not a GitHub HTTPS clone URL: {url}")
    return m.group("owner"), m.group("repo")


def plugin_name_from_url(url: str) -> str:
    """Derive the agora plugin name from a GitHub URL — uses bare repo name
    (lowercase, .git stripped). Note: this means two plugins from different
    owners but the same repo name would collide; the agora marketplace is
    currently single-owner so this is acceptable."""
    _, repo = parse_github_url(url)
    return repo.lower()


def _run(cmd: list[str], timeout: int = _DEFAULT_TIMEOUT) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as e:
        raise GitError("git is not installed or not on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise GitError(f"git command timed out: {' '.join(cmd)}") from e


def ls_remote_tags(url: str, timeout: int = _DEFAULT_TIMEOUT) -> dict[str, str]:
    """Run `git ls-remote --tags <url>`. Returns {tag_name: sha}.

    Annotated tags are peeled — when both `refs/tags/v1.0.0` and
    `refs/tags/v1.0.0^{}` are present, the peeled-commit SHA wins. This
    matches what `current_sha` in plugins.json must point at.
    """
    result = _run(["git", "ls-remote", "--tags", url], timeout=timeout)
    if result.returncode != 0:
        raise GitError(
            f"git ls-remote failed for {url}: {result.stderr.strip() or 'unknown error'}"
        )
    tags: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in result.stdout.splitlines():
        m = _LS_REMOTE_LINE.match(line.strip())
        if not m:
            continue
        sha, tag = m.group("sha"), m.group("tag")
        if tag.endswith("^{}"):
            peeled[tag[:-3]] = sha
        else:
            tags.setdefault(tag, sha)
    tags.update(peeled)
    return tags


def get_local_remote_url(repo_dir: Path | str | None = None) -> str | None:
    """Run `git remote get-url origin` from repo_dir (or cwd). Returns None
    if the directory is not a git repo or has no origin."""
    cwd = str(repo_dir) if repo_dir else None
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT,
            check=False,
            cwd=cwd,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def shallow_clone(url: str, tag: str, target_dir: Path | str,
                  timeout: int = 120) -> Path:
    """git clone --depth 1 --branch <tag> <url> <target>.
    Returns the target path. Raises GitError on failure."""
    target = Path(target_dir)
    result = _run(
        ["git", "clone", "--depth", "1", "--branch", tag, url, str(target)],
        timeout=timeout,
    )
    if result.returncode != 0:
        raise GitError(
            f"git clone failed for {url}@{tag}: "
            f"{result.stderr.strip() or 'unknown error'}"
        )
    return target

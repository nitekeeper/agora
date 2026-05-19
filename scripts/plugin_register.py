# scripts/plugin_register.py
"""Register or refresh a plugin entry in plugins.json.

Derives every required field from the plugin's GitHub repo:
 - URL (CLI arg or auto-detected from cwd's git origin)
 - latest stable tag (via `git ls-remote --tags`)
 - SPDX license (from a LICENSE file in a shallow clone, with GH API fallback)
 - description, topics, homepage (via the GitHub REST API)

Then writes plugins.json + recompiled marketplace.json atomically via
scripts.registry.save_registry.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import git_helpers, github_api, license_parser, registry, semver
from scripts.git_helpers import GitError
from scripts.github_api import GitHubAPIError

_ALLOWED_CATEGORIES = (
    "development",
    "productivity",
    "engineering",
    "design",
    "data",
    "product-management",
    "figma",
    "other",
)

TOPIC_TO_CATEGORY = {
    "developer-tools": "development",
    "devtools": "development",
    "claude-code": "development",
    "cli": "development",
    "workflow": "productivity",
    "productivity": "productivity",
    "task-management": "productivity",
    "engineering": "engineering",
    "architecture": "engineering",
    "design-tools": "design",
    "design-system": "design",
    "ui": "design",
    "data": "data",
    "analytics": "data",
    "data-science": "data",
    "product-management": "product-management",
    "pm": "product-management",
    "figma": "figma",
}

_LICENSE_FILENAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
_DESCRIPTION_MAX = 280
_KEYWORDS_MAX = 16


class RegisterError(Exception):
    """Fatal registration error suitable to surface to the user."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_repo_url(url: str) -> str:
    """Strip trailing slash and ensure a trailing .git for schema compliance."""
    cleaned = url.strip().rstrip("/")
    if not cleaned.endswith(".git"):
        cleaned = cleaned + ".git"
    return cleaned


def _detect_license_locally(clone_root: Path) -> str | None:
    for name in _LICENSE_FILENAMES:
        path = clone_root / name
        if path.exists() and path.is_file():
            spdx = license_parser.detect_spdx_from_file(path)
            if spdx:
                return spdx
    return None


def _resolve_license(clone_root: Path, owner: str, repo: str) -> str | None:
    local = _detect_license_locally(clone_root)
    if local:
        return local
    try:
        meta = github_api.get_repo_metadata(owner, repo)
    except GitHubAPIError:
        return None
    spdx = meta.license_spdx_id
    if not spdx or spdx == "NOASSERTION":
        return None
    return spdx


def _resolve_category(topics: list[str], override: str | None) -> str | None:
    if override is not None:
        if override not in _ALLOWED_CATEGORIES:
            raise RegisterError(
                f"invalid --category '{override}'; must be one of: "
                + ", ".join(_ALLOWED_CATEGORIES)
            )
        return override
    for topic in topics:
        mapped = TOPIC_TO_CATEGORY.get(topic)
        if mapped:
            return mapped
    return None


def _resolve_keywords(topics: list[str], category_topic: str | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in topics:
        if not raw:
            continue
        kw = raw.lower()
        if category_topic and kw == category_topic.lower():
            continue
        if kw in seen:
            continue
        seen.add(kw)
        out.append(kw)
        if len(out) >= _KEYWORDS_MAX:
            break
    return out


def _category_topic(
    topics: list[str], override: str | None, chosen_category: str | None
) -> str | None:
    """Return the topic that was used to derive the category (so it can be
    stripped from keywords). None when --category override was used or no
    topic mapped."""
    if override is not None:
        return None
    if chosen_category is None:
        return None
    for topic in topics:
        if TOPIC_TO_CATEGORY.get(topic) == chosen_category:
            return topic
    return None


def _resolve_description(
    meta_description: str | None, override: str | None, owner: str, repo: str
) -> str:
    desc = override.strip() if override is not None else (meta_description or "").strip()
    if not desc:
        raise RegisterError(
            f"GitHub repo description is empty - set it at "
            f"https://github.com/{owner}/{repo}/edit or pass --description '...'"
        )
    if len(desc) > _DESCRIPTION_MAX:
        print(
            f"warning: description exceeds {_DESCRIPTION_MAX} chars; truncating",
            file=sys.stderr,
        )
        desc = desc[:_DESCRIPTION_MAX]
    return desc


def _build_entry(
    *,
    plugin_name: str,
    repository_url: str,
    chosen_tag: str,
    current_sha: str,
    description: str,
    license_id: str,
    category: str | None,
    keywords: list[str],
    owner: str,
    homepage: str,
    existing: dict | None,
) -> dict:
    entry: dict = {
        "name": plugin_name,
        "repository_url": repository_url,
        "current_version": chosen_tag,
        "current_sha": current_sha,
        "description": description,
        "license": license_id,
    }
    if category:
        entry["category"] = category
    if keywords:
        entry["keywords"] = keywords
    entry["author"] = {"name": owner}
    entry["homepage"] = homepage

    now = _now_iso()
    if existing and existing.get("registered_at"):
        entry["registered_at"] = existing["registered_at"]
    else:
        entry["registered_at"] = now
    entry["updated_at"] = now
    return entry


def register(
    url: str | None,
    *,
    include_prerelease: bool = False,
    description_override: str | None = None,
    category_override: str | None = None,
    plugins_path: Path | None = None,
    marketplace_path: Path | None = None,
) -> dict:
    """Register or refresh a plugin entry. Returns the entry written.

    Raises RegisterError on user-facing failure conditions.
    """
    # 1. URL resolution
    if url is None:
        url = git_helpers.get_local_remote_url()
        if not url:
            raise RegisterError(
                "could not detect repository URL - pass --url or cd into the plugin repo"
            )

    # 2. Parse URL
    owner, repo = git_helpers.parse_github_url(url)

    # 3. Plugin name
    plugin_name = git_helpers.plugin_name_from_url(url)

    # Normalize for storage (schema requires .git suffix).
    repository_url = _normalize_repo_url(url)

    # 4. Pick the latest tag
    tags = git_helpers.ls_remote_tags(url)
    if not tags:
        raise RegisterError(
            "plugin has no release tags; tag a release (e.g. 'git tag v1.0.0 && git push --tags')"
        )
    chosen_tag = semver.pick_latest(list(tags.keys()), include_prerelease=include_prerelease)
    if chosen_tag is None:
        raise RegisterError(
            "no stable release tag found; add a stable tag or use --include-prerelease"
        )
    current_sha = tags[chosen_tag]

    # 5. Shallow clone + 6. license + 7. GH meta
    with tempfile.TemporaryDirectory() as tmp:
        clone_target = Path(tmp) / "repo"
        try:
            git_helpers.shallow_clone(url, chosen_tag, clone_target)
        except GitError as e:
            raise RegisterError(f"clone failed: {e}") from e

        license_id = _resolve_license(clone_target, owner, repo)

    if not license_id:
        raise RegisterError(
            "could not determine license - add a LICENSE file with a "
            "recognized SPDX identifier (MIT, Apache-2.0, BSD-3-Clause, "
            "etc.) and re-tag"
        )

    try:
        meta = github_api.get_repo_metadata(owner, repo)
    except GitHubAPIError as e:
        raise RegisterError(f"GitHub API request failed: {e}") from e

    # 8. Description
    description = _resolve_description(meta.description, description_override, owner, repo)

    # 9. Category (validates override)
    topics = list(meta.topics or [])
    category = _resolve_category(topics, category_override)

    # 10. Keywords (minus the topic used to derive the category)
    cat_topic = _category_topic(topics, category_override, category)
    keywords = _resolve_keywords(topics, cat_topic)

    # 12. Homepage
    homepage = (meta.homepage or "").strip()
    if not homepage:
        homepage = f"https://github.com/{owner}/{repo}"

    # 14. Update plugins.json
    if plugins_path is None:
        data = registry.load_registry()
    else:
        data = registry.load_registry(plugins_path)
    found = registry.find_plugin(data, plugin_name)
    existing = found[1] if found else None

    entry = _build_entry(
        plugin_name=plugin_name,
        repository_url=repository_url,
        chosen_tag=chosen_tag,
        current_sha=current_sha,
        description=description,
        license_id=license_id,
        category=category,
        keywords=keywords,
        owner=owner,
        homepage=homepage,
        existing=existing,
    )

    if found:
        data["plugins"][found[0]] = entry
    else:
        data["plugins"].append(entry)

    save_kwargs: dict = {}
    if plugins_path is not None:
        save_kwargs["plugins_path"] = plugins_path
    if marketplace_path is not None:
        save_kwargs["marketplace_path"] = marketplace_path
    registry.save_registry(data, **save_kwargs)

    return entry


def _print_success(entry: dict) -> None:
    name = entry["name"]
    version = entry["current_version"]
    sha = entry["current_sha"]
    short_sha = sha[:7]
    print(f"Registered {name} {version} (sha {short_sha}...)")
    print()
    print("Next:")
    print("  cd <agora-repo>")
    print(f"  git checkout -b register-{name}")
    print("  git add plugins.json")
    print(f'  git commit -m "Register {name} {version}"')
    print(f"  git push -u origin register-{name}")
    print("  gh pr create")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="agora-plugin-register",
        description="Register or refresh a plugin entry in agora's plugins.json",
    )
    p.add_argument("--url", help="GitHub HTTPS clone URL of the plugin repo")
    p.add_argument(
        "--include-prerelease",
        action="store_true",
        help="Allow pre-release tags (-rc, -beta, ...) when picking the latest",
    )
    p.add_argument(
        "--description",
        dest="description",
        help="Override the GitHub repo description for the registry entry",
    )
    p.add_argument(
        "--category",
        choices=_ALLOWED_CATEGORIES,
        help="Override the auto-derived category",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        entry = register(
            url=args.url,
            include_prerelease=args.include_prerelease,
            description_override=args.description,
            category_override=args.category,
        )
    except RegisterError as e:
        print(f"register failed: {e}", file=sys.stderr)
        return 1
    except GitError as e:
        print(f"register failed: {e}", file=sys.stderr)
        return 1
    _print_success(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# scripts/paths.py
"""Canonical repo-relative and user-home paths used by every agora script."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_JSON = REPO_ROOT / "plugins.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
SCHEMA_JSON = REPO_ROOT / "docs" / "plugins.schema.json"
DOCS_DIR = REPO_ROOT / "docs"
SKILLS_DIR = REPO_ROOT / "skills"
HOOKS_DIR = REPO_ROOT / "hooks"

CACHE_DIR = Path.home() / ".agora"
CHECK_CACHE_JSON = CACHE_DIR / "check-cache.json"

CLAUDE_SETTINGS_JSON = Path.home() / ".claude" / "settings.json"

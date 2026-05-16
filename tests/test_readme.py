from pathlib import Path


def test_readme_exists():
    assert Path("README.md").exists()


def test_readme_describes_marketplace_role():
    """Agora's purpose — registry over Claude Code's native marketplace — must
    be visible in the README."""
    content = Path("README.md").read_text(encoding="utf-8").lower()
    assert "marketplace" in content
    assert "plugins.json" in content
    assert "marketplace.json" in content


def test_readme_has_three_audience_install_sections():
    """Each audience should be able to find their install path without
    reading the other two."""
    content = Path("README.md").read_text(encoding="utf-8").lower()
    assert "for consumers" in content
    assert "for plugin authors" in content
    assert "for agora contributors" in content


def test_readme_discloses_claude_code_origin():
    """Set expectations: most code in this repo is developed with AI assistance.
    Readers reviewing PRs should know."""
    content = Path("README.md").read_text(encoding="utf-8")
    assert "Claude Code" in content

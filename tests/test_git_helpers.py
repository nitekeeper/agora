# tests/test_git_helpers.py
import subprocess

import pytest

from scripts import git_helpers as gh


class TestParseUrl:
    def test_basic(self):
        assert gh.parse_github_url("https://github.com/nitekeeper/atelier.git") == (
            "nitekeeper",
            "atelier",
        )

    def test_no_git_suffix(self):
        assert gh.parse_github_url("https://github.com/nitekeeper/atelier") == (
            "nitekeeper",
            "atelier",
        )

    def test_trailing_slash(self):
        assert gh.parse_github_url("https://github.com/nitekeeper/atelier/") == (
            "nitekeeper",
            "atelier",
        )

    def test_invalid(self):
        for bad in ["", "http://github.com/x/y.git", "https://gitlab.com/x/y.git", "garbage"]:
            with pytest.raises(gh.GitError):
                gh.parse_github_url(bad)


def test_plugin_name_lowercase():
    assert gh.plugin_name_from_url("https://github.com/Nitekeeper/Atelier.git") == "atelier"


class TestLsRemoteTags:
    def _mock_result(self, stdout: str, returncode: int = 0):
        return subprocess.CompletedProcess(
            args=["git"], returncode=returncode, stdout=stdout, stderr=""
        )

    def test_lightweight_tags(self, monkeypatch):
        stdout = (
            "abc1230000000000000000000000000000000000\trefs/tags/v1.0.0\n"
            "def4560000000000000000000000000000000000\trefs/tags/v1.1.0\n"
        )
        monkeypatch.setattr(gh, "_run", lambda *a, **kw: self._mock_result(stdout))
        assert gh.ls_remote_tags("url") == {
            "v1.0.0": "abc1230000000000000000000000000000000000",
            "v1.1.0": "def4560000000000000000000000000000000000",
        }

    def test_annotated_tag_peeling(self, monkeypatch):
        stdout = (
            "1111111111111111111111111111111111111111\trefs/tags/v1.0.0\n"
            "2222222222222222222222222222222222222222\trefs/tags/v1.0.0^{}\n"
        )
        monkeypatch.setattr(gh, "_run", lambda *a, **kw: self._mock_result(stdout))
        assert gh.ls_remote_tags("url") == {"v1.0.0": "2" * 40}

    def test_failure(self, monkeypatch):
        monkeypatch.setattr(gh, "_run", lambda *a, **kw: self._mock_result("", returncode=128))
        with pytest.raises(gh.GitError):
            gh.ls_remote_tags("url")


class TestLocalRemote:
    def test_returns_url(self, monkeypatch):
        def fake_run(*a, **kw):
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="https://x/y.git\n", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert gh.get_local_remote_url() == "https://x/y.git"

    def test_no_origin(self, monkeypatch):
        def fake_run(*a, **kw):
            return subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="error")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert gh.get_local_remote_url() is None

    def test_git_not_found(self, monkeypatch):
        def fake_run(*a, **kw):
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert gh.get_local_remote_url() is None


def test_shallow_clone_failure(monkeypatch, tmp_path):
    def fake(*a, **kw):
        return subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="not found")

    monkeypatch.setattr(gh, "_run", fake)
    with pytest.raises(gh.GitError):
        gh.shallow_clone("url", "v1.0.0", tmp_path / "dest")

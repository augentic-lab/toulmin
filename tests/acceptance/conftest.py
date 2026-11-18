"""Isolation and service fixtures only for the WO contract acceptance directory."""

from types import SimpleNamespace

import pytest

from tests.acceptance.wo_support import FakeNative, repository


@pytest.fixture
def wo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)
    monkeypatch.delenv("TOULMIN_ROOT", raising=False)
    monkeypatch.delenv("TOULMIN_CONFIG", raising=False)
    source = repository(tmp_path / "code")
    return SimpleNamespace(root=tmp_path / "records", source=source, tmp=tmp_path)


@pytest.fixture
def native(monkeypatch):
    fake = FakeNative()
    monkeypatch.setattr("toulmin.application.aoe.AoEClient", lambda *a, **kw: fake)
    monkeypatch.setattr("toulmin.cli.aoe.AoEClient", lambda *a, **kw: fake)
    return fake

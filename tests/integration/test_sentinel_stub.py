"""Sentinel module availability tests (Linux / no-assets path)."""

from __future__ import annotations

import importlib
import sys


def test_sentinel_stub_raises_import_error_when_root_absent(monkeypatch):
    """Importing data_engine.sentinel fails clearly without a valid asset root."""
    monkeypatch.delenv("DATA_ENGINE_SENTINEL_ROOT", raising=False)
    # Ensure the module is not cached from a previous test.
    for name in (
        "data_engine.sentinel",
        "data_engine.sentinel.pipeline",
        "data_engine.sentinel.config",
    ):
        sys.modules.pop(name, None)

    monkeypatch.setenv("DATA_ENGINE_SENTINEL_ROOT", "/definitely/not/a/sentinel/root")
    try:
        importlib.import_module("data_engine.sentinel")
    except ImportError as exc:
        assert "data_engine.sentinel is not available" in str(exc)
        assert "DATA_ENGINE_SENTINEL_ROOT" in str(exc)
    else:
        raise AssertionError("ImportError was not raised for an invalid sentinel root")
    finally:
        for name in (
            "data_engine.sentinel",
            "data_engine.sentinel.pipeline",
            "data_engine.sentinel.config",
        ):
            sys.modules.pop(name, None)

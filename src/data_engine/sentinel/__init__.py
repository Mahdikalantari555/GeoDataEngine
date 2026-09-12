"""Sentinel-2 processing domain."""

from __future__ import annotations


def _raise_sentinel_unavailable() -> None:
    raise ImportError(
        "data_engine.sentinel is not available. "
        "The sentinel source directory cannot be reached. "
        "Set DATA_ENGINE_SENTINEL_ROOT to a valid Sentinel asset path."
    )


# Sentinel module contents will be populated when assets are available.
# Current state: stub placeholder until Windows-only source is copied.
__all__: list[str] = []

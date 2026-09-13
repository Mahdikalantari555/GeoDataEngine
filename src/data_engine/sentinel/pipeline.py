"""Sentinel-2 processing pipeline — stub for Linux environments."""

from __future__ import annotations


class SentinelPipeline:
    """End-to-end Sentinel-2 processing pipeline (stub).

    Raises NotImplementedError when run on platforms without valid
    DATA_ENGINE_SENTINEL_ROOT assets.
    """

    def __init__(self, scene_dir: str) -> None:
        self.scene_dir = scene_dir

    def run(self) -> dict:
        raise NotImplementedError(
            "SentinelPipeline requires DATA_ENGINE_SENTINEL_ROOT to point "
            "to a valid Sentinel asset directory."
        )


class SentinelFetcher:
    """High-level Sentinel-2 STAC downloader (stub).

    Raises NotImplementedError when run on platforms without valid
    DATA_ENGINE_SENTINEL_ROOT assets.
    """

    def __init__(self, collection: str = "sentinel-2-l2a") -> None:
        self.collection = collection

    def fetch(self, scene_id: str) -> dict:
        raise NotImplementedError(
            "SentinelFetcher requires DATA_ENGINE_SENTINEL_ROOT to point "
            "to a valid Sentinel asset directory."
        )

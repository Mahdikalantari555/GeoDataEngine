"""Tests for ``app.core.config`` — session persistence and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.config import (
    BASIC_INDICES,
    DEFAULT_MIRROR_URL,
    PRESET_NAMES,
    SATELLITES,
    SENTINEL_ONLY_INDICES,
    AppConfig,
    ConfigStore,
    app_dir,
    default_output_dir,
    venv_python,
)


class TestAppConfigDefaults:
    def test_defaults_are_sane(self):
        cfg = AppConfig()
        assert cfg.satellite in SATELLITES
        assert cfg.sort_by in ("date", "cloud_cover")
        assert cfg.mode == "lite"
        assert cfg.preset in PRESET_NAMES
        assert cfg.mirror_url == DEFAULT_MIRROR_URL
        assert 0.0 <= cfg.min_coverage_ratio <= 1.0
        assert cfg.selected_indices  # something pre-ticked
        assert set(cfg.selected_indices) <= set(BASIC_INDICES)

    def test_sentinel_only_index_not_preselected(self):
        # OPTRAM must never be pre-ticked, it is Sentinel-2 only.
        assert not set(AppConfig().selected_indices) & set(SENTINEL_ONLY_INDICES)

    def test_default_output_dir_is_next_to_app(self):
        assert default_output_dir().parent == app_dir()


class TestNormalization:
    def test_out_of_range_values_are_clamped(self):
        cfg = AppConfig(cloud_threshold=250, min_coverage_ratio=-3).normalized()
        assert cfg.cloud_threshold == 100.0
        assert cfg.min_coverage_ratio == 0.0

    def test_invalid_strings_fall_back_to_defaults(self):
        cfg = AppConfig(cloud_threshold="abc", min_coverage_ratio="x").normalized()
        assert cfg.cloud_threshold == 20.0
        assert cfg.min_coverage_ratio == 0.55

    def test_unknown_satellite_and_sort_fall_back(self):
        cfg = AppConfig(satellite="mars-orbiter", sort_by="price").normalized()
        assert cfg.satellite == "landsat-8"
        assert cfg.sort_by == "date"

    def test_unknown_indices_are_dropped(self):
        cfg = AppConfig(selected_indices=["ndvi", "BOGUS"]).normalized()
        assert cfg.selected_indices == ["NDVI"]

    def test_unknown_preset_falls_back(self):
        assert AppConfig(preset="everything").normalized().preset == "minimal"

    def test_unknown_mode_falls_back_to_lite(self):
        assert AppConfig(mode="turbo").normalized().mode == "lite"

    def test_normalized_returns_copy(self):
        original = AppConfig(cloud_threshold=500)
        copy = original.normalized()
        assert original.cloud_threshold == 500
        assert copy.cloud_threshold == 100.0


class TestSerialization:
    def test_round_trip_preserves_known_fields(self):
        cfg = AppConfig(
            roi_path="/data/roi.geojson",
            start_date="2024-01-01",
            end_date="2024-12-31",
            output_dir="/data/out",
            cloud_threshold=15.0,
            min_coverage_ratio=0.75,
            satellite="sentinel-2",
            sort_by="cloud_cover",
            crs_override="EPSG:32639",
            selected_indices=["NDVI", "OPTRAM"],
            preset="standard",
            mode="full",
        )
        restored = AppConfig.from_dict(cfg.to_dict())
        for field in (
            "roi_path",
            "start_date",
            "end_date",
            "output_dir",
            "cloud_threshold",
            "min_coverage_ratio",
            "satellite",
            "sort_by",
            "crs_override",
            "preset",
            "mode",
        ):
            assert getattr(restored, field) == getattr(cfg, field)
        assert restored.selected_indices == ["NDVI", "OPTRAM"]

    def test_unknown_keys_are_preserved(self):
        payload = {"cloud_threshold": 12.0, "future_setting": {"nested": True}}
        cfg = AppConfig.from_dict(payload)
        assert cfg.extra == {"future_setting": {"nested": True}}
        assert cfg.to_dict()["future_setting"] == {"nested": True}

    def test_from_dict_handles_none(self):
        assert AppConfig.from_dict(None).satellite == "landsat-8"

    def test_date_range_and_directories(self):
        cfg = AppConfig(start_date="2024-01-01", end_date="2024-02-01", output_dir="/tmp/o")
        assert cfg.date_range() == ("2024-01-01", "2024-02-01")
        assert cfg.scenes_dir == Path("/tmp/o/scenes")
        assert cfg.products_dir == Path("/tmp/o/products")


class TestConfigStore:
    def test_load_returns_defaults_when_missing(self, tmp_path):
        store = ConfigStore(tmp_path / "nested" / "appdir")
        cfg = store.load()
        assert isinstance(cfg, AppConfig)
        assert cfg.satellite == "landsat-8"
        assert not store.path.exists()

    def test_save_then_load_round_trip(self, tmp_path):
        store = ConfigStore(tmp_path / "appdir")
        cfg = AppConfig(roi_path="/r.geojson", cloud_threshold=33.0, selected_indices=["NDWI"])
        path = store.save(cfg)
        assert path.exists()
        assert path.name == "config.json"
        restored = store.load()
        assert restored.roi_path == "/r.geojson"
        assert restored.cloud_threshold == 33.0
        assert restored.selected_indices == ["NDWI"]

    def test_save_is_atomic_no_tmp_left_behind(self, tmp_path):
        store = ConfigStore(tmp_path / "appdir")
        store.save(AppConfig())
        assert not list(store.directory.glob("*.tmp"))

    def test_corrupt_json_falls_back_to_defaults(self, tmp_path):
        store = ConfigStore(tmp_path / "appdir")
        store.directory.mkdir(parents=True)
        store.path.write_text("{not json", encoding="utf-8")
        assert store.load().satellite == "landsat-8"

    def test_non_object_json_falls_back_to_defaults(self, tmp_path):
        store = ConfigStore(tmp_path / "appdir")
        store.directory.mkdir(parents=True)
        store.path.write_text("[1, 2, 3]", encoding="utf-8")
        assert store.load().mode == "lite"

    def test_saved_values_are_normalized_on_load(self, tmp_path):
        store = ConfigStore(tmp_path / "appdir")
        store.directory.mkdir(parents=True)
        store.path.write_text(json.dumps({"cloud_threshold": 900}), encoding="utf-8")
        assert store.load().cloud_threshold == 100.0

    def test_venv_dir_is_beside_config(self, tmp_path):
        store = ConfigStore(tmp_path / "appdir")
        assert store.venv_dir() == tmp_path / "appdir" / ".venv"

    def test_restore_across_instances(self, tmp_path):
        """Settings survive an app restart (new store instance)."""
        directory = tmp_path / "appdir"
        first = ConfigStore(directory)
        cfg = first.load()
        cfg.output_dir = "/data/output"
        cfg.cloud_threshold = 11.5
        first.save(cfg)

        second = ConfigStore(directory)
        assert second.load().output_dir == "/data/output"
        assert second.load().cloud_threshold == 11.5


class TestVenvPython:
    def test_posix_layout(self):
        assert venv_python(Path("/app/.venv")).as_posix().endswith("/.venv/bin/python")

    def test_windows_layout(self, monkeypatch):
        import app.core.config as config_module

        monkeypatch.setattr(config_module, "_is_windows", lambda: True)
        assert venv_python(Path("C:/app/.venv")).name == "python.exe"
        assert venv_python(Path("C:/app/.venv")).parent.name == "Scripts"


@pytest.mark.parametrize("name", ["landsat-8", "landsat-9", "sentinel-2"])
def test_satellite_constants_match_config(name):
    assert name in SATELLITES

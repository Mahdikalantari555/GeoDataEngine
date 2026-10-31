"""Tests for ``app.core.layout`` — output folder contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.layout import (
    build_product_metadata,
    ensure_layout,
    ensure_product_dirs,
    list_products,
    list_scene_dirs,
    product_dir,
    product_metadata_dir,
    product_raster_path,
    sanitize_scene_id,
    scenes_dir,
    utc_timestamp,
    write_json_atomic,
    write_product_metadata,
)


class TestPaths:
    def test_scenes_and_products_folders(self, tmp_path):
        assert scenes_dir(tmp_path) == tmp_path / "scenes"
        assert product_dir(tmp_path, "ndvi") == tmp_path / "products" / "ndvi"
        assert product_metadata_dir(tmp_path, "ndvi") == tmp_path / "products" / "ndvi" / "metadata"
        assert product_metadata_dir(tmp_path, "ETaDaily") == (
            tmp_path / "products" / "ETaDaily" / "metadata"
        )

    def test_ensure_layout_creates_both_folders(self, tmp_path):
        created = ensure_layout(tmp_path / "out")
        assert created["scenes"].is_dir()
        assert created["products"].is_dir()

    def test_ensure_layout_is_idempotent(self, tmp_path):
        ensure_layout(tmp_path)
        ensure_layout(tmp_path)
        assert (tmp_path / "scenes").is_dir()

    def test_ensure_product_dirs(self, tmp_path):
        folders = ensure_product_dirs(tmp_path, "optram")
        assert folders["raster"].name == "optram"
        assert folders["metadata"].name == "metadata"
        assert folders["metadata"].is_dir()

    def test_raster_path_uses_scene_id(self, tmp_path):
        path = product_raster_path(tmp_path, "ndvi", "LC08_20240601")
        assert path == tmp_path / "products" / "ndvi" / "LC08_20240601.tif"
        assert path.parent.is_dir()

    def test_raster_path_can_be_disambiguated(self, tmp_path):
        path = product_raster_path(tmp_path, "ndvi", "LC08", multi_scene=True)
        assert path.name == "LC08_ndvi.tif"

    def test_unsafe_scene_ids_are_sanitized(self, tmp_path):
        path = product_raster_path(tmp_path, "ndvi", "S2B/MSIL2A:2024*06")
        assert "/" not in path.name and ":" not in path.name
        assert path.name.startswith("S2B_MSIL2A")


class TestSanitize:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("LC08_L2SP_166038_20240601", "LC08_L2SP_166038_20240601"),
            ("S2B/MSIL2A:20240601", "S2B_MSIL2A_20240601"),
            ("scene with spaces", "scene_with_spaces"),
            ("...", "scene"),
            ("", "scene"),
        ],
    )
    def test_sanitize(self, raw, expected):
        assert sanitize_scene_id(raw) == expected

    def test_windows_reserved_characters_are_stripped(self):
        assert sanitize_scene_id('a<b>c:d"e|f?g*h') == "a_b_c_d_e_f_g_h"


class TestMetadata:
    def test_build_product_metadata(self):
        metadata = build_product_metadata(
            product="ndvi",
            scene_id="SCENE",
            scene_date="2024-06-01",
            source_bands=["nir08", "red"],
            crs="EPSG:32639",
            transform=(30.0, 0.0, 210000.0, 0.0, -30.0, 3430000.0),
            width=16,
            height=16,
            params={"light_coeff": 0.5},
            extra={"statistics": {"min": 0.1}},
        )
        assert metadata["product"] == "ndvi"
        assert metadata["source_bands"] == ["nir08", "red"]
        assert metadata["crs"] == "EPSG:32639"
        assert len(metadata["transform"]) == 6
        assert metadata["parameters"] == {"light_coeff": 0.5}
        assert metadata["statistics"] == {"min": 0.1}
        assert metadata["created_utc"]

    def test_write_metadata_goes_to_metadata_subfolder(self, tmp_path):
        path = write_product_metadata(
            tmp_path, "evi", "SCENE", {"product": "evi", "scene_id": "SCENE"}
        )
        assert path.parent == tmp_path / "products" / "evi" / "metadata"
        assert json.loads(path.read_text())["scene_id"] == "SCENE"

    def test_write_json_atomic_leaves_no_tmp(self, tmp_path):
        target = tmp_path / "x" / "file.json"
        write_json_atomic(target, {"a": 1})
        assert target.exists()
        assert not list(target.parent.glob("*.tmp"))

    def test_timestamp_is_iso_utc(self):
        stamp = utc_timestamp()
        assert stamp.endswith("+00:00")
        assert "T" in stamp


class TestDiscovery:
    def test_list_scene_dirs_requires_mtl(self, tmp_path, landsat_scene):
        ensure_layout(tmp_path)
        target = scenes_dir(tmp_path) / landsat_scene.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.mkdir()
            for path in landsat_scene.glob("*"):
                (target / path.name).write_bytes(path.read_bytes())
        (scenes_dir(tmp_path) / "not_a_scene").mkdir()
        found = list_scene_dirs(tmp_path)
        assert [path.name for path in found] == [target.name]

    def test_list_products_groups_by_folder(self, tmp_path):
        ensure_product_dirs(tmp_path, "ndvi")
        ensure_product_dirs(tmp_path, "evi")
        (tmp_path / "products" / "ndvi" / "A.tif").write_bytes(b"x")
        (tmp_path / "products" / "evi" / "B.tif").write_bytes(b"x")
        ensure_product_dirs(tmp_path, "empty")
        products = list_products(tmp_path)
        assert set(products) == {"ndvi", "evi"}

    def test_list_products_on_missing_root(self, tmp_path):
        assert list_products(tmp_path / "nope") == {}
        assert list_scene_dirs(tmp_path / "nope") == []


def test_metadata_and_raster_share_scene_id(tmp_path):
    metadata_path = write_product_metadata(tmp_path, "savi", "SC/ENE", {"product": "savi"})
    raster_path = product_raster_path(tmp_path, "savi", "SC/ENE")
    assert metadata_path.stem == raster_path.stem == "SC_ENE"


def test_paths_accept_strings(tmp_path):
    assert product_dir(str(tmp_path), "ndvi") == Path(tmp_path) / "products" / "ndvi"

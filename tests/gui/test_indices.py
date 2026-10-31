"""Tests for ``app.core.indices`` — light-stack index generation."""

from __future__ import annotations

import json

import numpy as np
import pytest
from app.core.indices import (
    GeneratedProduct,
    SceneIndexError,
    SceneInfo,
    UnsupportedIndexError,
    available_indices,
    compute_index,
    discover_bands,
    generate_index,
    generate_indices,
    list_scenes,
    missing_bands,
    optram,
    scene_from_directory,
    validate_index,
)

from tests.gui.conftest import SENTINEL_BANDS, write_scene


class TestAvailability:
    def test_landsat_supports_everything_but_optram(self):
        assert available_indices("landsat-8") == ["NDVI", "EVI", "SAVI", "NDWI"]
        assert available_indices("landsat-9") == ["NDVI", "EVI", "SAVI", "NDWI"]

    def test_sentinel_supports_optram(self):
        assert "OPTRAM" in available_indices("sentinel-2")

    def test_validate_index_normalizes_case(self):
        assert validate_index("ndvi", "landsat-8") == "NDVI"

    def test_validate_index_rejects_unknown(self):
        with pytest.raises(UnsupportedIndexError, match="Unknown index"):
            validate_index("NDII", "landsat-8")

    def test_optram_rejected_for_landsat(self):
        with pytest.raises(UnsupportedIndexError, match="only available for Sentinel-2"):
            validate_index("OPTRAM", "landsat-8")

    def test_missing_bands(self):
        assert missing_bands("EVI", {"nir08": None, "red": None}) == ["blue"]
        assert missing_bands("NDVI", {"nir08": None, "red": None}) == []


class TestOptram:
    def test_matches_engine_formula(self):
        red = np.array([[0.2, 0.3], [0.1, 0.4]])
        nir = np.array([[0.6, 0.7], [0.5, 0.8]])
        result = optram(red, nir)
        expected = np.sqrt(nir / red) * (1.0 - red / nir)
        np.testing.assert_allclose(result, np.clip(expected, 0.0, 1.0))

    def test_nodata_and_zero_crossings_become_nan(self):
        red = np.array([[0.0, np.nan], [0.2, 0.2]])
        nir = np.array([[0.5, 0.5], [0.0, np.nan]])
        result = optram(red, nir)
        assert np.isnan(result[0, 0])
        assert np.isnan(result[0, 1])
        assert np.isnan(result[1, 0])
        assert np.isnan(result[1, 1])

    def test_output_is_clipped_to_unit_interval(self):
        red = np.array([[1e-6, 0.9]])
        nir = np.array([[0.9, 1e-6]])
        result = optram(red, nir)
        finite = result[np.isfinite(result)]
        assert np.all(finite >= 0.0) and np.all(finite <= 1.0)

    def test_shape_mismatch_is_rejected(self):
        with pytest.raises(SceneIndexError, match="equal-shaped"):
            optram(np.zeros((2, 2)), np.zeros((2, 3)))

    def test_matches_engine_optram_on_a_datacube(self):
        """Same numbers as data_engine.surface.optram on identical inputs."""
        pytest.importorskip("xarray")
        from data_engine.surface.optram import OPTRAM

        red = np.array([[0.2, 0.25], [0.3, 0.35]])
        nir = np.array([[0.6, 0.65], [0.7, 0.75]])
        expected = OPTRAM().compute(_cube(red, nir)).get("optram").values
        np.testing.assert_allclose(optram(red, nir), expected, rtol=1e-12)

    def test_compute_index_routes_optram(self):
        red = np.full((2, 2), 0.2)
        nir = np.full((2, 2), 0.6)
        result = compute_index("OPTRAM", {"red": red, "nir08": nir})
        np.testing.assert_allclose(result, optram(red, nir))


def _cube(red, nir):
    import xarray as xr

    from data_engine.core.datacube import DataCube

    cube = DataCube()
    cube.add("red", xr.DataArray(red, dims=("y", "x")))
    cube.add("nir08", xr.DataArray(nir, dims=("y", "x")))
    return cube


class TestEngineDelegation:
    """NDVI/EVI/SAVI/NDWI must use the engine implementation, not a copy."""

    def _bands(self):
        return {
            "blue": np.full((4, 4), 0.08),
            "green": np.full((4, 4), 0.12),
            "red": np.full((4, 4), 0.20),
            "nir08": np.full((4, 4), 0.62),
        }

    @pytest.mark.parametrize("name", ["NDVI", "EVI", "SAVI", "NDWI"])
    def test_matches_vendored_spectral_module(self, name):
        from data_engine._vendor.geospatial_core import spectral

        bands = self._bands()
        expected = spectral.compute_spectral_index(
            name,
            {
                "nir": bands["nir08"],
                "red": bands["red"],
                "blue": bands["blue"],
                "green": bands["green"],
            },
        )
        np.testing.assert_allclose(compute_index(name, bands), expected)

    def test_ndvi_value(self):
        result = compute_index("NDVI", self._bands())
        np.testing.assert_allclose(result, (0.62 - 0.20) / (0.62 + 0.20))

    def test_savi_light_coefficient_is_configurable(self):
        bands = self._bands()
        default = compute_index("SAVI", bands)
        custom = compute_index("SAVI", bands, params={"light_coeff": 0.25})
        assert not np.allclose(default, custom)

    def test_missing_band_raises(self):
        with pytest.raises(SceneIndexError, match="requires band"):
            compute_index("EVI", {"nir08": np.zeros((2, 2)), "red": np.zeros((2, 2))})

    def test_unknown_index_raises(self):
        with pytest.raises(UnsupportedIndexError):
            compute_index("NOPE", self._bands())


class TestDiscovery:
    def test_discover_bands(self, landsat_scene):
        bands = discover_bands(landsat_scene)
        expected = {"blue", "green", "red", "nir08", "swir16", "swir22", "lwir11", "qa_pixel"}
        assert set(bands) == expected
        assert bands["red"].name == "red.tif"

    def test_discover_bands_missing_directory(self, tmp_path):
        with pytest.raises(SceneIndexError, match="does not exist"):
            discover_bands(tmp_path / "nope")

    def test_scene_from_directory_reads_mtl(self, sentinel_scene):
        scene = scene_from_directory(sentinel_scene)
        assert scene.scene_id == "S2B_MSIL2A_20240601_T39SXC"
        assert scene.date == "2024-06-01"
        assert scene.satellite == "sentinel-2"
        assert set(scene.bands) == set(SENTINEL_BANDS)

    def test_scene_from_directory_falls_back_to_folder_name(self, tmp_path):
        folder = tmp_path / "unknown_scene"
        write_scene(folder, scene_id="ignored")
        (folder / "MTL.json").unlink()
        scene = scene_from_directory(folder)
        assert scene.scene_id == "unknown_scene"

    def test_scene_from_directory_tolerates_corrupt_mtl(self, landsat_scene):
        (landsat_scene / "MTL.json").write_text("{not json")
        scene = scene_from_directory(landsat_scene)
        assert scene.scene_id == landsat_scene.name

    def test_list_scenes(self, tmp_path, landsat_scene, sentinel_scene):
        root = landsat_scene.parent
        scenes = list_scenes(root)
        assert {scene.name for scene in scenes} == {landsat_scene.name, sentinel_scene.name}

    def test_list_scenes_skips_folders_without_bands(self, tmp_path):
        empty = tmp_path / "empty_scene"
        empty.mkdir()
        assert list_scenes(tmp_path) == []

    def test_list_scenes_missing_root(self, tmp_path):
        assert list_scenes(tmp_path / "nope") == []


class TestGeneration:
    def test_generates_ndvi_raster_and_metadata(self, landsat_scene, tmp_path):
        output = tmp_path / "out"
        scene = scene_from_directory(landsat_scene)
        product = generate_index(scene, "NDVI", output)

        assert isinstance(product, GeneratedProduct)
        assert product.raster_path == output / "products" / "ndvi" / f"{scene.scene_id}.tif"
        assert product.raster_path.exists()
        assert product.metadata_path == (
            output / "products" / "ndvi" / "metadata" / f"{scene.scene_id}.json"
        )
        metadata = json.loads(product.metadata_path.read_text())
        assert metadata["product"] == "NDVI"
        assert metadata["source_bands"] == ["nir08", "red"]
        assert metadata["crs"] == "EPSG:32639"
        assert metadata["statistics"]["mean"] == pytest.approx(
            (0.62 - 0.20) / (0.62 + 0.20), rel=1e-4
        )

    def test_raster_keeps_transform_and_crs(self, landsat_scene, tmp_path):
        import rasterio

        scene = scene_from_directory(landsat_scene)
        product = generate_index(scene, "SAVI", tmp_path / "out")
        with rasterio.open(product.raster_path) as src:
            assert src.crs is not None and src.crs.to_epsg() == 32639
            assert src.count == 1
            assert src.dtypes[0] == "float32"
            assert np.isnan(src.nodata)
            data = src.read(1)
            assert data.shape == (16, 16)
            assert np.isfinite(data).all()

    def test_all_five_indices_for_sentinel(self, sentinel_scene, tmp_path):
        output = tmp_path / "out"
        scene = scene_from_directory(sentinel_scene)
        products = generate_indices(scene, ["NDVI", "EVI", "SAVI", "NDWI", "OPTRAM"], output)
        assert [product.index for product in products] == ["NDVI", "EVI", "SAVI", "NDWI", "OPTRAM"]
        for product in products:
            assert product.raster_path.exists()
            assert product.metadata_path.exists()
            assert product.raster_path.parent.name == product.index.lower()
            assert product.metadata_path.parent.name == "metadata"

    def test_products_of_different_indices_do_not_collide(self, landsat_scene, tmp_path):
        output = tmp_path / "out"
        scene = scene_from_directory(landsat_scene)
        generate_indices(scene, ["NDVI", "NDWI"], output)
        assert (output / "products" / "ndvi" / f"{scene.scene_id}.tif").exists()
        assert (output / "products" / "ndwi" / f"{scene.scene_id}.tif").exists()

    def test_missing_band_reports_clearly(self, tmp_path):
        folder = tmp_path / "scenes" / "partial"
        write_scene(folder, bands={"red": 0.2, "nir08": 0.6})
        scene = scene_from_directory(folder)
        # EVI additionally needs the blue band, which this scene does not have.
        with pytest.raises(SceneIndexError, match="requires band"):
            generate_index(scene, "EVI", tmp_path / "out")
        # NDVI only needs red + NIR, so it still works.
        assert generate_index(scene, "NDVI", tmp_path / "out").raster_path.exists()

    def test_optram_on_landsat_is_refused(self, landsat_scene, tmp_path):
        scene = scene_from_directory(landsat_scene)
        with pytest.raises(UnsupportedIndexError):
            generate_index(scene, "OPTRAM", tmp_path / "out")

    def test_empty_selection_is_refused(self, landsat_scene, tmp_path):
        scene = scene_from_directory(landsat_scene)
        with pytest.raises(SceneIndexError, match="at least one index"):
            generate_indices(scene, [], tmp_path / "out")

    def test_validation_happens_before_any_work(self, landsat_scene, tmp_path):
        scene = scene_from_directory(landsat_scene)
        output = tmp_path / "out"
        with pytest.raises(UnsupportedIndexError):
            generate_indices(scene, ["NDVI", "OPTRAM"], output)
        # Nothing was written: validation is up-front.
        assert not (output / "products" / "ndvi").exists()

    def test_progress_messages(self, landsat_scene, tmp_path):
        messages = []
        scene = scene_from_directory(landsat_scene)
        generate_index(scene, "NDVI", tmp_path / "out", progress=messages.append)
        assert any("reading" in message for message in messages)
        assert any("saved" in message for message in messages)
        assert any("metadata" in message for message in messages)

    def test_overwrite_is_safe(self, landsat_scene, tmp_path):
        output = tmp_path / "out"
        scene = scene_from_directory(landsat_scene)
        first = generate_index(scene, "NDVI", output)
        second = generate_index(scene, "NDVI", output)
        assert first.raster_path == second.raster_path
        assert first.raster_path.exists()

    def test_nodata_pixels_propagate(self, tmp_path):
        import rasterio
        from rasterio.transform import from_origin

        folder = tmp_path / "scenes" / "nodata"
        folder.mkdir(parents=True)
        for band, value in (("red", 0.2), ("nir08", 0.6)):
            path = folder / f"{band}.tif"
            data = np.full((4, 4), value, dtype="float32")
            data[0, 0] = 0.0
            with rasterio.open(
                path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32",
                crs="EPSG:32639", transform=from_origin(210000, 3430000, 30, 30), nodata=0.0,
            ) as dst:
                dst.write(data, 1)
        (folder / "MTL.json").write_text(json.dumps({"item_id": "NODATA", "datetime": "2024-06-01"}))
        product = generate_index(scene_from_directory(folder), "NDVI", tmp_path / "out")
        with rasterio.open(product.raster_path) as src:
            data = src.read(1, masked=True)
        assert np.ma.is_masked(data[0, 0])
        assert not np.ma.is_masked(data[1, 1])


class TestSceneInfo:
    def test_name_property(self, landsat_scene):
        assert scene_from_directory(landsat_scene).name == landsat_scene.name

    def test_paths_can_be_strings(self, landsat_scene):
        assert scene_from_directory(str(landsat_scene)).scene_id == "LC08_L2SP_166038_20240601"

    def test_scene_info_accepts_plain_dict(self, tmp_path):
        scene = SceneInfo(
            scene_id="X",
            directory=tmp_path,
            satellite="landsat-8",
            bands={"red": tmp_path / "red.tif", "nir08": tmp_path / "nir08.tif"},
        )
        assert scene.name == tmp_path.name

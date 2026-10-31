"""Tests for ``app.core.presets`` — METRIC preset mapping and gating."""

from __future__ import annotations

import json

import numpy as np
import pytest
from app.core import presets
from app.core.indices import scene_from_directory
from app.core.presets import (
    OUTPUT_PRODUCT_NAMES,
    PRESET_CATEGORIES,
    PRODUCT_BANDS,
    FullProcessingRequiredError,
    PresetError,
    engine_presets,
    preset_categories,
    preset_help_entries,
    preset_product_map,
    preset_products,
    run_preset,
    validate_preset_request,
    write_preset_products,
)


class ArrayLike:
    """Minimal stand-in for an ``xarray.DataArray`` returned by the pipeline."""

    def __init__(self, data, crs=None, transform=None):
        self.values = data
        self.attrs = {}
        if crs is not None:
            self.attrs["crs"] = crs
        if transform is not None:
            self.attrs["transform"] = transform


@pytest.fixture
def scene(landsat_scene):
    return scene_from_directory(landsat_scene)


def pipeline_result(products, shape=(8, 8)):
    """``{cube_band: DataArray}`` for the requested product names."""
    return {
        PRODUCT_BANDS[name]: ArrayLike(
            np.full(shape, 1.25, dtype="float32"),
            crs="EPSG:32639",
            transform=(30.0, 0.0, 210000.0, 0.0, -30.0, 3430000.0),
        )
        for name in products
    }


class FakeRunner:
    def __init__(self, products=None, result=None):
        self.products = products
        self.result = result
        self.calls = []

    def __call__(self, scene, categories, destination):
        self.calls.append({"scene": scene, "categories": list(categories)})
        if self.result is not None:
            return self.result
        return pipeline_result(self.products or preset_products("minimal"))


class TestEngineParity:
    """The GUI's copy of the preset tables must match the engine's."""

    def test_preset_names_match_engine(self):
        from data_engine.config.settings import OUTPUT_PRESETS

        assert set(PRESET_CATEGORIES) == set(OUTPUT_PRESETS)

    def test_preset_categories_match_engine(self):
        from data_engine.config.settings import OUTPUT_PRESETS

        for name, categories in OUTPUT_PRESETS.items():
            assert list(PRESET_CATEGORIES[name]) == list(categories), name

    def test_product_lists_match_engine(self):
        from data_engine.config.settings import OUTPUT_PRODUCTS

        assert set(OUTPUT_PRODUCT_NAMES) == set(OUTPUT_PRODUCTS)
        for category, products in OUTPUT_PRODUCTS.items():
            assert OUTPUT_PRODUCT_NAMES[category] == tuple(name for name, _band, _dtype in products)

    def test_product_bands_match_engine(self):
        from data_engine.config.settings import OUTPUT_PRODUCTS

        for products in OUTPUT_PRODUCTS.values():
            for name, band, _dtype in products:
                assert PRODUCT_BANDS[name] == band

    def test_engine_presets_prefers_engine_table(self):
        from data_engine.config.settings import OUTPUT_PRESETS

        assert engine_presets() == {k: list(v) for k, v in OUTPUT_PRESETS.items()}


class TestPresetMapping:
    def test_minimal_is_et_core(self):
        assert preset_categories("minimal") == ["et_core"]
        assert preset_products("minimal") == ["ETaDaily", "ETinst", "ETrF", "LE"]

    def test_standard_includes_energy_balance_and_surface(self):
        categories = preset_categories("standard")
        assert categories == ["et_core", "energy_balance", "surface_props"]
        products = preset_products("standard")
        for name in ("ETaDaily", "Rn", "G", "H", "NDVI", "Albedo", "LST"):
            assert name in products

    def test_full_covers_every_category(self):
        assert preset_categories("full") == list(OUTPUT_PRODUCT_NAMES)

    def test_products_are_unique_within_a_preset(self):
        products = preset_products("full")
        assert len(products) == len(set(products))

    def test_preset_product_map(self):
        mapping = preset_product_map("minimal")
        assert mapping["ETaDaily"] == "ET_daily"
        assert set(mapping) == set(preset_products("minimal"))

    def test_unknown_preset(self):
        with pytest.raises(PresetError, match="Unknown preset"):
            preset_categories("supersize")

    def test_case_insensitive(self):
        assert preset_categories("STANDARD") == preset_categories("standard")

    def test_help_entries(self):
        entries = preset_help_entries()
        assert [name for name, _products in entries] == ["minimal", "standard", "full"]
        assert all(products for _name, products in entries)


class TestGating:
    def test_lite_mode_requires_full_processing(self):
        with pytest.raises(FullProcessingRequiredError, match="Enable full processing"):
            validate_preset_request("minimal", "landsat-8", full_enabled=False)

    def test_full_mode_allows_landsat(self):
        assert validate_preset_request("minimal", "landsat-8", full_enabled=True) == ["et_core"]

    def test_sentinel_scene_is_refused(self):
        with pytest.raises(PresetError, match="Landsat"):
            validate_preset_request("minimal", "sentinel-2", full_enabled=True)

    def test_require_full_mode_helper(self):
        presets.require_full_mode(True)
        with pytest.raises(FullProcessingRequiredError):
            presets.require_full_mode(False)


class TestRunPreset:
    def test_lite_mode_is_blocked_before_the_runner_runs(self, scene, tmp_path):
        runner = FakeRunner()
        with pytest.raises(FullProcessingRequiredError):
            run_preset(scene, "minimal", tmp_path, full_enabled=False, runner=runner)
        assert runner.calls == []
        assert not (tmp_path / "products").exists()

    def test_minimal_writes_et_core_products(self, scene, tmp_path):
        runner = FakeRunner()
        run = run_preset(scene, "minimal", tmp_path, full_enabled=True, runner=runner)

        assert run.preset == "minimal"
        assert run.categories == ["et_core"]
        assert runner.calls[0]["categories"] == ["et_core"]
        written = {path.parent.name for path in run.written}
        assert written == {"ETaDaily", "ETinst", "ETrF", "LE"}

    def test_standard_writes_products_under_products_folder(self, scene, tmp_path):
        run = run_preset(scene, "standard", tmp_path, full_enabled=True, runner=FakeRunner())
        for path in run.written:
            assert path.parent.parent.name == "products"
            assert path.exists()
            metadata = path.parent / "metadata" / f"{scene.scene_id}.json"
            assert metadata.exists()
            payload = json.loads(metadata.read_text())
            assert payload["parameters"]["preset"] == "standard"

    def test_missing_products_are_skipped(self, scene, tmp_path):
        runner = FakeRunner(result=pipeline_result(["ETaDaily"]))
        run = run_preset(scene, "standard", tmp_path, full_enabled=True, runner=runner)
        assert [path.parent.name for path in run.written] == ["ETaDaily"]

    def test_no_products_raises(self, scene, tmp_path):
        runner = FakeRunner(result={})
        with pytest.raises(PresetError, match="produced no products"):
            run_preset(scene, "minimal", tmp_path, full_enabled=True, runner=runner)

    def test_runner_must_return_a_dict(self, scene, tmp_path):
        with pytest.raises(PresetError, match="no product dictionary"):
            run_preset(scene, "minimal", tmp_path, full_enabled=True, runner=lambda *a: None)

    def test_progress_messages(self, scene, tmp_path):
        messages = []
        run_preset(
            scene, "minimal", tmp_path, full_enabled=True, runner=FakeRunner(),
            progress=messages.append,
        )
        assert any("categories" in message for message in messages)
        assert any("wrote" in message for message in messages)

    def test_run_summary(self, scene, tmp_path):
        run = run_preset(scene, "minimal", tmp_path, full_enabled=True, runner=FakeRunner())
        assert "minimal" in run.summary
        assert "4" in run.summary


class TestSpecialDtypes:
    def test_quality_products_are_written_as_uint8(self, scene, tmp_path):
        import rasterio

        result = {
            "ET_quality_class": ArrayLike(np.full((4, 4), 2.0), crs="EPSG:32639",
                                          transform=(30.0, 0.0, 0.0, 0.0, -30.0, 0.0)),
        }
        written = write_preset_products(scene, "full", result, tmp_path)
        assert len(written) == 1
        with rasterio.open(written[0]) as src:
            assert src.dtypes[0] == "uint8"

    def test_float_products_are_float32_with_nan_nodata(self, scene, tmp_path):
        import rasterio

        written = write_preset_products(
            scene, "minimal", pipeline_result(["ETaDaily"]), tmp_path
        )
        with rasterio.open(written[0]) as src:
            assert src.dtypes[0] == "float32"
            assert np.isnan(src.nodata)

    def test_crs_and_transform_come_from_the_dataarray(self, scene, tmp_path):
        import rasterio

        written = write_preset_products(
            scene, "minimal", pipeline_result(["ETaDaily"]), tmp_path
        )
        with rasterio.open(written[0]) as src:
            assert src.crs.to_epsg() == 32639
            assert src.transform.a == 30.0

    def test_squeezes_extra_dimensions(self, scene, tmp_path):
        import rasterio

        data = ArrayLike(np.zeros((1, 4, 5)), crs="EPSG:32639",
                         transform=(30.0, 0.0, 0.0, 0.0, -30.0, 0.0))
        written = write_preset_products(scene, "minimal", {"ET_daily": data}, tmp_path)
        with rasterio.open(written[0]) as src:
            assert (src.height, src.width) == (4, 5)

    def test_raw_numpy_array_is_accepted(self, scene, tmp_path):
        written = write_preset_products(
            scene, "minimal", {"ET_daily": np.ones((3, 3))}, tmp_path
        )
        assert written and written[0].exists()


class TestDefaultRunner:
    def test_requires_weather_input(self, scene):
        runner = presets.DefaultMetricRunner()
        with pytest.raises(PresetError, match="meteorological input"):
            runner._weather()

    def test_accepts_injected_weather(self, scene):
        runner = presets.DefaultMetricRunner(meteo_data={"temperature_2m": 290})
        assert runner._weather() == {"temperature_2m": 290}

    def test_runner_is_used_by_bridge_default(self):
        from app.core.session import LiveEngineBridge

        assert isinstance(LiveEngineBridge().metric_runner(), presets.DefaultMetricRunner)

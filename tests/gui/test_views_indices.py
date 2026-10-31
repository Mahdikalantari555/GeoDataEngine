"""GUI tests: Indices tab (basic indices, METRIC gating, help)."""

from __future__ import annotations

import pytest
from app.core.config import BASIC_INDICES, PRESET_NAMES
from app.core.presets import PRODUCT_BANDS

from tests.gui.conftest import write_scene


@pytest.fixture
def app_with_scenes(app, prompter, tmp_path):
    """App whose output folder already holds one Landsat and one Sentinel scene."""
    output = tmp_path / "output"
    write_scene(output / "scenes" / "landsat_20240601_166_038")
    write_scene(
        output / "scenes" / "sentinel_20240601",
        scene_id="S2B_MSIL2A_20240601_T39SXC",
        bands={"blue": 0.08, "green": 0.12, "red": 0.2, "nir08": 0.62},
        platform="sentinel-2",
    )
    prompter.next_directory = str(output)
    app.browse_output_dir()
    app.refresh_scene_list()
    return app


class TestScenePicker:
    def test_downloaded_scenes_are_listed(self, app_with_scenes):
        assert len(app_with_scenes.scene_listbox.items) == 2
        assert any("landsat" in item for item in app_with_scenes.scene_listbox.items)

    def test_empty_state(self, app):
        assert app.scene_listbox.items == []
        assert app.product_label.cget("text") == "No products yet"

    def test_refresh_picks_up_new_scenes(self, app, tmp_path):
        assert app.scene_listbox.items == []
        write_scene(tmp_path / "output" / "scenes" / "landsat_new")
        app.output_entry.set(str(tmp_path / "output"))
        app.refresh_scene_list()
        assert app.scene_listbox.items

    def test_index_checkboxes(self, app):
        assert list(app.index_vars) == list(BASIC_INDICES)
        assert app.index_vars["NDVI"].get() is True
        assert app.index_vars["OPTRAM"].get() is False


class TestBasicIndexGeneration:
    def test_generate_for_all_scenes(self, app_with_scenes, prompter, tmp_path):
        app_with_scenes.index_vars["NDVI"].set(True)
        app_with_scenes.index_vars["NDWI"].set(True)
        app_with_scenes.generate_indices()

        products = tmp_path / "output" / "products"
        assert (products / "ndvi").is_dir()
        assert list((products / "ndvi").glob("*.tif"))
        assert (products / "ndvi" / "metadata").is_dir()
        assert app_with_scenes.prompter.info_calls

    def test_sentinel_only_index_skipped_for_landsat_scene(self, app_with_scenes):
        """OPTRAM is requested for a Sentinel + Landsat batch."""
        scene = app_with_scenes.session.get_scene("sentinel_20240601")
        assert scene.satellite == "sentinel-2"
        app_with_scenes.scene_listbox.selection_set(1)  # sentinel only
        app_with_scenes.index_vars["OPTRAM"].set(True)
        app_with_scenes.generate_indices()
        assert (list((app_with_scenes.session.config.products_dir / "optram").glob("*.tif")))

    def test_landsat_scene_rejects_optram(self, app_with_scenes):
        app_with_scenes.scene_listbox.selection_set(0)  # landsat
        for name in BASIC_INDICES:
            app_with_scenes.index_vars[name].set(True)
        app_with_scenes.generate_indices()
        # The engine refuses OPTRAM for Landsat and the UI surfaces the error.
        assert app_with_scenes.prompter.error_calls
        assert "Sentinel-2" in app_with_scenes.prompter.error_calls[-1][1]

    def test_no_index_selected_warns(self, app_with_scenes, prompter):
        for name in BASIC_INDICES:
            app_with_scenes.index_vars[name].set(False)
        app_with_scenes.generate_indices()
        assert prompter.warning_calls
        assert "at least one index" in prompter.warning_calls[-1][1]

    def test_no_scenes_warns(self, app, prompter):
        app.generate_indices()
        assert prompter.warning_calls

    def test_selection_is_persisted(self, app_with_scenes):
        app_with_scenes.index_vars["NDVI"].set(True)
        app_with_scenes.index_vars["NDWI"].set(True)
        for name in ("EVI", "SAVI"):
            app_with_scenes.index_vars[name].set(False)
        app_with_scenes.generate_indices()
        assert app_with_scenes.session.store.load().selected_indices == ["NDVI", "NDWI"]

    def test_product_label_is_updated(self, app_with_scenes):
        app_with_scenes.index_vars["NDVI"].set(True)
        app_with_scenes.generate_indices()
        assert "product(s)" in app_with_scenes.product_label.cget("text")

    def test_products_are_logged(self, app_with_scenes):
        app_with_scenes.index_vars["NDVI"].set(True)
        app_with_scenes.generate_indices()
        content = app_with_scenes.indices_log.content
        assert "NDVI" in content

    def test_generate_is_ignored_while_busy(self, app_with_scenes, prompter):
        app_with_scenes.busy = True
        app_with_scenes.generate_indices()
        assert prompter.warning_calls == []


class TestMetricPresets:
    def test_preset_choices(self, app):
        assert list(app.preset_box.values) == list(PRESET_NAMES)

    def test_full_processing_is_gated(self, app_with_scenes, prompter):
        app_with_scenes.generate_metric()
        assert prompter.warning_calls
        assert "Full processing required" in prompter.warning_calls[-1][0]
        assert "Enable full processing" in prompter.warning_calls[-1][1]
        assert "not enabled" in app_with_scenes.last_status

    def test_hint_label_reflects_mode(self, app):
        assert "disabled" in app.full_hint_label.cget("text")
        app.session.set_full_mode(True)
        app.refresh_env_status()
        app._sync_index_availability()
        assert "enabled" in app.full_hint_label.cget("text")

    def test_preset_combo_is_disabled_in_lite_mode(self, app):
        assert app.preset_box.cget("state") == "disabled"

    def test_preset_combo_is_enabled_in_full_mode(self, app):
        app.session.set_full_mode(True)
        app.refresh_env_status()
        app._sync_index_availability()
        assert app.preset_box.cget("state") == "readonly"

    def test_metric_run_writes_products(self, app_with_scenes, fake_bridge, tmp_path):
        import numpy as np

        class Array:
            values = np.ones((4, 4), dtype="float32")
            attrs = {"crs": "EPSG:32639", "transform": (30.0, 0.0, 0.0, 0.0, -30.0, 0.0)}

        fake_bridge.preset_results = {
            PRODUCT_BANDS[name]: Array() for name in ("ETaDaily", "ETinst", "ETrF", "LE")
        }
        app_with_scenes.session.set_full_mode(True)
        app_with_scenes.refresh_env_status()
        app_with_scenes._sync_index_availability()
        app_with_scenes.scene_listbox.selection_set(0)  # landsat only
        app_with_scenes.preset_box.set("minimal")
        app_with_scenes.generate_metric()

        products = tmp_path / "output" / "products"
        assert (products / "ETaDaily").is_dir()
        assert app_with_scenes.prompter.error_calls == []
        assert "METRIC" in app_with_scenes.last_status

    def test_metric_failure_is_reported(self, app_with_scenes, prompter):
        """No preset results → PresetError surfaces as a dialog."""
        app_with_scenes.session.set_full_mode(True)
        app_with_scenes.scene_listbox.selection_set(0)
        app_with_scenes.generate_metric()
        assert prompter.error_calls
        assert "no products" in prompter.error_calls[-1][1]


class TestHelpFromIndicesTab:
    def test_help_button_opens_the_dialog(self, app, fake_toolkit, prompter):
        fake_toolkit.find_button("Help").invoke()
        assert prompter.help_calls
        assert "METRIC presets" in prompter.help_calls[0]


class TestSentinelAwareIndexGating:
    """OPTRAM is greyed out for Landsat and never silently dropped."""

    def test_optram_checkbox_is_disabled_for_landsat(self, app):
        assert app.session.config.satellite == "landsat-8"
        assert app.index_checks["OPTRAM"].cget("state") == "disabled"
        assert app.index_checks["NDVI"].cget("state") != "disabled"

    def test_optram_checkbox_is_enabled_for_sentinel(self, app):
        app.satellite_box.set("sentinel-2")
        app._collect_config()
        app._sync_index_availability()
        assert app.index_checks["OPTRAM"].cget("state") == "normal"

    def test_switching_to_landsat_clears_a_ticked_optram(self, app):
        app.satellite_box.set("sentinel-2")
        app._collect_config()
        app._sync_index_availability()
        app.index_vars["OPTRAM"].set(True)

        app.satellite_box.set("landsat-8")
        app._collect_config()
        app._sync_index_availability()

        assert app.index_vars["OPTRAM"].get() is False

    def test_config_never_keeps_optram_for_landsat(self, app):
        app.index_vars["OPTRAM"].set(True)
        cfg = app._collect_config()
        assert "OPTRAM" not in cfg.selected_indices
        assert "NDVI" in cfg.selected_indices

    def test_config_keeps_optram_for_sentinel(self, app):
        app.satellite_box.set("sentinel-2")
        app.index_vars["OPTRAM"].set(True)
        assert "OPTRAM" in app._collect_config().selected_indices

    def test_invalid_combination_fails_before_writing_anything(self, app_with_scenes, tmp_path):
        """A Landsat scene + OPTRAM is rejected up-front, no partial output."""
        app_with_scenes.scene_listbox.selection_set(0)  # Landsat
        for name in app_with_scenes.index_vars:
            app_with_scenes.index_vars[name].set(True)

        app_with_scenes.generate_indices()

        products = tmp_path / "output" / "products"
        assert not products.exists() or not list(products.rglob("*.tif"))
        assert app_with_scenes.prompter.error_calls
        assert "not available" in app_with_scenes.prompter.error_calls[-1][1]

    def test_mixed_batch_checks_every_scene(self, app_with_scenes, prompter):
        """Batch over Landsat + Sentinel with OPTRAM is refused as a whole."""
        for scene in app_with_scenes.session.scene_infos():
            app_with_scenes.session.selected_ids.add(scene.scene_id)
        app_with_scenes.index_vars["OPTRAM"].set(True)
        app_with_scenes.generate_indices()
        assert prompter.error_calls
        assert "OPTRAM" in prompter.error_calls[-1][1]

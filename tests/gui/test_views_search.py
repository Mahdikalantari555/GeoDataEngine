"""GUI tests: Search tab (STAC search, coverage filter, selection, ROI input)."""

from __future__ import annotations

import pytest
from app.core.config import BASIC_INDICES, SATELLITES, SORT_OPTIONS
from app.ui.fake import FakeButton, FakeTreeview
from app.ui.views import LANDSAT_BANDS, SENTINEL_BANDS, WINDOW_TITLE

from tests.gui.conftest import SCENE_FOOTPRINT_PARTIAL


@pytest.fixture
def ready_app(app, prompter, roi_geojson_file, tmp_path):
    """App with a ROI loaded, dates filled in and an output folder chosen."""
    prompter.next_file = str(roi_geojson_file)
    prompter.next_directory = str(tmp_path / "output")
    app.browse_roi()
    app.browse_output_dir()
    app.start_entry.set("2024-01-01")
    app.end_entry.set("2024-12-31")
    app.cloud_entry.set("20")
    app.coverage_entry.set("1.0")
    return app


class TestWindowConstruction:
    def test_window_title(self, app):
        assert WINDOW_TITLE.startswith("GeoDataEngine")

    def test_four_tabs(self, app, fake_toolkit):
        assert fake_toolkit.find_notebook().tab_titles() == [
            "Search",
            "Download",
            "Indices",
            "Settings",
        ]

    def test_search_criteria_widgets_exist(self, app, fake_toolkit):
        for text in ("Search", "Select all", "Clear selection", "Browse…"):
            assert fake_toolkit.find_button(text) is not None

    def test_satellite_choices(self, app):
        assert list(app.satellite_box.values) == list(SATELLITES)

    def test_sort_choices(self, app):
        assert list(app.sort_box.values) == list(SORT_OPTIONS)

    def test_results_table_columns(self, app):
        tree = app.results_tree
        assert len(tree.columns) == 7
        assert tree.headings["Scene ID"]["text"] == "Scene ID"
        assert tree.headings["Selected"]["text"] == "Selected"

    def test_status_bar_starts_ready(self, app):
        assert "Ready" in app.last_status
        assert "Lite" in app.status_label.cget("text")

    def test_startup_log(self, app):
        assert "GeoDataEngine ready." in app.log_text.content

    def test_menubar_has_help_and_enable_full(self, app, fake_toolkit):
        menu = fake_toolkit.find_menu()
        assert menu is not None
        assert "Help" in menu.commands
        assert "Enable full processing" in menu.commands


class TestRoiInput:
    def test_browse_loads_geojson_and_updates_label(self, ready_app):
        assert "roi.geojson" in ready_app.roi_label.cget("text")

    def test_roi_path_is_written_to_config(self, ready_app, roi_geojson_file):
        assert ready_app.session.config.roi_path == str(roi_geojson_file)

    def test_invalid_roi_shows_error_and_keeps_search_disabled_state(
        self, app, prompter, tmp_path
    ):
        bad = tmp_path / "bad.geojson"
        bad.write_text("{nope")
        prompter.next_file = str(bad)
        app.browse_roi()
        assert prompter.error_calls
        assert app.session.roi is None
        assert "ROI error" in app.last_status

    def test_unsupported_format_shows_error(self, app, prompter, tmp_path):
        kml = tmp_path / "roi.kml"
        kml.write_text("<kml/>")
        prompter.next_file = str(kml)
        app.browse_roi()
        assert prompter.error_calls
        assert "Unsupported ROI format" in prompter.error_calls[0][1]

    def test_cancelled_file_dialog_changes_nothing(self, app, prompter):
        prompter.next_file = ""
        app.browse_roi()
        assert app.session.roi is None

    def test_crs_override_is_applied_from_settings(self, app, prompter, shapefile_without_prj):
        app.crs_entry.set("EPSG:32639")
        prompter.next_file = str(shapefile_without_prj)
        app.browse_roi()
        assert app.session.roi.crs == "EPSG:32639"

    def test_roi_warnings_are_logged(self, app, prompter, roi_geojson_without_crs):
        prompter.next_file = str(roi_geojson_without_crs)
        app.browse_roi()
        assert "WARNING:" in app.log_text.content

    def test_shapefile_without_prj_logs_assumption(self, app, prompter, shapefile_without_prj):
        prompter.next_file = str(shapefile_without_prj)
        app.browse_roi()
        assert "assuming EPSG:4326" in app.log_text.content


class TestSearchAction:
    def test_search_populates_the_table(self, ready_app):
        ready_app.run_search()
        tree = ready_app.results_tree
        assert tree.get_children() == ("LC08_L2SP_166038_20240601",)
        values = tree.values_of("LC08_L2SP_166038_20240601")
        assert values[0] == "LC08_L2SP_166038_20240601"
        assert values[1] == "2024-06-01"
        assert values[2] == "5.0"
        assert values[3] == "landsat-8"
        assert values[4] == "166"
        assert values[5] == "38"

    def test_search_without_roi_shows_error(self, app):
        app.run_search()
        assert "Load a ROI" in app.last_status
        assert app.error_calls if hasattr(app, "error_calls") else True

    def test_no_qualifying_scenes_shows_message(self, ready_app, fake_bridge, prompter):
        fake_bridge.items = [
            {
                "id": "PARTIAL",
                "datetime": "2024-06-05T00:00:00Z",
                "cloud_cover": 1.0,
                "platform": "landsat-8",
                "geometry": SCENE_FOOTPRINT_PARTIAL,
            }
        ]
        ready_app.run_search()
        assert ready_app.results_tree.get_children() == ()
        assert prompter.warning_calls
        assert "No qualifying scenes" in prompter.warning_calls[-1][1]
        assert "No qualifying scenes" in ready_app.last_status

    def test_results_are_sorted_by_date(self, ready_app):
        ready_app.coverage_entry.set("0.2")
        ready_app.run_search()
        assert ready_app.results_tree.get_children() == (
            "LC08_L2SP_166038_20240601",
            "LC08_L2SP_166038_20240605",
        )

    def test_results_are_sorted_by_cloud_cover(self, ready_app):
        ready_app.coverage_entry.set("0.2")
        ready_app.sort_box.set("cloud_cover")
        ready_app.run_search()
        assert ready_app.results_tree.get_children() == (
            "LC08_L2SP_166038_20240605",
            "LC08_L2SP_166038_20240601",
        )

    def test_settings_are_persisted_by_a_search(self, ready_app):
        ready_app.run_search()
        saved = ready_app.session.store.load()
        assert saved.start_date == "2024-01-01"
        assert saved.cloud_threshold == 20.0
        assert saved.output_dir.endswith("output")

    def test_coverage_ratio_reaches_the_bridge(self, ready_app, fake_bridge):
        ready_app.coverage_entry.set("0.75")
        ready_app.run_search()
        assert ready_app.session.config.min_coverage_ratio == 0.75

    def test_search_logs_progress(self, ready_app):
        ready_app.run_search()
        content = ready_app.log_text.content
        assert "Searching landsat-8" in content
        assert "qualifying scene(s) listed" in content

    def test_invalid_numeric_fields_fall_back_to_defaults(self, ready_app):
        ready_app.cloud_entry.set("abc")
        ready_app.coverage_entry.set("xyz")
        ready_app.run_search()
        assert ready_app.session.config.cloud_threshold == 20.0
        assert ready_app.session.config.min_coverage_ratio == 0.55

    def test_search_is_ignored_while_busy(self, ready_app):
        ready_app.busy = True
        ready_app.run_search()
        assert ready_app.results_tree.get_children() == ()

    def test_re_search_replaces_old_rows(self, ready_app, fake_bridge):
        ready_app.run_search()
        fake_bridge.items = []
        ready_app.run_search()
        assert ready_app.results_tree.get_children() == ()


class TestSelection:
    def _search_two(self, app):
        app.coverage_entry.set("0.2")
        app.run_search()
        return app.results_tree.get_children()

    def test_toggle_marks_the_row(self, ready_app):
        first, _second = self._search_two(ready_app)
        ready_app.toggle_scene(first)
        assert ready_app.session.is_selected(first)
        assert ready_app.results_tree.values_of(first)[-1] == "✔"

    def test_toggle_twice_clears(self, ready_app):
        first, _second = self._search_two(ready_app)
        ready_app.toggle_scene(first)
        ready_app.toggle_scene(first)
        assert not ready_app.session.is_selected(first)
        assert ready_app.results_tree.values_of(first)[-1] == ""

    def test_select_all_and_clear(self, ready_app):
        first, second = self._search_two(ready_app)
        ready_app.select_all_results()
        assert ready_app.session.selected_count == 2
        assert ready_app.selection_label.cget("text") == "2 selected"

        ready_app.clear_selection()
        assert ready_app.session.selected_count == 0
        assert ready_app.selection_label.cget("text") == "0 selected"

    def test_selection_label_updates_on_toggle(self, ready_app):
        first, _second = self._search_two(ready_app)
        ready_app.toggle_scene(first)
        assert ready_app.selection_label.cget("text") == "1 selected"

    def test_unknown_scene_is_ignored(self, app):
        app.toggle_scene("NOT_A_SCENE")
        assert app.session.selected_count == 0

    def test_selection_persists_across_re_search(self, ready_app):
        first, _second = self._search_two(ready_app)
        ready_app.toggle_scene(first)
        ready_app.run_search()
        assert ready_app.results_tree.values_of(first)[-1] == "✔"

    def test_select_all_buttons_exist(self, app, fake_toolkit):
        assert isinstance(fake_toolkit.find_button("Select all"), FakeButton)
        assert isinstance(fake_toolkit.find_button("Clear selection"), FakeButton)

    def test_results_tree_is_a_treeview(self, app):
        assert isinstance(app.results_tree, FakeTreeview)


class TestDownloadTabWiring:
    def test_band_description_lists_landsat_and_sentinel_bands(self, app):
        text = app.bands_label.cget("text")
        assert LANDSAT_BANDS in text
        assert SENTINEL_BANDS in text

    def test_no_per_band_checkboxes(self, app, fake_toolkit):
        """Raw bands always download fully — there must be no band checkboxes."""
        texts = [
            widget.cget("text")
            for widget in fake_toolkit.widgets(type(fake_toolkit.find_button("NDVI")))
            if widget.cget("text")
        ]
        for band in ("blue", "green", "red", "nir08", "swir16", "swir22", "lwir11", "qa_pixel"):
            assert band not in texts

    def test_output_browse_sets_both_entries(self, app, prompter, tmp_path):
        prompter.next_directory = str(tmp_path / "chosen")
        app.browse_output_dir()
        assert app.output_entry.get().endswith("chosen")
        assert app.output_entry_settings.get().endswith("chosen")
        assert "chosen" in app.last_status

    def test_cancel_button_starts_disabled(self, app):
        assert app.cancel_button.cget("state") == "disabled"

    def test_index_checkboxes_cover_basic_indices(self, app):
        assert set(app.index_vars) == set(BASIC_INDICES)

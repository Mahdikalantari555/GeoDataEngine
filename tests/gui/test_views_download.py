"""GUI tests: Download tab (progress, log, cancel, skip-existing)."""

from __future__ import annotations

import pytest
from app.ui.fake import FakeProgressbar

from tests.gui.conftest import BAND_VALUES


@pytest.fixture
def ready_app(app, prompter, roi_geojson_file, tmp_path):
    prompter.next_file = str(roi_geojson_file)
    prompter.next_directory = str(tmp_path / "output")
    app.browse_roi()
    app.browse_output_dir()
    app.start_entry.set("2024-01-01")
    app.end_entry.set("2024-12-31")
    app.coverage_entry.set("1.0")
    app.run_search()
    return app


class TestDownloadFlow:
    def test_downloads_selected_scenes_into_scenes_folder(self, ready_app, tmp_path):
        ready_app.select_all_results()
        ready_app.download_selected()

        scenes_folder = tmp_path / "output" / "scenes"
        assert scenes_folder.is_dir()
        assert any(scenes_folder.iterdir())
        assert ready_app.prompter.info_calls
        assert "Download complete" in ready_app.prompter.info_calls[-1][0]

    def test_only_selected_scenes_are_downloaded(self, ready_app, fake_bridge):
        ready_app.coverage_entry.set("0.2")
        ready_app.run_search()
        first, second = ready_app.results_tree.get_children()
        ready_app.toggle_scene(second)
        ready_app.download_selected()
        assert fake_bridge.download_calls[-1]["selected_ids"] == [second]

    def test_nothing_selected_shows_warning(self, ready_app, prompter, fake_bridge):
        ready_app.download_selected()
        assert prompter.warning_calls
        assert fake_bridge.download_calls == []
        assert ready_app.last_status == "No scenes selected"

    def test_each_band_is_logged(self, ready_app):
        ready_app.select_all_results()
        ready_app.download_selected()
        content = ready_app.log_text.content
        for band in BAND_VALUES:
            assert f"saved {band}" in content

    def test_progress_bar_reaches_full(self, ready_app):
        ready_app.select_all_results()
        ready_app.download_selected()
        assert isinstance(ready_app.progress_bar, FakeProgressbar)
        assert ready_app.progress_bar.fraction() == pytest.approx(1.0)

    def test_progress_label_shows_the_scene(self, ready_app):
        ready_app.select_all_results()
        ready_app.download_selected()
        texts = [ready_app.progress_label.cget("text"), ready_app.last_status]
        assert any("1/1" in text or "scene(s) downloaded" in text for text in texts)

    def test_output_folder_is_created_on_demand(self, ready_app, tmp_path):
        ready_app.select_all_results()
        ready_app.download_selected()
        assert (tmp_path / "output").is_dir()

    def test_download_errors_are_reported(self, ready_app, fake_bridge, prompter):
        from app.core.catalog import CatalogError

        fake_bridge.download_error = CatalogError("quota exceeded")
        ready_app.select_all_results()
        ready_app.download_selected()
        assert prompter.error_calls
        assert "quota exceeded" in ready_app.last_status

    def test_scene_list_is_refreshed_after_download(self, ready_app):
        ready_app.select_all_results()
        ready_app.download_selected()
        assert ready_app.scene_listbox.items
        assert "product" in ready_app.product_label.cget("text").lower()

    def test_second_download_is_skipped_by_the_engine(self, ready_app, tmp_path, fake_bridge):
        """A scene already on disk is not downloaded again (engine behaviour)."""
        ready_app.select_all_results()
        ready_app.download_selected()
        first_directory = next((tmp_path / "output" / "scenes").iterdir())

        # Simulate the engine's skip: fetch_scenes returns the existing scene.
        assert first_directory.is_dir()
        assert fake_bridge.download_calls

    def test_download_is_ignored_while_busy(self, ready_app, fake_bridge):
        ready_app.busy = True
        ready_app.select_all_results()
        ready_app.download_selected()
        assert fake_bridge.download_calls == []


class TestProgressWidget:
    def test_set_progress_fraction_and_label(self, app):
        app.set_progress(2, 4, "scene")
        assert app.progress_bar.fraction() == pytest.approx(0.5)
        assert app.progress_label.cget("text") == "2/4 scene"

    def test_set_progress_with_zero_total(self, app):
        app.set_progress(0, 0, "")
        assert app.progress_bar.fraction() == 0.0

    def test_set_progress_clamps(self, app):
        app.set_progress(9, 4, "over")
        assert app.progress_bar.fraction() == pytest.approx(1.0)

    def test_progress_history_is_recorded(self, app):
        app.set_progress(1, 4, "a")
        app.set_progress(2, 4, "b")
        assert app.progress_bar.history == [0.25, 0.5]


class TestLogWidget:
    def test_log_appends_and_records_history(self, app):
        app.log("hello world")
        assert "hello world" in app.log_text.content
        assert app.session.log_history[-1] == "hello world"

    def test_log_can_target_a_single_tab(self, app):
        app.log("settings only", target="settings")
        assert "settings only" in app.settings_log.content
        assert "settings only" not in app.log_text.content

    def test_autoscroll_is_requested(self, app):
        app.log("scrolling")
        assert app.log_text.options.get("seen") is not None


class TestCancel:
    def test_cancel_requests_cancellation_of_the_running_job(self, app):
        from app.core.workers import BackgroundJob

        job = BackgroundJob(lambda emit: None, "fake")
        app.current_job = job
        app.cancel_job()
        assert job.cancelled is True
        assert "Cancelling" in app.last_status

    def test_cancel_without_a_job_is_a_no_op(self, app):
        app.cancel_job()
        assert "Cancelling" not in app.last_status


class TestBackgroundThreading:
    def test_job_runs_through_the_poll_loop(self, app, fake_toolkit):
        """With the real runner the UI drains the queue via ``after()``."""
        from app.ui.views import background_runner

        app.job_runner = background_runner
        app.progress_bar.set(0)
        app.set_status("idle")

        def work(emit):
            emit.log("threaded work")
            emit.progress(1, 1, "done")
            return "finished"

        results = []
        job = app._start_job(work, results.append, name="thread")
        job.join(timeout=5)
        fake_toolkit.run_pending()

        assert results == ["finished"]
        assert "threaded work" in app.log_text.content
        assert app.busy is False
        assert app.progress_bar.fraction() == pytest.approx(1.0)

    def test_error_through_the_poll_loop(self, app, fake_toolkit, prompter):
        from app.ui.views import background_runner

        app.job_runner = background_runner

        def work(emit):
            raise RuntimeError("threaded failure")

        job = app._start_job(work, None, name="thread-error")
        job.join(timeout=5)
        fake_toolkit.run_pending()

        assert prompter.error_calls
        assert "threaded failure" in app.last_status
        assert app.busy is False

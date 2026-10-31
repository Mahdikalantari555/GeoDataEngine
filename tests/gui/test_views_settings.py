"""GUI tests: Settings tab, persistence across restarts and environment status."""

from __future__ import annotations

import json

from app.core.bootstrap import Bootstrapper
from app.core.config import DEFAULT_MIRROR_URL, AppConfig, ConfigStore
from app.ui.views import DesktopApp, SyncJobRunner


class TestFieldBinding:
    def test_defaults_are_shown(self, app):
        assert app.mirror_entry.get() == DEFAULT_MIRROR_URL
        assert app.cloud_entry.get() == "20.0"
        assert app.coverage_entry.get() == "0.55"

    def test_fields_are_read_into_config(self, app, tmp_path):
        app.start_entry.set("2024-03-01")
        app.end_entry.set("2024-03-31")
        app.cloud_entry.set("12.5")
        app.coverage_entry.set("0.9")
        app.satellite_box.set("sentinel-2")
        app.sort_box.set("cloud_cover")
        app.crs_entry.set("EPSG:32639")
        app.mirror_entry.set("https://pypi.org/simple")
        app.output_entry.set(str(tmp_path / "chosen"))

        cfg = app._collect_config()

        assert cfg.start_date == "2024-03-01"
        assert cfg.end_date == "2024-03-31"
        assert cfg.cloud_threshold == 12.5
        assert cfg.min_coverage_ratio == 0.9
        assert cfg.satellite == "sentinel-2"
        assert cfg.sort_by == "cloud_cover"
        assert cfg.crs_override == "EPSG:32639"
        assert cfg.mirror_url == "https://pypi.org/simple"
        assert cfg.output_dir.endswith("chosen")

    def test_invalid_numbers_keep_previous_values(self, app):
        app.cloud_entry.set("not-a-number")
        assert app._collect_config().cloud_threshold == 20.0

    def test_out_of_range_values_are_clamped(self, app):
        app.cloud_entry.set("500")
        app.coverage_entry.set("7")
        cfg = app._collect_config()
        assert cfg.cloud_threshold == 100.0
        assert cfg.min_coverage_ratio == 1.0


class TestSaveSettings:
    def test_save_persists_every_field(self, app, tmp_path):
        app.output_entry_settings.set(str(tmp_path / "new_output"))
        app.settings_start_entry.set("2024-01-01")
        app.settings_end_entry.set("2024-12-31")
        app.settings_cloud_entry.set("15")
        app.settings_coverage_entry.set("0.8")
        app.mirror_entry.set("https://pypi.org/simple")
        app.crs_entry.set("EPSG:32639")

        app.save_settings()

        saved = json.loads(app.session.store.path.read_text())
        assert saved["output_dir"].endswith("new_output")
        assert saved["start_date"] == "2024-01-01"
        assert saved["cloud_threshold"] == 15.0
        assert saved["min_coverage_ratio"] == 0.8
        assert saved["mirror_url"] == "https://pypi.org/simple"
        assert saved["crs_override"] == "EPSG:32639"
        assert app.last_status == "Settings saved"

    def test_save_is_logged_on_the_settings_tab(self, app):
        app.save_settings()
        assert "Settings saved" in app.settings_log.content

    def test_save_button_is_wired(self, app, fake_toolkit, tmp_path):
        app.output_entry_settings.set(str(tmp_path / "via_button"))
        fake_toolkit.find_button("Save settings").invoke()
        assert app.session.store.load().output_dir.endswith("via_button")


class TestPersistenceAcrossRestart:
    def test_settings_are_restored_on_startup(self, tmp_path, fake_bridge, fake_toolkit):
        store = ConfigStore(tmp_path / "appdir")
        store.save(
            AppConfig(
                roi_path="",
                start_date="2023-05-01",
                end_date="2023-09-30",
                output_dir=str(tmp_path / "restored"),
                cloud_threshold=8.0,
                min_coverage_ratio=0.7,
                satellite="sentinel-2",
                sort_by="cloud_cover",
                mirror_url="https://pypi.org/simple",
                crs_override="EPSG:32639",
                selected_indices=["NDWI"],
            )
        )

        from app.core.session import Session

        session = Session(store=store, bridge=fake_bridge)
        bootstrapper = Bootstrapper(store, app_root=tmp_path / "appdir", probe=lambda m: True)
        prompter = _Prompter()
        desktop = DesktopApp(
            session, bootstrapper, toolkit=fake_toolkit, prompter=prompter,
            job_runner=SyncJobRunner(),
        ).build()

        assert desktop.start_entry.get() == "2023-05-01"
        assert desktop.end_entry.get() == "2023-09-30"
        assert desktop.cloud_entry.get() == "8.0"
        assert desktop.coverage_entry.get() == "0.7"
        assert desktop.satellite_box.get() == "sentinel-2"
        assert desktop.sort_box.get() == "cloud_cover"
        assert desktop.mirror_entry.get() == "https://pypi.org/simple"
        assert desktop.crs_entry.get() == "EPSG:32639"
        assert desktop.output_entry.get().endswith("restored")
        assert desktop.index_vars["NDWI"].get() is True
        assert desktop.index_vars["NDVI"].get() is False

    def test_missing_saved_roi_is_reported_but_not_fatal(self, tmp_path, fake_bridge, fake_toolkit):
        store = ConfigStore(tmp_path / "appdir")
        store.save(AppConfig(roi_path=str(tmp_path / "gone.geojson")))
        from app.core.session import Session

        desktop = DesktopApp(
            Session(store=store, bridge=fake_bridge),
            Bootstrapper(store, app_root=tmp_path / "appdir", probe=lambda m: True),
            toolkit=fake_toolkit,
            prompter=_Prompter(),
            job_runner=SyncJobRunner(),
        ).build()
        assert desktop.session.roi is None
        assert "could not be loaded" in desktop.log_text.content


class TestEnvironmentStatus:
    def test_lite_status_is_displayed(self, app):
        assert app.env_label.cget("text") == "Environment: Lite"

    def test_full_status_is_displayed(self, app):
        app.session.set_full_mode(True)
        app.refresh_env_status()
        assert "Full" in app.env_label.cget("text")

    def test_enable_button_is_disabled_in_full_mode(self, app):
        app.session.set_full_mode(True)
        app.refresh_env_status()
        assert app.enable_full_button.cget("state") == "disabled"

    def test_prepare_environment_runs_the_bootstrapper(self, app, tmp_path):
        created = []

        def runner(args, on_line=None):
            created.append(args)
            if "venv" in args:
                venv = tmp_path / "appdir" / ".venv" / "bin" / "python"
                venv.parent.mkdir(parents=True, exist_ok=True)
                venv.write_text("#!/bin/sh\n")
            return 0

        app.bootstrapper.runner = runner
        app.bootstrapper.probe = lambda module: False
        app.prepare_environment()

        assert created
        assert app.last_status == "Environment ready"
        assert "Environment prepared" in app.settings_log.content

    def test_enable_full_processing_installs_and_switches_mode(self, app, prompter):
        commands = []

        def runner(args, on_line=None):
            commands.append(args)
            return 0

        app.bootstrapper.runner = runner
        app.bootstrapper.probe = lambda module: False
        app.enable_full_processing()

        assert any("requirements-full.txt" in " ".join(command) for command in commands)
        assert app.session.full_mode_enabled() is True
        assert app.session.store.load().mode == "full"
        assert prompter.info_calls
        assert "Full processing enabled" in prompter.info_calls[-1][0]
        assert app.preset_box.cget("state") == "readonly"

    def test_failed_install_stays_lite(self, app, prompter):
        app.bootstrapper.runner = lambda args, on_line=None: 1
        app.bootstrapper.probe = lambda module: False
        app.enable_full_processing()
        assert app.session.full_mode_enabled() is False
        assert prompter.error_calls
        assert "install" in prompter.error_calls[-1][1].lower()

    def test_install_is_ignored_while_busy(self, app):
        app.busy = True
        app.enable_full_processing()
        assert app.session.full_mode_enabled() is False


class TestPrompter:
    def test_toolkit_prompter_uses_the_toolkit_dialogs(self, fake_toolkit):
        from app.ui.views import ToolkitPrompter

        fake_toolkit.next_file = "/data/roi.geojson"
        fake_toolkit.next_directory = "/data/out"
        prompter = ToolkitPrompter(fake_toolkit)

        assert prompter.open_file("Select", kind="roi") == "/data/roi.geojson"
        assert prompter.open_file("Select", kind="weather") == "/data/roi.geojson"
        assert prompter.open_directory("Pick") == "/data/out"

        prompter.info("t", "m")
        prompter.error("t", "m")
        prompter.warning("t", "m")
        prompter.help("body")

        assert fake_toolkit.info_calls == [("t", "m")]
        assert fake_toolkit.error_calls == [("t", "m")]
        assert fake_toolkit.warning_calls == [("t", "m")]
        assert fake_toolkit.dialogs == [("GeoDataEngine help", "body")]


class _Prompter:
    def __init__(self):
        self.next_file = ""
        self.next_directory = ""
        self.info_calls = []
        self.error_calls = []
        self.warning_calls = []
        self.help_calls = []

    def open_file(self, title="", kind="roi"):
        return self.next_file

    def open_directory(self, title=""):
        return self.next_directory

    def info(self, title, message):
        self.info_calls.append((title, message))

    def error(self, title, message):
        self.error_calls.append((title, message))

    def warning(self, title, message):
        self.warning_calls.append((title, message))

    def help(self, body):
        self.help_calls.append(body)

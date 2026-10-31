"""Tests for the launcher entry point (change task 1.4).

The real Tk window cannot be opened in this environment (no Tk libraries, no
display), so the tests assert the launcher wiring: configuration loading,
environment preparation, exit codes, and that the Tk view is only constructed
after Tk has been confirmed available.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from app import main as launcher
from app.core.config import ConfigStore


class RecordingDesktopApp:
    """Stands in for ``app.ui.views.DesktopApp`` and records the lifecycle."""

    instances: list[RecordingDesktopApp] = []

    def __init__(self, session=None, bootstrapper=None, **kwargs):
        self.session = session
        self.bootstrapper = bootstrapper
        self.built = False
        self.ran = False
        RecordingDesktopApp.instances.append(self)

    def build(self):
        self.built = True
        return self

    def mainloop(self):
        self.ran = True

    def run(self):
        self.built = True
        self.ran = True


@pytest.fixture(autouse=True)
def reset_instances():
    RecordingDesktopApp.instances.clear()
    yield
    RecordingDesktopApp.instances.clear()


@pytest.fixture
def fake_tk_app(monkeypatch):
    import app.ui.views as views

    monkeypatch.setattr(views, "DesktopApp", RecordingDesktopApp)
    return RecordingDesktopApp


class TestArgumentParsing:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            launcher.parse_args(["--help"])
        assert excinfo.value.code == 0
        assert "geodataengine-gui" in capsys.readouterr().out

    def test_unknown_flag_exits_two(self):
        with pytest.raises(SystemExit) as excinfo:
            launcher.parse_args(["--nope"])
        assert excinfo.value.code == 2


class TestLaunch:
    def test_launch_builds_and_enters_the_event_loop(self, tmp_path, fake_tk_app):
        assert launcher.main(["--no-bootstrap", "--app-dir", str(tmp_path)]) == launcher.EXIT_OK
        app = fake_tk_app.instances[-1]
        assert app.built is True
        assert app.ran is True
        assert app.session.store.directory == tmp_path

    def test_launch_loads_the_saved_config(self, tmp_path, fake_tk_app):
        store = ConfigStore(tmp_path)
        config = store.load()
        config.output_dir = str(tmp_path / "saved_output")
        store.save(config)

        launcher.main(["--no-bootstrap", "--app-dir", str(tmp_path)])

        assert fake_tk_app.instances[-1].session.config.output_dir == str(
            tmp_path / "saved_output"
        )

    def test_launch_prepares_the_environment_first(self, tmp_path, fake_tk_app):
        """Without the essentials the bootstrapper runs before the window opens."""
        from app.core.bootstrap import Bootstrapper

        order: list[str] = []
        store = ConfigStore(tmp_path)
        boot = Bootstrapper(store, app_root=tmp_path, probe=lambda module: False)
        boot.runner = lambda args, on_line=None: 0
        for name in ("requirements.txt", "requirements-full.txt"):
            (tmp_path / name).write_text("# test stand-in\n", encoding="utf-8")

        original_install = boot.install_essentials

        def recording_install(*args, **kwargs):
            # Simulate a successful first run: create the venv marker first.
            boot.env_python.parent.mkdir(parents=True, exist_ok=True)
            boot.env_python.write_text("#!/bin/sh\n")
            order.append("prepare")
            return original_install(*args, **kwargs)

        boot.install_essentials = recording_install  # type: ignore[method-assign]

        assert launcher.main(
            ["--app-dir", str(tmp_path)], bootstrapper=boot, store=store
        ) == launcher.EXIT_OK
        assert order == ["prepare"]
        assert fake_tk_app.instances[-1].ran is True

    def test_bootstrap_failure_exits_with_env_code(self, tmp_path, fake_tk_app):
        from app.core.bootstrap import Bootstrapper

        store = ConfigStore(tmp_path)
        boot = Bootstrapper(store, app_root=tmp_path, probe=lambda module: False)
        boot.runner = lambda args, on_line=None: 1  # pip/venv fails

        assert launcher.main(
            ["--app-dir", str(tmp_path)], bootstrapper=boot, store=store
        ) == launcher.EXIT_ENV
        assert fake_tk_app.instances == []

    def test_keyboard_interrupt_exits_cleanly(self, tmp_path, fake_tk_app, monkeypatch):
        def interrupt(self):
            raise KeyboardInterrupt

        monkeypatch.setattr(RecordingDesktopApp, "run", interrupt)
        assert launcher.main(["--no-bootstrap", "--app-dir", str(tmp_path)]) == launcher.EXIT_ENV

    def test_no_bootstrap_skips_the_install(self, tmp_path, fake_tk_app):
        from app.core.bootstrap import Bootstrapper

        store = ConfigStore(tmp_path)
        boot = Bootstrapper(store, app_root=tmp_path, probe=lambda module: False)
        assert launcher.main(
            ["--no-bootstrap", "--app-dir", str(tmp_path)], bootstrapper=boot, store=store
        ) == launcher.EXIT_OK
        assert boot.venv_exists() is False


class TestSetupOnly:
    def test_setup_only_exits_without_opening_a_window(self, tmp_path, fake_tk_app):
        (tmp_path / "requirements.txt").write_text("# nothing to install\n")
        assert launcher.main(["--setup-only", "--app-dir", str(tmp_path), "--mirror", ""]) == 0
        assert fake_tk_app.instances == []
        assert (tmp_path / ".venv").is_dir()

    def test_setup_only_reports_the_environment(self, tmp_path, capsys):
        (tmp_path / "requirements.txt").write_text("# nothing to install\n")
        launcher.main(["--setup-only", "--app-dir", str(tmp_path), "--mirror", ""])
        out = capsys.readouterr().out
        assert "venv" in out and "essentials" in out

    def test_setup_only_without_requirements_fails(self, tmp_path, capsys):
        assert launcher.main(["--setup-only", "--app-dir", str(tmp_path), "--mirror", ""]) == 2
        assert "requirements" in capsys.readouterr().err.lower()


class TestPackagingInvariants:
    def test_launcher_uses_the_app_package(self):
        source = (Path(launcher.__file__)).read_text(encoding="utf-8")
        assert "from app.ui.views import DesktopApp" in source

    def test_main_module_is_runnable(self):
        import subprocess

        root = Path(launcher.__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "app.main", "--version"],
            cwd=str(root), capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0
        assert "GeoDataEngine Desktop" in result.stdout

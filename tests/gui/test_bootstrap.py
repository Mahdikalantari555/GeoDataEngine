"""Tests for ``app.core.bootstrap`` — first-run venv creation and upgrades."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from app.core import bootstrap
from app.core.bootstrap import (
    ESSENTIAL_MODULES,
    FULL_MODULES,
    BootstrapError,
    Bootstrapper,
    full_mode_available,
    is_noise,
    resolve_base_python,
)


class RecordingRunner:
    """Records commands and optionally simulates failures / venv creation."""

    def __init__(self, exit_code=0, create_venv_files=False, pip_exit_code=None):
        self.commands: list[list[str]] = []
        self.lines: list[str] = []
        self.exit_code = exit_code
        self.create_venv_files = create_venv_files
        self.pip_exit_code = pip_exit_code
        self.on_command = None

    def __call__(self, args, on_line=None):
        self.commands.append([str(a) for a in args])
        if on_line:
            on_line("collecting packages")
            on_line("installing packages")
        if self.on_command:
            self.on_command(args)
        if self.create_venv_files and "venv" in args:
            venv_dir = Path(args[args.index("venv") + 1])
            python = venv_dir / "bin" / "python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("#!/bin/sh\n", encoding="utf-8")
        if self.pip_exit_code is not None and "pip" in args:
            return self.pip_exit_code
        return self.exit_code


class Probe:
    def __init__(self, missing=()):
        self.missing = set(missing)
        self.checked: list[str] = []

    def __call__(self, module):
        self.checked.append(module)
        return module not in self.missing


def make_bootstrapper(tmp_path, runner, probe, base_python="/usr/bin/python3", venv=False):
    from app.core.config import ConfigStore

    app_root = tmp_path / "appdir"
    app_root.mkdir(parents=True, exist_ok=True)
    for name in ("requirements.txt", "requirements-full.txt"):
        (app_root / name).write_text("numpy\n", encoding="utf-8")
    store = ConfigStore(app_root)
    boot = Bootstrapper(
        store, app_root=app_root, runner=runner, probe=probe, base_python=base_python
    )
    if venv:
        boot.env_python.parent.mkdir(parents=True, exist_ok=True)
        boot.env_python.write_text("#!/bin/sh\n", encoding="utf-8")
    return boot


class TestStatus:
    def test_missing_venv_reports_not_created(self, tmp_path):
        status = make_bootstrapper(tmp_path, RecordingRunner(), Probe()).status()
        assert status.venv_exists is False
        assert status.label == "Environment: not created"

    def test_lite_status(self, tmp_path):
        boot = make_bootstrapper(tmp_path, RecordingRunner(), Probe(missing=FULL_MODULES), venv=True)
        status = boot.status()
        assert status.essentials_ready is True
        assert status.full_ready is False
        assert status.label == "Environment: Lite"

    def test_full_status(self, tmp_path):
        boot = make_bootstrapper(tmp_path, RecordingRunner(), Probe(), venv=True)
        status = boot.status()
        assert status.full_ready is True
        assert status.label == "Environment: Full"

    def test_incomplete_status(self, tmp_path):
        boot = make_bootstrapper(tmp_path, RecordingRunner(), Probe(missing=["numpy"]), venv=True)
        status = boot.status()
        assert status.essentials_ready is False
        assert status.missing_essentials == ["numpy"]
        assert status.label == "Environment: incomplete"

    def test_status_serialization(self, tmp_path):
        payload = make_bootstrapper(tmp_path, RecordingRunner(), Probe()).status().as_dict()
        for key in ("venv_dir", "venv_exists", "essentials_ready", "full_ready", "mode", "label"):
            assert key in payload

    def test_missing_modules_order_is_stable(self, tmp_path):
        probe = Probe(missing=ESSENTIAL_MODULES[1:3])
        boot = make_bootstrapper(tmp_path, RecordingRunner(), probe)
        assert boot.missing_modules() == list(ESSENTIAL_MODULES[1:3])

    def test_needs_bootstrap(self, tmp_path):
        assert make_bootstrapper(tmp_path, RecordingRunner(), Probe()).needs_bootstrap()
        complete = make_bootstrapper(tmp_path, RecordingRunner(), Probe(), venv=True)
        assert complete.venv_exists() is True
        assert complete.needs_bootstrap() is False


class TestCreateVenv:
    def test_creates_venv_when_missing(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True)
        boot = make_bootstrapper(tmp_path, runner, Probe())
        python = boot.create_venv()
        assert runner.commands[0] == ["/usr/bin/python3", "-m", "venv", str(boot.venv_dir)]
        assert python.exists()

    def test_second_call_is_a_no_op(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True)
        boot = make_bootstrapper(tmp_path, runner, Probe())
        boot.create_venv()
        boot.create_venv()
        venv_commands = [c for c in runner.commands if "venv" in c]
        assert len(venv_commands) == 1

    def test_failed_creation_raises(self, tmp_path):
        boot = make_bootstrapper(tmp_path, RecordingRunner(exit_code=1), Probe())
        with pytest.raises(BootstrapError, match="Could not create"):
            boot.create_venv()

    def test_creation_runs_even_when_interpreter_file_is_simulated(self, tmp_path):
        """A runner that does not create files is an error, not a silent success."""
        boot = make_bootstrapper(tmp_path, RecordingRunner(), Probe())
        with pytest.raises(BootstrapError):
            boot.create_venv()

    def test_progress_is_logged(self, tmp_path):
        messages = []
        boot = make_bootstrapper(tmp_path, RecordingRunner(create_venv_files=True), Probe())
        boot.create_venv(messages.append)
        assert any("Creating virtual environment" in message for message in messages)
        assert any("Virtual environment created" in message for message in messages)


class TestInstallEssentials:
    def test_installs_with_tuna_mirror_by_default(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True)
        boot = make_bootstrapper(tmp_path, runner, Probe(missing=["numpy"]))
        boot.install_essentials()
        install = runner.commands[-1]
        assert "--index-url" in install
        assert "https://mirror-pypi.runflare.com/simple" in install
        assert "--trusted-host" in install
        assert install[install.index("--trusted-host") + 1] == "mirror-pypi.runflare.com"
        assert "-r" in install
        assert install[-1].endswith("requirements.txt")

    def test_custom_mirror(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True)
        boot = make_bootstrapper(tmp_path, runner, Probe(missing=["numpy"]))
        boot.install_essentials("https://pypi.org/simple")
        install = runner.commands[-1]
        assert "https://pypi.org/simple" in install
        assert install[install.index("--trusted-host") + 1] == "pypi.org"

    def test_empty_mirror_omits_index_url(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True)
        boot = make_bootstrapper(tmp_path, runner, Probe(missing=["numpy"]))
        boot.install_essentials(None)
        assert "--index-url" not in runner.commands[-1]

    def test_skips_when_everything_is_importable(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True)
        boot = make_bootstrapper(tmp_path, runner, Probe())
        boot.venv_dir.mkdir(parents=True, exist_ok=True)
        boot.env_python.parent.mkdir(parents=True, exist_ok=True)
        boot.env_python.write_text("#!/bin/sh\n")
        code = boot.install_essentials()
        assert code == 0
        assert runner.commands == []

    def test_force_reinstalls(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True)
        boot = make_bootstrapper(tmp_path, runner, Probe())
        boot.install_essentials(force=True)
        assert any("pip" in command for command in runner.commands)

    def test_failure_raises(self, tmp_path):
        boot = make_bootstrapper(
            tmp_path, RecordingRunner(exit_code=2, create_venv_files=True), Probe(missing=["numpy"])
        )
        with pytest.raises(BootstrapError, match="exit code 2"):
            boot.install_essentials()

    def test_missing_requirements_file(self, tmp_path):
        boot = make_bootstrapper(tmp_path, RecordingRunner(), Probe(missing=["numpy"]))
        boot.requirements_path().unlink()
        with pytest.raises(BootstrapError, match="Missing requirements file"):
            boot.install_essentials()

    def test_setup_output_is_streamed(self, tmp_path):
        messages = []
        boot = make_bootstrapper(
            tmp_path, RecordingRunner(create_venv_files=True), Probe(missing=["numpy"])
        )
        boot.install_essentials(progress=messages.append)
        assert "collecting packages" in messages
        assert "installing packages" in messages


class TestInstallFull:
    def test_installs_full_requirements_and_switches_mode(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True)
        boot = make_bootstrapper(tmp_path, runner, Probe(missing=FULL_MODULES))
        boot.venv_dir.mkdir(parents=True, exist_ok=True)
        boot.env_python.parent.mkdir(parents=True, exist_ok=True)
        boot.env_python.write_text("#!/bin/sh\n")

        boot.install_full()

        assert any("requirements-full.txt" in " ".join(command) for command in runner.commands)
        assert boot.store.load().mode == "full"

    def test_installs_essentials_first_when_missing(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True)
        boot = make_bootstrapper(tmp_path, runner, Probe(missing=list(ESSENTIAL_MODULES) + ["scipy"]))
        boot.install_full()
        joined = [" ".join(command) for command in runner.commands]
        essentials = next(i for i, command in enumerate(joined) if "requirements.txt" in command)
        full = next(i for i, command in enumerate(joined) if "requirements-full.txt" in command)
        assert essentials < full

    def test_failure_keeps_mode_lite(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True, pip_exit_code=1)
        boot = make_bootstrapper(tmp_path, runner, Probe(missing=["scipy"]))
        with pytest.raises(BootstrapError, match="full stack failed"):
            boot.install_full()
        assert boot.store.load().mode == "lite"

    def test_failure_message_says_retry(self, tmp_path):
        runner = RecordingRunner(create_venv_files=True, pip_exit_code=1)
        boot = make_bootstrapper(tmp_path, runner, Probe(missing=["scipy"]))
        with pytest.raises(BootstrapError) as excinfo:
            boot.install_full()
        assert "again" in str(excinfo.value)

    def test_requires_full_requirements_file(self, tmp_path):
        boot = make_bootstrapper(tmp_path, RecordingRunner(), Probe())
        boot.requirements_path(full=True).unlink()
        with pytest.raises(BootstrapError, match="Missing requirements file"):
            boot.install_full()


class TestEnsureReady:
    def test_returns_status_after_install(self, tmp_path):
        boot = make_bootstrapper(
            tmp_path, RecordingRunner(create_venv_files=True), Probe(missing=["numpy"])
        )
        status = boot.ensure_ready()
        assert status.venv_exists is True

    def test_propagates_failures(self, tmp_path):
        boot = make_bootstrapper(tmp_path, RecordingRunner(exit_code=1), Probe(missing=["numpy"]))
        with pytest.raises(BootstrapError):
            boot.ensure_ready()


class TestRequirementsFiles:
    def test_essentials_file_lists_lite_stack(self, tmp_path):
        root = Path(__file__).resolve().parents[2] / "app"
        content = (root / "requirements.txt").read_text(encoding="utf-8").lower()
        for package in ("numpy", "rasterio", "requests", "pyproj", "shapely",
                        "pystac-client", "planetary-computer", "pyshp"):
            assert package in content, package
        for heavy in ("scipy", "pandas", "xarray", "geopandas", "matplotlib"):
            assert heavy not in content.split("#")[0] or heavy not in content

    def test_full_file_includes_essentials_and_heavy_stack(self):
        root = Path(__file__).resolve().parents[2] / "app"
        content = (root / "requirements-full.txt").read_text(encoding="utf-8")
        assert "-r requirements.txt" in content
        for package in ("scipy", "pandas", "xarray", "rioxarray", "geopandas", "matplotlib"):
            assert package in content

    def test_requirement_names_cover_the_probed_modules(self):
        """Every probed import name maps to something we actually install."""
        root = Path(__file__).resolve().parents[2] / "app"
        essentials = (root / "requirements.txt").read_text(encoding="utf-8").lower()
        aliases = {"pystac_client": "pystac-client", "planetary_computer": "planetary-computer",
                   "shapefile": "pyshp"}
        for module in ESSENTIAL_MODULES:
            package = aliases.get(module, module)
            assert package in essentials, f"{module} ({package}) missing from requirements.txt"

    def test_requirements_lookup_for_frozen_build(self, tmp_path, monkeypatch):
        boot = make_bootstrapper(tmp_path, RecordingRunner(), Probe())
        monkeypatch.setattr(sys, "_MEIPASS", str(boot.app_root), raising=False)
        assert boot.requirements_path().is_file()


class TestInterpreterResolution:
    def test_explicit_base_python_wins(self, tmp_path):
        boot = make_bootstrapper(tmp_path, RecordingRunner(), Probe(), base_python="/custom/python")
        assert boot.interpreter() == "/custom/python"

    def test_env_var_override(self, tmp_path, monkeypatch):
        interpreter = tmp_path / "portable-python"
        interpreter.write_text("#!/bin/sh\n")
        monkeypatch.setenv("GEODATAENGINE_PYTHON", str(interpreter))
        assert resolve_base_python(tmp_path) == str(interpreter)

    def test_env_var_pointing_nowhere_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GEODATAENGINE_PYTHON", str(tmp_path / "missing"))
        with pytest.raises(BootstrapError, match="missing interpreter"):
            resolve_base_python(tmp_path)

    def test_portable_python_folder(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GEODATAENGINE_PYTHON", raising=False)
        portable = tmp_path / "python" / "python"
        portable.parent.mkdir(parents=True)
        portable.write_text("#!/bin/sh\n")
        assert resolve_base_python(tmp_path) == str(portable)

    def test_source_run_falls_back_to_sys_executable(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GEODATAENGINE_PYTHON", raising=False)
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert resolve_base_python(tmp_path) == sys.executable


class TestHelpers:
    def test_is_noise_filters_pip_deprecations(self):
        assert is_noise("DEPRECATION: something old")
        assert is_noise("  WARNING: mirror is slow")
        assert not is_noise("Successfully installed numpy-2.0.0")

    def test_full_mode_available(self):
        assert full_mode_available(lambda module: True) is True
        assert full_mode_available(lambda module: module != "scipy") is False

    def test_default_probe_reports_stdlib(self):
        assert bootstrap.default_probe("json") is True
        assert bootstrap.default_probe("definitely_not_a_module_xyz") is False

    def test_run_command_streams_output(self):
        lines = []
        code = bootstrap.run_command(
            [sys.executable, "-c", "print('hello'); print('world')"], lines.append
        )
        assert code == 0
        assert lines == ["hello", "world"]

    def test_run_command_missing_binary(self):
        with pytest.raises(BootstrapError, match="Cannot start"):
            bootstrap.run_command(["/definitely/not/a/binary"])

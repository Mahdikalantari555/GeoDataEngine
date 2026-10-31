"""Architecture and packaging guards for the desktop app.

These tests protect the invariants the design depends on:

* ``app.core`` never imports ``tkinter`` or the heavy scientific stack, so the
  whole layer is testable and the GUI starts without METRIC dependencies;
* the views only use the toolkit API both implementations provide;
* the launcher, spec and requirements files stay consistent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"
HEAVY_MODULES = (
    "scipy",
    "pandas",
    "xarray",
    "rioxarray",
    "geopandas",
    "fiona",
    "matplotlib",
    "cartopy",
    "sklearn",
)


def run_python(code: str, *, blocked: tuple[str, ...] = (), cwd: Path = REPO_ROOT):
    """Run ``code`` in a subprocess with selected modules made unimportable."""
    prelude = ""
    if blocked:
        prelude = (
            "import sys\n"
            "class _Blocker:\n"
            "    def find_module(self, name, path=None):\n"
            f"        return self if name.split('.')[0] in {blocked!r} else None\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            f"        if name.split('.')[0] in {blocked!r}:\n"
            "            raise ImportError('blocked: ' + name)\n"
            "        return None\n"
            "sys.meta_path.insert(0, _Blocker())\n"
        )
    return subprocess.run(
        [sys.executable, "-c", prelude + code],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )


class TestCoreIsDependencyLight:
    def test_core_imports_without_tkinter(self):
        code = (
            "import app.core.bootstrap, app.core.catalog, app.core.config, "
            "app.core.indices, app.core.layout, app.core.presets, app.core.roi, "
            "app.core.session, app.core.workers\n"
            "import sys\n"
            "assert 'tkinter' not in sys.modules, 'core imported tkinter'\n"
            "print('ok')\n"
        )
        result = run_python(code, blocked=("tkinter",))
        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout

    def test_core_imports_without_the_heavy_stack(self):
        code = (
            "import app.core.session, app.core.indices, app.core.presets\n"
            "import sys\n"
            f"heavy = [m for m in {HEAVY_MODULES!r} if m in sys.modules]\n"
            "assert not heavy, heavy\n"
            "print('ok')\n"
        )
        result = run_python(code, blocked=HEAVY_MODULES)
        assert result.returncode == 0, result.stderr

    def test_help_text_is_importable_without_heavy_deps(self):
        result = run_python(
            "from app.help_text import build_help_text; print(len(build_help_text()))",
            blocked=HEAVY_MODULES + ("tkinter",),
        )
        assert result.returncode == 0, result.stderr
        assert int(result.stdout.strip()) > 1000

    def test_ui_package_does_not_import_tkinter_eagerly(self):
        result = run_python(
            "import app.ui.views, app.ui.fake, app.ui.toolkit\n"
            "import sys\n"
            "assert 'tkinter' not in sys.modules\n"
            "print('ok')",
            blocked=("tkinter",),
        )
        assert result.returncode == 0, result.stderr

    def test_get_toolkit_reports_missing_tkinter_clearly(self):
        code = (
            "from app.ui.toolkit import get_toolkit\n"
            "try:\n"
            "    get_toolkit()\n"
            "except RuntimeError as exc:\n"
            "    assert 'Tkinter is not available' in str(exc), exc\n"
            "    print('ok')\n"
        )
        result = run_python(code, blocked=("tkinter",))
        assert result.returncode == 0, result.stderr


class TestSourceLayout:
    def test_app_package_files_exist(self):
        for name in (
            "__init__.py",
            "main.py",
            "help_text.py",
            "requirements.txt",
            "requirements-full.txt",
            "GeoDataEngine.spec",
        ):
            assert (APP_DIR / name).is_file(), name

    def test_core_modules_exist(self):
        expected = {
            "__init__.py",
            "bootstrap.py",
            "catalog.py",
            "config.py",
            "indices.py",
            "layout.py",
            "presets.py",
            "roi.py",
            "session.py",
            "workers.py",
        }
        assert expected <= {path.name for path in (APP_DIR / "core").iterdir()}

    def test_ui_modules_exist(self):
        expected = {"__init__.py", "fake.py", "tk_toolkit.py", "toolkit.py", "views.py"}
        assert expected <= {path.name for path in (APP_DIR / "ui").iterdir()}

    def test_launchers_exist(self):
        assert (REPO_ROOT / "main.py").is_file()
        assert (REPO_ROOT / "main.pyw").is_file()

    def test_engine_is_on_the_path_after_import(self):
        import app

        assert str(app.SRC_DIR) in sys.path or app.ensure_engine_on_path() is None


class TestToolkitContract:
    """The views must only rely on the widget API the fake implements."""

    def test_fake_and_tk_toolkit_expose_the_same_factories(self):
        from app.ui.fake import FakeToolkit
        from app.ui.toolkit import Toolkit

        required = [name for name in dir(Toolkit) if not name.startswith("_")]
        for name in required:
            assert hasattr(FakeToolkit, name), f"FakeToolkit lacks {name}"

    def test_tk_toolkit_module_declares_the_same_factories(self):
        source = (APP_DIR / "ui" / "tk_toolkit.py").read_text(encoding="utf-8")
        for name in (
            "Frame",
            "Label",
            "Button",
            "Entry",
            "Checkbutton",
            "Combobox",
            "Listbox",
            "Treeview",
            "Progressbar",
            "Text",
            "LabelFrame",
            "Scale",
        ):
            assert f"def {name}(" in source, name

    def test_views_are_built_only_through_the_toolkit(self):
        source = (APP_DIR / "ui" / "views.py").read_text(encoding="utf-8")
        assert "import tkinter" not in source
        assert "from tkinter" not in source

    def test_fake_toolkit_records_creation(self):
        from app.ui.fake import FakeToolkit

        toolkit = FakeToolkit()
        frame = toolkit.Frame()
        toolkit.Label(frame, text="hi")
        assert len(toolkit.created) == 2
        assert frame.winfo_children()

    def test_fake_notebook_tracks_tabs(self):
        from app.ui.fake import FakeToolkit

        toolkit = FakeToolkit()
        notebook = toolkit.Notebook()
        tab = toolkit.Frame()
        notebook.add(tab, text="Search")
        assert notebook.tab_titles() == ["Search"]
        assert notebook.tabs() == (tab,)

    def test_fake_treeview_selection_api(self):
        from app.ui.fake import FakeToolkit

        tree = FakeToolkit().Treeview(columns=("a", "b"))
        tree.insert("", "end", iid="X", values=("1", "2"))
        tree.selection_set("X")
        assert tree.selection() == ("X",)
        tree.selection_remove("X")
        assert tree.selection() == ()
        assert tree.values_of("X") == ("1", "2")


class TestPackagingSpec:
    def test_spec_references_entry_point_and_requirements(self):
        spec = (APP_DIR / "GeoDataEngine.spec").read_text(encoding="utf-8")
        assert "main.py" in spec
        assert "requirements.txt" in spec
        assert "requirements-full.txt" in spec
        assert "COLLECT(" in spec

    def test_spec_excludes_the_heavy_stack(self):
        spec = (APP_DIR / "GeoDataEngine.spec").read_text(encoding="utf-8")
        excludes_block = spec.split("excludes=[", 1)[1].split("]", 1)[0]
        for module in ("scipy", "pandas", "xarray", "geopandas", "matplotlib"):
            assert f'"{module}"' in excludes_block

    def test_spec_bundles_the_lite_engine_modules(self):
        spec = (APP_DIR / "GeoDataEngine.spec").read_text(encoding="utf-8")
        assert "data_engine.io.planetary_computer_fetcher" in spec
        assert "data_engine._vendor.geospatial_core.spectral" in spec
        assert "tkinter" in spec

    def test_spec_is_importable_python(self):
        source = (APP_DIR / "GeoDataEngine.spec").read_text(encoding="utf-8")
        compile(source, "GeoDataEngine.spec", "exec")


class TestLauncher:
    def test_parse_args_defaults(self):
        from app.main import parse_args

        args = parse_args([])
        assert args.no_bootstrap is False
        assert args.setup_only is False
        assert args.app_dir is None
        assert args.mirror is None

    def test_parse_args_flags(self):
        from app.main import parse_args

        args = parse_args(["--no-bootstrap", "--setup-only", "--app-dir", "/tmp/x"])
        assert args.no_bootstrap is True
        assert args.setup_only is True
        assert args.app_dir == "/tmp/x"

    def test_version_exit_code(self, capsys):
        from app.main import EXIT_OK, main

        assert main(["--version"]) == EXIT_OK
        assert "GeoDataEngine Desktop" in capsys.readouterr().out

    def test_bootstrap_report_lists_the_essentials(self, bootstrapper):
        from app.main import bootstrap_report

        report = bootstrap_report(bootstrapper.status())
        assert "venv" in report
        assert "essentials" in report
        assert "mode" in report

    def test_module_entry_point_prints_version(self):
        result = subprocess.run(
            [sys.executable, "-m", "app.main", "--version"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        assert "GeoDataEngine Desktop" in result.stdout

    def test_main_script_entry_point(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--version"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        assert "GeoDataEngine Desktop" in result.stdout

    def test_no_tk_exit_code_when_tkinter_is_missing(self, tmp_path):
        """Without Tk the launcher exits with a clear code instead of crashing."""
        code = (
            "import sys\n"
            "class _Blocker:\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name.split('.')[0] == 'tkinter':\n"
            "            raise ImportError('blocked')\n"
            "        return None\n"
            "sys.meta_path.insert(0, _Blocker())\n"
            "from app.main import main, EXIT_NO_TK\n"
            f"sys.exit(main(['--no-bootstrap', '--app-dir', {str(tmp_path)!r}]))\n"
        )
        result = run_python(code)
        assert result.returncode == 3, (result.returncode, result.stderr)
        assert "Tkinter is not available" in result.stderr

    def test_setup_only_creates_the_environment(self, tmp_path):
        """``--setup-only`` builds .venv and reports; it never starts the GUI."""
        from app.main import main

        requirements = tmp_path / "requirements.txt"
        requirements.write_text("# no packages: keeps the test fast\n", encoding="utf-8")
        result = main(["--setup-only", "--app-dir", str(tmp_path), "--mirror", ""])
        assert result == 0
        assert (tmp_path / ".venv").exists()
        assert (tmp_path / "config.json").exists() or requirements.exists()

    def test_setup_only_reports_missing_requirements(self, tmp_path, capsys):
        from app.main import EXIT_ENV, main

        assert main(["--setup-only", "--app-dir", str(tmp_path), "--mirror", ""]) == EXIT_ENV
        assert "requirements" in capsys.readouterr().err.lower()


class TestFixtureHygiene:
    def test_tests_do_not_touch_the_real_app_directory(self, session, tmp_path):
        assert session.store.directory != APP_DIR
        assert session.store.directory.is_relative_to(tmp_path)

    def test_sample_roi_is_still_usable(self):
        from app.core.roi import load_roi

        sample = REPO_ROOT / "sample" / "sample.geojson"
        if not sample.is_file():  # pragma: no cover
            pytest.skip("sample missing")
        assert load_roi(sample).feature_count >= 1

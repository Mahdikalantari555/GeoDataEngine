"""Self-bootstrapping virtual environment.

On first run the app creates ``.venv`` next to itself, installs the essentials
from ``requirements.txt`` (Tuna mirror by default) and then re-launches inside
that environment.  "Enable full processing" upgrades the *same* environment
with ``requirements-full.txt``.

All heavy lifting is delegated to :class:`SubprocessRunner`, which is trivially
replaceable in tests, and to :class:`ImportProbe`, which answers "are the
essentials / heavy packages importable here?" without importing them for real.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .config import DEFAULT_MIRROR_URL, AppConfig, ConfigStore, venv_python

ESSENTIALS_REQUIREMENTS = "requirements.txt"
FULL_REQUIREMENTS = "requirements-full.txt"

#: Packages the light stack must be able to import.
ESSENTIAL_MODULES: tuple[str, ...] = (
    "numpy",
    "rasterio",
    "requests",
    "pyproj",
    "shapely",
    "pystac_client",
    "planetary_computer",
    "tenacity",
    "loguru",
    "shapefile",
)

#: Packages only needed for METRIC presets.
#:
#: The essentials stop at what searching the catalog and clipping bands with
#: rasterio needs.  ``stackstac`` (Landsat band stacking) and the METRIC
#: pipeline's scientific/plotting stack only arrive with full processing.
FULL_MODULES: tuple[str, ...] = (
    "stackstac",
    "xarray",
    "pandas",
    "scipy",
    "matplotlib",
    "rioxarray",
    "geopandas",
    "fiona",
    "click",
    "yaml",
    "tqdm",
)

LogCallback = Callable[[str], None]


class BootstrapError(RuntimeError):
    """Raised when the environment cannot be prepared."""


class CommandRunner(Protocol):
    """Minimal subprocess surface used by the bootstrapper."""

    def __call__(
        self, args: Sequence[str], on_line: LogCallback | None = None
    ) -> int: ...


class ImportProbe(Protocol):
    """Answer whether a module is importable."""

    def __call__(self, module: str) -> bool: ...


def default_probe(module: str) -> bool:
    """Import ``module`` (cached by Python) and report success."""
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def run_command(args: Sequence[str], on_line: LogCallback | None = None) -> int:
    """Run a command, streaming its output line by line to ``on_line``."""
    args = [str(a) for a in args]
    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise BootstrapError(f"Cannot start {' '.join(args)}: {exc}") from exc

    assert process.stdout is not None
    for line in process.stdout:
        if on_line:
            on_line(line.rstrip())
    return process.wait()


PIP_DEPRECATION = re.compile(r"^\s*(DEPRECATION|WARNING):", re.IGNORECASE)


def is_noise(line: str) -> bool:
    """Pip chatter that should not clutter the GUI log."""
    return bool(PIP_DEPRECATION.match(line))


@dataclass
class BootstrapStatus:
    """Everything the Settings tab needs to describe the environment."""

    venv_dir: Path
    env_python: Path
    venv_exists: bool
    essentials_ready: bool
    full_ready: bool
    mode: str
    missing_essentials: list[str] = field(default_factory=list)
    missing_full: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        """One-line environment description for the status bar and Settings tab."""
        if not self.venv_exists:
            return "Environment: not created"
        if not self.essentials_ready:
            return "Environment: incomplete"
        if self.full_ready:
            return "Environment: Full"
        return "Environment: Lite"

    def as_dict(self) -> dict[str, object]:
        return {
            "venv_dir": str(self.venv_dir),
            "venv_exists": self.venv_exists,
            "essentials_ready": self.essentials_ready,
            "full_ready": self.full_ready,
            "mode": self.mode,
            "label": self.label,
            "missing_essentials": list(self.missing_essentials),
            "missing_full": list(self.missing_full),
        }


class Bootstrapper:
    """Create and upgrade the application virtual environment."""

    def __init__(
        self,
        store: ConfigStore | None = None,
        *,
        app_root: Path | str | None = None,
        runner: CommandRunner | None = None,
        probe: ImportProbe | None = None,
        base_python: str | Path | None = None,
    ) -> None:
        self.store = store or ConfigStore(app_root)
        self.app_root = Path(app_root) if app_root is not None else self.store.directory
        self.runner: CommandRunner = runner or run_command
        self.probe: ImportProbe = probe or default_probe
        self.base_python = str(base_python) if base_python else ""

    # ------------------------------------------------------------------
    # Paths and status
    # ------------------------------------------------------------------
    def interpreter(self) -> str:
        """The Python used to create the virtual environment.

        A PyInstaller executable is not a Python interpreter, so packaged
        builds either ship a portable interpreter in ``<app>/python`` or point
        ``GEODATAENGINE_PYTHON`` at one.
        """
        if self.base_python:
            return self.base_python
        resolved = resolve_base_python(self.app_root)
        self.base_python = resolved
        return resolved

    @property
    def venv_dir(self) -> Path:
        return self.store.venv_dir()

    @property
    def env_python(self) -> Path:
        return venv_python(self.venv_dir)

    def requirements_path(self, full: bool = False) -> Path:
        """Locate a requirements file in a source checkout or a frozen build."""
        name = FULL_REQUIREMENTS if full else ESSENTIALS_REQUIREMENTS
        candidates = [self.app_root / name]
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            candidates.append(Path(bundle) / name)
            candidates.append(Path(bundle) / "app" / name)
        candidates.extend([self.app_root / "app" / name, self.app_root / "_internal" / name])
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]

    def missing_modules(self, full: bool = False) -> list[str]:
        modules: Iterable[str] = FULL_MODULES if full else ESSENTIAL_MODULES
        return [module for module in modules if not self.probe(module)]

    def venv_exists(self) -> bool:
        return self.env_python.exists()

    def status(self, config: AppConfig | None = None) -> BootstrapStatus:
        """Inspect the environment without modifying it."""
        cfg = config or self.store.load()
        missing_essentials = self.missing_modules()
        missing_full = self.missing_modules(full=True)
        exists = self.venv_exists()
        return BootstrapStatus(
            venv_dir=self.venv_dir,
            env_python=self.env_python,
            venv_exists=exists,
            essentials_ready=not missing_essentials,
            full_ready=not missing_full,
            mode=cfg.mode,
            missing_essentials=missing_essentials,
            missing_full=missing_full,
        )

    # ------------------------------------------------------------------
    # Creation / upgrade
    # ------------------------------------------------------------------
    def build_install_command(self, requirements: Path, mirror_url: str | None) -> list[str]:
        """Arguments used to install a requirements file into the venv."""
        if not mirror_url:
            return [
                str(self.env_python),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--disable-pip-version-check",
                "--no-input",
                "-r",
                str(requirements),
            ]
        return [
            str(self.env_python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--disable-pip-version-check",
            "--no-input",
            "--index-url",
            mirror_url,
            "--trusted-host",
            _host_of(mirror_url),
            "-r",
            str(requirements),
        ]

    def create_venv(self, progress: LogCallback | None = None) -> Path:
        """Create the virtual environment if it is missing."""
        if self.venv_exists():
            self._log(progress, f"Virtual environment already present: {self.venv_dir}")
            return self.env_python

        self.venv_dir.parent.mkdir(parents=True, exist_ok=True)
        self._log(progress, f"Creating virtual environment in {self.venv_dir}")
        code = self.runner(
            [self.interpreter(), "-m", "venv", str(self.venv_dir)],
            lambda line: self._log(progress, line),
        )
        if code != 0 or not self.env_python.exists():
            raise BootstrapError(
                f"Could not create the virtual environment (exit code {code}). "
                "Check that Python's venv module is available."
            )
        self._log(progress, "Virtual environment created")
        return self.env_python

    def install_essentials(
        self,
        mirror_url: str | None = DEFAULT_MIRROR_URL,
        progress: LogCallback | None = None,
        *,
        force: bool = False,
    ) -> int:
        """Install ``requirements.txt`` into the venv (idempotent)."""
        requirements = self.requirements_path()
        if not requirements.is_file():
            raise BootstrapError(f"Missing requirements file: {requirements}")
        self.create_venv(progress)

        if not force and not self.missing_modules():
            self._log(progress, "Essentials already installed — skipping")
            return 0

        self._log(progress, f"Installing essentials from {_describe_mirror(mirror_url)}")
        code = self.runner(
            self.build_install_command(requirements, mirror_url),
            lambda line: self._log(progress, line),
        )
        if code != 0:
            raise BootstrapError(f"Installing essentials failed (exit code {code})")
        return code

    def install_full(
        self,
        mirror_url: str | None = DEFAULT_MIRROR_URL,
        progress: LogCallback | None = None,
        *,
        config: AppConfig | None = None,
    ) -> int:
        """Install ``requirements-full.txt`` and switch the config to full mode."""
        requirements = self.requirements_path(full=True)
        if not requirements.is_file():
            raise BootstrapError(f"Missing requirements file: {requirements}")
        self.create_venv(progress)
        # The heavy set builds on the essentials.
        if self.missing_modules():
            self.install_essentials(mirror_url, progress)

        self._log(progress, f"Installing full processing stack from {_describe_mirror(mirror_url)}")
        code = self.runner(
            self.build_install_command(requirements, mirror_url),
            lambda line: self._log(progress, line),
        )
        if code != 0:
            raise BootstrapError(
                f"Installing the full stack failed (exit code {code}). "
                "pip is idempotent — press the button again to resume."
            )

        cfg = config or self.store.load()
        cfg.mode = "full"
        self.store.save(cfg)
        self._log(progress, "Full processing enabled")
        return code

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _log(self, progress: LogCallback | None, message: str) -> None:
        if progress and message:
            progress(message)

    def needs_bootstrap(self) -> bool:
        """True when the app should prepare the environment before starting."""
        return not self.venv_exists() or bool(self.missing_modules())

    def ensure_ready(
        self,
        mirror_url: str | None = DEFAULT_MIRROR_URL,
        progress: LogCallback | None = None,
    ) -> BootstrapStatus:
        """Make sure the essentials are importable, installing when needed."""
        self.install_essentials(mirror_url, progress)
        return self.status()


def _host_of(url: str) -> str:
    """Extract the host part of a mirror URL for pip's ``--trusted-host``."""
    host = url.split("://", 1)[-1]
    host = host.split("/", 1)[0]
    return host.split("@")[-1]


def _describe_mirror(url: str | None) -> str:
    return "the default PyPI index" if not url else _host_of(url)


def resolve_base_python(app_root: Path | str) -> str:
    """Find a real Python interpreter able to create the ``.venv``.

    Order: ``GEODATAENGINE_PYTHON`` → ``<app>/python/python[.exe]`` →
    ``<app>/python/bin/python`` → the running interpreter (source runs).
    """
    env_value = os.environ.get("GEODATAENGINE_PYTHON")
    if env_value:
        candidate = Path(env_value)
        if candidate.exists():
            return str(candidate)
        raise BootstrapError(
            f"GEODATAENGINE_PYTHON points to a missing interpreter: {env_value}"
        )

    root = Path(app_root)
    names = ["python.exe", "python"] if os.name == "nt" else ["python", "python3"]
    for name in names:
        for directory in (root / "python", root / "python" / "bin", root):
            candidate = directory / name
            if candidate.is_file():
                return str(candidate)

    if not getattr(sys, "frozen", False):
        return sys.executable

    # Frozen build: fall back to any interpreter discoverable on PATH so a
    # system Python (e.g. the one the user already installed) can be used.
    import shutil

    for candidate_name in ("python.exe", "python3.exe", "python", "python3", "py"):
        found = shutil.which(candidate_name)
        if found:
            return found

    raise BootstrapError(
        "No Python interpreter available to create the virtual environment. "
        "Place a portable Python in the 'python' folder next to the application, "
        "add Python to PATH, or set GEODATAENGINE_PYTHON."
    )


def full_mode_available(probe: ImportProbe | None = None) -> bool:
    """Whether every heavy dependency is importable right now."""
    probe = probe or default_probe
    return all(probe(module) for module in FULL_MODULES)


__all__ = [
    "ESSENTIALS_REQUIREMENTS",
    "ESSENTIAL_MODULES",
    "FULL_MODULES",
    "FULL_REQUIREMENTS",
    "BootstrapError",
    "BootstrapStatus",
    "Bootstrapper",
    "CommandRunner",
    "ImportProbe",
    "default_probe",
    "full_mode_available",
    "resolve_base_python",
    "is_noise",
    "run_command",
]

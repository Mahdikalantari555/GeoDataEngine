"""Launcher entry point.

``python -m app.main`` (or ``python main.py`` from the portable folder):

1. load ``config.json``;
2. make sure the essentials are installed (first run creates ``.venv``);
3. re-launch inside that environment when the current interpreter lacks them;
4. build the Tkinter window and enter the event loop.

Exit codes: ``0`` success, ``2`` environment not ready, ``3`` Tkinter missing.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

# Allow "python app/main.py" as well as "python -m app.main".
if __package__ in (None, ""):  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.bootstrap import BootstrapError, Bootstrapper, BootstrapStatus  # noqa: E402
from app.core.config import AppConfig, ConfigStore  # noqa: E402
from app.core.session import Session  # noqa: E402

EXIT_OK = 0
EXIT_ENV = 2
EXIT_NO_TK = 3


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="geodataengine-gui",
        description="GeoDataEngine desktop GUI (STAC search, download, indices).",
    )
    parser.add_argument("--no-bootstrap", action="store_true",
                        help="skip the environment check and launch immediately")
    parser.add_argument("--setup-only", action="store_true",
                        help="only prepare the virtual environment, then exit")
    parser.add_argument("--app-dir", default=None,
                        help="folder holding config.json and .venv (default: app folder)")
    parser.add_argument("--mirror", default=None,
                        help="override the PyPI mirror URL for this run")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    return parser.parse_args(list(argv) if argv is not None else None)


def bootstrap_report(status: BootstrapStatus) -> str:
    lines = [
        f"venv        : {status.venv_dir}",
        f"interpreter : {status.env_python}",
        f"venv exists : {'yes' if status.venv_exists else 'no'}",
        f"essentials  : {'ready' if status.essentials_ready else 'missing ' + ', '.join(status.missing_essentials)}",
        f"full stack  : {'ready' if status.full_ready else 'missing ' + ', '.join(status.missing_full)}",
        f"mode        : {status.mode}",
    ]
    return "\n".join(lines)


def prepare_environment(
    store: ConfigStore,
    config: AppConfig,
    mirror: str | None,
    bootstrapper: Bootstrapper | None = None,
) -> Bootstrapper:
    """Create the venv and install essentials, echoing progress to the console."""
    bootstrapper = bootstrapper or Bootstrapper(store)
    bootstrapper.install_essentials(mirror or config.mirror_url, print)
    return bootstrapper


def main(
    argv: Sequence[str] | None = None,
    *,
    bootstrapper: Bootstrapper | None = None,
    store: ConfigStore | None = None,
) -> int:
    """Start the GUI (or prepare the environment with ``--setup-only``).

    ``bootstrapper`` and ``store`` are injectable so the launcher itself can be
    tested without touching a real virtual environment.
    """
    args = parse_args(argv)

    from app import __version__

    if args.version:
        print(f"GeoDataEngine Desktop {__version__}")
        return EXIT_OK

    store = store or ConfigStore(args.app_dir)
    config = store.load()
    bootstrapper = bootstrapper or Bootstrapper(
        store, app_root=Path(args.app_dir) if args.app_dir else None
    )

    status = bootstrapper.status(config)
    if args.setup_only:
        mirror = args.mirror or config.mirror_url
        try:
            bootstrapper.install_essentials(mirror, print)
        except BootstrapError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ENV
        print(bootstrap_report(bootstrapper.status(config)))
        return EXIT_OK

    if not args.no_bootstrap and not status.essentials_ready:
        print("Preparing the environment (first run installs dependencies)…")
        try:
            prepare_environment(store, config, args.mirror, bootstrapper)
        except BootstrapError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ENV
        status = bootstrapper.status(config)

    session = Session(store=store)
    try:
        from app.ui.views import DesktopApp

        app = DesktopApp(session=session, bootstrapper=bootstrapper)
    except RuntimeError as exc:  # tkinter missing
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_NO_TK

    try:
        app.run()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("interrupted", file=sys.stderr)
        return EXIT_ENV
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

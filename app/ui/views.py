"""Tkinter views: Search, Download, Indices, Settings, help and status bar.

The views hold widgets and user interaction only.  Every decision (which
scenes qualify, where products are written, what a preset contains) belongs to
:mod:`app.core`, reached through :class:`app.core.session.Session`.

``DesktopApp`` is constructed with:

``session``      the headless controller (real or fake in tests)
``bootstrapper`` the environment manager
``toolkit``      ``TkToolkit`` or ``FakeToolkit``
``prompter``     dialog callables (file pickers, message boxes)
``job_runner``   how work is dispatched (a ``BackgroundJob`` by default)
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..core import catalog
from ..core.bootstrap import Bootstrapper
from ..core.config import (
    BASIC_INDICES,
    PRESET_NAMES,
    SATELLITES,
    SENTINEL2,
    SENTINEL_ONLY_INDICES,
    SORT_OPTIONS,
    AppConfig,
)
from ..core.roi import ROIError
from ..core.session import Session
from ..core.workers import BackgroundJob, Emitter, JobEvent
from ..help_text import build_help_text
from .toolkit import get_toolkit

WINDOW_TITLE = "GeoDataEngine — Remote Sensing Desktop"
POLL_INTERVAL_MS = 120

LANDSAT_BANDS = "blue, green, red, nir08, swir16, swir22, lwir11, qa_pixel"
SENTINEL_BANDS = "blue (B02), green (B03), red (B04), nir08 (B08)"


# ---------------------------------------------------------------------------
# Prompting (dialogs injected so tests never block on a modal)
# ---------------------------------------------------------------------------
class ToolkitPrompter:
    """Dialog façade backed by the toolkit (file pickers + message boxes)."""

    def __init__(self, toolkit: Any) -> None:
        self.toolkit = toolkit

    def open_file(self, title: str = "Select a file", kind: str = "roi") -> str:
        if kind == "roi":
            return self.toolkit.ask_open_file(title=title) or ""
        if kind == "weather":
            return self.toolkit.ask_open_file(
                title=title,
                filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
            ) or ""
        return self.toolkit.ask_open_file(title=title) or ""

    def open_directory(self, title: str = "Select a folder") -> str:
        return self.toolkit.ask_directory(title=title) or ""

    def info(self, title: str, message: str) -> None:
        self.toolkit.show_info(title, message)

    def error(self, title: str, message: str) -> None:
        self.toolkit.show_error(title, message)

    def warning(self, title: str, message: str) -> None:
        self.toolkit.show_warning(title, message)

    def help(self, body: str) -> None:
        self.toolkit.show_text_dialog("GeoDataEngine help", body)


class SyncJobRunner:
    """Job runner that executes immediately (used by tests)."""

    def __call__(self, func: Callable[[Emitter], Any], name: str) -> BackgroundJob:
        job = BackgroundJob(func, name)
        job.run_sync()
        return job


def background_runner(func: Callable[[Emitter], Any], name: str) -> BackgroundJob:
    """Default job runner: a daemon thread polled through the Tk event loop."""
    return BackgroundJob(func, name).start()


# ---------------------------------------------------------------------------
# The application shell
# ---------------------------------------------------------------------------
class DesktopApp:
    """Owns the window, the four tabs and the shared progress/log widgets."""

    def __init__(
        self,
        session: Session | None = None,
        bootstrapper: Bootstrapper | None = None,
        *,
        toolkit: Any | None = None,
        prompter: Any | None = None,
        job_runner: Callable[[Callable[[Emitter], Any], str], BackgroundJob] | None = None,
    ) -> None:
        self.tk = get_toolkit(toolkit)
        self.session = session or Session()
        self.bootstrapper = bootstrapper or Bootstrapper(self.session.store)
        self.prompter = prompter or ToolkitPrompter(self.tk)
        self.job_runner = job_runner or background_runner

        self.root: Any = None
        self.notebook: Any = None
        self.busy = False
        self.current_job: BackgroundJob | None = None
        self.last_status = "Ready"
        self._on_result: Callable[[Any], None] | None = None

        # widget references
        self.roi_entry: Any = None
        self.roi_label: Any = None
        self.satellite_box: Any = None
        self.start_entry: Any = None
        self.end_entry: Any = None
        self.cloud_entry: Any = None
        self.coverage_entry: Any = None
        self.sort_box: Any = None
        self.results_tree: Any = None
        self.selection_label: Any = None
        self.search_button: Any = None
        self.download_button: Any = None
        self.cancel_button: Any = None
        self.output_entry: Any = None
        self.bands_label: Any = None
        self.log_text: Any = None
        self.scene_listbox: Any = None
        self.index_vars: dict[str, Any] = {}
        self.index_checks: dict[str, Any] = {}
        self.preset_box: Any = None
        self.full_hint_label: Any = None
        self.progress_bar: Any = None
        self.progress_label: Any = None
        self.status_label: Any = None
        self.mirror_entry: Any = None
        self.crs_entry: Any = None
        self.env_label: Any = None
        self.enable_full_button: Any = None
        self.indices_log: Any = None
        self.product_label: Any = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def build(self) -> DesktopApp:
        """Create every widget (call before :meth:`mainloop`)."""
        self.root = self._build_root()
        self._build_menubar()
        self.notebook = self.tk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self._build_search_tab(self.notebook)
        self._build_download_tab(self.notebook)
        self._build_indices_tab(self.notebook)
        self._build_settings_tab(self.notebook)

        self._build_status_bar(self.root)
        self._load_config_into_widgets()
        self.refresh_scene_list()
        self.refresh_env_status()
        self.log("GeoDataEngine ready.")
        self.set_status(self.session.status_line("Ready"))
        return self

    def _build_root(self) -> Any:
        root = self.tk.root if hasattr(self.tk, "root") else None
        if root is None:
            root = self.tk.Frame()
        try:
            root.title(WINDOW_TITLE)
            root.geometry("1080x760")
        except Exception:  # FakeToolkit frames have no window methods
            pass
        return root

    def _build_menubar(self) -> None:
        menu = self.tk.Menu() if hasattr(self.tk, "Menu") else None
        if menu is None:  # toolkit without menus (fake) — Help button still works
            return
        menu.add_command(label="Help", command=self.open_help)
        if not getattr(sys, "frozen", False):
            menu.add_command(label="Enable full processing", command=self.enable_full_processing)
        with contextlib.suppress(Exception):  # pragma: no cover - window without a menu
            self.root.configure(menu=getattr(menu, "widget", menu))

    # -- Search tab ----------------------------------------------------
    def _build_search_tab(self, master: Any) -> None:
        tab = self.tk.Frame(master)
        tab.pack(fill="both", expand=True)
        if hasattr(self.notebook, "add"):
            self.notebook.add(getattr(tab, "widget", tab), text="Search")
        self.search_tab = tab

        form = self.tk.LabelFrame(tab, text="Search criteria")
        form.pack(fill="x", padx=10, pady=(10, 6))

        self.tk.Label(form, text="ROI file (GeoJSON / Shapefile)").grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        self.roi_entry = self.tk.Entry(form, width=62)
        self.roi_entry.grid(row=0, column=1, columnspan=3, sticky="we", padx=6, pady=4)
        self.tk.Button(form, text="Browse…", command=self.browse_roi).grid(
            row=0, column=4, padx=6, pady=4
        )
        self.roi_label = self.tk.Label(form, text="No ROI loaded")
        self.roi_label.grid(row=1, column=0, columnspan=5, sticky="w", padx=6)

        self.tk.Label(form, text="Satellite").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.satellite_box = self.tk.Combobox(form, values=list(SATELLITES), state="readonly")
        self.satellite_box.grid(row=2, column=1, sticky="w", padx=6, pady=4)

        self.tk.Label(form, text="Start date (YYYY-MM-DD)").grid(
            row=2, column=2, sticky="w", padx=6
        )
        self.start_entry = self.tk.Entry(form, width=14)
        self.start_entry.grid(row=2, column=3, sticky="w", padx=6)

        self.tk.Label(form, text="End date (YYYY-MM-DD)").grid(
            row=2, column=4, sticky="w", padx=6
        )
        self.end_entry = self.tk.Entry(form, width=14)
        self.end_entry.grid(row=2, column=5, sticky="w", padx=6)

        self.tk.Label(form, text="Max cloud cover %").grid(
            row=3, column=0, sticky="w", padx=6, pady=4
        )
        self.cloud_entry = self.tk.Entry(form, width=14)
        self.cloud_entry.grid(row=3, column=1, sticky="w", padx=6)

        self.tk.Label(form, text="Min coverage ratio (0.5–1.0)").grid(
            row=3, column=2, sticky="w", padx=6
        )
        self.coverage_entry = self.tk.Entry(form, width=14)
        self.coverage_entry.grid(row=3, column=3, sticky="w", padx=6)

        self.tk.Label(form, text="Sort by").grid(row=3, column=4, sticky="w", padx=6)
        self.sort_box = self.tk.Combobox(form, values=list(SORT_OPTIONS), state="readonly")
        self.sort_box.grid(row=3, column=5, sticky="w", padx=6)

        actions = self.tk.Frame(tab)
        actions.pack(fill="x", padx=10)
        self.search_button = self.tk.Button(actions, text="Search", command=self.run_search)
        self.search_button.pack(side="left", pady=4)
        self.tk.Button(actions, text="Select all", command=self.select_all_results).pack(
            side="left", padx=6
        )
        self.tk.Button(actions, text="Clear selection", command=self.clear_selection).pack(
            side="left"
        )
        self.selection_label = self.tk.Label(actions, text="0 selected")
        self.selection_label.pack(side="left", padx=12)

        self.results_tree = self.tk.Treeview(
            tab, columns=list(catalog.TABLE_COLUMNS) + ["Selected"], show="headings", height=14
        )
        for column in list(catalog.TABLE_COLUMNS) + ["Selected"]:
            width = 130 if column == "Scene ID" else 90
            if column in ("Path", "Row", "Selected"):
                width = 60
            self.results_tree.column(column, width=width, anchor="w")
            self.results_tree.heading(column, text=column)
        self.results_tree.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self._bind_tree()

    def _bind_tree(self) -> None:
        tree = self.results_tree
        if tree is None or not hasattr(tree, "bind"):
            return
        try:
            tree.bind("<Button-1>", self._on_tree_click)
            tree.bind("<space>", self._on_tree_click)
        except Exception:  # pragma: no cover - toolkits without bind
            pass

    def _on_tree_click(self, event: Any) -> None:
        widget = getattr(event, "widget", None)
        tree = self.results_tree
        try:
            row = tree.identify_row(event.y)
        except Exception:
            row = None
        if not row:
            selection = tree.selection() if hasattr(tree, "selection") else ()
            row = selection[0] if selection else None
        if row:
            self.toggle_scene(row)
        del widget

    # -- Download tab --------------------------------------------------
    def _build_download_tab(self, master: Any) -> None:
        tab = self.tk.Frame(master)
        tab.pack(fill="both", expand=True)
        if hasattr(self.notebook, "add"):
            self.notebook.add(getattr(tab, "widget", tab), text="Download")
        self.download_tab = tab

        head = self.tk.LabelFrame(tab, text="Downloads")
        head.pack(fill="x", padx=10, pady=(10, 6))

        self.tk.Label(head, text="Output folder").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.output_entry = self.tk.Entry(head, width=62)
        self.output_entry.grid(row=0, column=1, sticky="we", padx=6, pady=4)
        self.tk.Button(head, text="Browse…", command=self.browse_output_dir).grid(
            row=0, column=2, padx=6
        )

        bands_info = (
            f"Downloaded bands (complete set, no per-band selection)\n"
            f"  Landsat 8/9 : {LANDSAT_BANDS}\n"
            f"  Sentinel-2  : {SENTINEL_BANDS}"
        )
        self.bands_label = self.tk.Label(head, text=bands_info, justify="left")
        self.bands_label.grid(row=1, column=0, columnspan=3, sticky="w", padx=6, pady=4)

        actions = self.tk.Frame(tab)
        actions.pack(fill="x", padx=10, pady=4)
        self.download_button = self.tk.Button(
            actions, text="Download selected", command=self.download_selected
        )
        self.download_button.pack(side="left")
        self.cancel_button = self.tk.Button(actions, text="Cancel", command=self.cancel_job)
        self.cancel_button.pack(side="left", padx=6)
        self.cancel_button.configure(state="disabled")

        self._build_progress(tab)
        self.log_text = self._build_log(tab, height=12)

    # -- Indices tab ---------------------------------------------------
    def _build_indices_tab(self, master: Any) -> None:
        tab = self.tk.Frame(master)
        tab.pack(fill="both", expand=True)
        if hasattr(self.notebook, "add"):
            self.notebook.add(getattr(tab, "widget", tab), text="Indices")
        self.indices_tab = tab

        scene_box = self.tk.LabelFrame(tab, text="Downloaded scenes (Ctrl-click for batch)")
        scene_box.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.scene_listbox = self.tk.Listbox(scene_box, height=8, selectmode="extended")
        self.scene_listbox.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.tk.Button(scene_box, text="Refresh", command=self.refresh_scene_list).pack(
            side="right", padx=6, anchor="n"
        )
        self.product_label = self.tk.Label(scene_box, text="No products yet")
        self.product_label.pack(side="bottom", anchor="w", padx=6)

        index_box = self.tk.LabelFrame(tab, text="Basic indices (light stack)")
        index_box.pack(fill="x", padx=10, pady=6)
        for name in BASIC_INDICES:
            var = self.tk.BooleanVar(value=name in self.session.config.selected_indices)
            self.index_vars[name] = var
            label = name if name not in SENTINEL_ONLY_INDICES else f"{name} (Sentinel-2 only)"
            check = self.tk.Checkbutton(
                index_box, text=label, variable=var, command=self._sync_index_availability
            )
            check.pack(side="left", padx=6, pady=4)
            self.index_checks[name] = check

        metric_box = self.tk.LabelFrame(tab, text="METRIC presets (Full processing)")
        metric_box.pack(fill="x", padx=10, pady=6)
        self.tk.Label(metric_box, text="Preset").pack(side="left", padx=6)
        self.preset_box = self.tk.Combobox(
            metric_box, values=list(PRESET_NAMES), state="readonly", width=12
        )
        self.preset_box.pack(side="left", padx=6)
        self.tk.Button(
            metric_box, text="Generate METRIC", command=self.generate_metric
        ).pack(side="left", padx=6)
        self.full_hint_label = self.tk.Label(
            metric_box, text="Full processing disabled — enable it in Settings"
        )
        self.full_hint_label.pack(side="left", padx=10)

        actions = self.tk.Frame(tab)
        actions.pack(fill="x", padx=10, pady=4)
        self.tk.Button(actions, text="Generate indices", command=self.generate_indices).pack(
            side="left"
        )
        self.tk.Button(actions, text="Help", command=self.open_help).pack(side="left", padx=6)
        self.indices_log = self._build_log(tab, height=8)

    # -- Settings tab --------------------------------------------------
    def _build_settings_tab(self, master: Any) -> None:
        tab = self.tk.Frame(master)
        tab.pack(fill="both", expand=True)
        if hasattr(self.notebook, "add"):
            self.notebook.add(getattr(tab, "widget", tab), text="Settings")
        self.settings_tab = tab

        box = self.tk.LabelFrame(tab, text="Defaults")
        box.pack(fill="x", padx=10, pady=(10, 6))
        rows = [
            ("Default output folder", "output"),
            ("PyPI mirror URL", "mirror"),
            ("CRS override for .shp without .prj", "crs"),
        ]
        for row, (label, kind) in enumerate(rows):
            self.tk.Label(box, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            entry = self.tk.Entry(box, width=64)
            entry.grid(row=row, column=1, sticky="we", padx=6, pady=4)
            if kind == "output":
                self.output_entry_settings = entry
                self.tk.Button(box, text="Browse…", command=self.browse_output_dir).grid(
                    row=row, column=2, padx=6
                )
            elif kind == "mirror":
                self.mirror_entry = entry
            else:
                self.crs_entry = entry

        range_box = self.tk.LabelFrame(tab, text="Search defaults")
        range_box.pack(fill="x", padx=10, pady=6)
        self.tk.Label(range_box, text="Start date").grid(row=0, column=0, padx=6, sticky="w")
        self.settings_start_entry = self.tk.Entry(range_box, width=14)
        self.settings_start_entry.grid(row=0, column=1, padx=6, pady=4)
        self.tk.Label(range_box, text="End date").grid(row=0, column=2, padx=6, sticky="w")
        self.settings_end_entry = self.tk.Entry(range_box, width=14)
        self.settings_end_entry.grid(row=0, column=3, padx=6)
        self.tk.Label(range_box, text="Cloud %").grid(row=1, column=0, padx=6, sticky="w")
        self.settings_cloud_entry = self.tk.Entry(range_box, width=14)
        self.settings_cloud_entry.grid(row=1, column=1, padx=6, pady=4)
        self.tk.Label(range_box, text="Min coverage").grid(row=1, column=2, padx=6, sticky="w")
        self.settings_coverage_entry = self.tk.Entry(range_box, width=14)
        self.settings_coverage_entry.grid(row=1, column=3, padx=6)

        env_box = self.tk.LabelFrame(tab, text="Python environment")
        env_box.pack(fill="x", padx=10, pady=6)
        self.env_label = self.tk.Label(env_box, text="Environment: unknown")
        self.env_label.pack(anchor="w", padx=6, pady=4)
        buttons = self.tk.Frame(env_box)
        buttons.pack(anchor="w", padx=6, pady=4)
        self.enable_full_button = self.tk.Button(
            buttons, text="Enable full processing", command=self.enable_full_processing
        )
        self.enable_full_button.pack(side="left")
        if getattr(sys, "frozen", False):
            self.enable_full_button.configure(state="disabled")
            self.enable_full_button.configure(text="Full processing (source install only)")
        self.tk.Button(buttons, text="Prepare environment", command=self.prepare_environment).pack(
            side="left", padx=6
        )
        self.tk.Button(buttons, text="Save settings", command=self.save_settings).pack(side="left")

        self.settings_log = self._build_log(tab, height=8)

    # -- shared widgets ------------------------------------------------
    def _build_progress(self, master: Any) -> None:
        frame = self.tk.Frame(master)
        frame.pack(fill="x", padx=10, pady=4)
        self.progress_bar = self.tk.Progressbar(frame, maximum=1.0, value=0.0, length=320)
        self.progress_bar.pack(side="left")
        self.progress_label = self.tk.Label(frame, text="")
        self.progress_label.pack(side="left", padx=8)

    def _build_log(self, master: Any, height: int = 10) -> Any:
        frame = self.tk.Frame(master)
        frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        text = self.tk.Text(frame, height=height, wrap="word")
        text.pack(side="left", fill="both", expand=True)
        scroll = getattr(self.tk, "Scrollbar", None)
        if scroll is not None:
            bar = scroll(frame)
            bar.pack(side="right", fill="y")
            try:
                text.configure(yscrollcommand=bar.set)
                bar.configure(command=text.yview)
            except Exception:  # pragma: no cover - fake widgets
                pass
        return text

    def _build_status_bar(self, master: Any) -> None:
        bar = self.tk.Frame(master)
        bar.pack(fill="x", side="bottom")
        self.status_label = self.tk.Label(bar, text="Ready", anchor="w")
        self.status_label.pack(fill="x", padx=10, pady=4)

    # ------------------------------------------------------------------
    # Config <-> widgets
    # ------------------------------------------------------------------
    def _load_config_into_widgets(self) -> None:
        cfg = self.session.config
        self._set_entry(self.roi_entry, cfg.roi_path)
        self._set_entry(self.start_entry, cfg.start_date)
        self._set_entry(self.end_entry, cfg.end_date)
        self._set_entry(self.cloud_entry, cfg.cloud_threshold)
        self._set_entry(self.coverage_entry, cfg.min_coverage_ratio)
        self._set_entry(self.output_entry, cfg.output_dir)
        self._set_entry(self.output_entry_settings, cfg.output_dir)
        self._set_entry(self.mirror_entry, cfg.mirror_url)
        self._set_entry(self.crs_entry, cfg.crs_override)
        self._set_entry(self.settings_start_entry, cfg.start_date)
        self._set_entry(self.settings_end_entry, cfg.end_date)
        self._set_entry(self.settings_cloud_entry, cfg.cloud_threshold)
        self._set_entry(self.settings_coverage_entry, cfg.min_coverage_ratio)
        self._set_combobox(self.satellite_box, cfg.satellite)
        self._set_combobox(self.sort_box, cfg.sort_by)
        self._set_combobox(self.preset_box, cfg.preset)
        if cfg.roi_path and self.session.roi is None:
            try:
                self.session.load_roi(cfg.roi_path, emit=self.log)
            except ROIError:
                self.log(f"Saved ROI could not be loaded: {cfg.roi_path}")
        if self.session.roi is not None:
            self._set_label(self.roi_label, f"ROI: {self.session.roi.label}")

    def _collect_config(self) -> AppConfig:
        """Read every widget into the session config (no persistence)."""
        cfg = self.session.config
        cfg.roi_path = self._entry_value(self.roi_entry) or cfg.roi_path
        cfg.start_date = self._entry_value(self.start_entry) or self._entry_value(
            self.settings_start_entry
        )
        cfg.end_date = self._entry_value(self.end_entry) or self._entry_value(
            self.settings_end_entry
        )
        cfg.cloud_threshold = self._as_float(
            self._entry_value(self.cloud_entry), cfg.cloud_threshold
        )
        cfg.min_coverage_ratio = self._as_float(
            self._entry_value(self.coverage_entry), cfg.min_coverage_ratio
        )
        cfg.satellite = self._combobox_value(self.satellite_box, cfg.satellite)
        cfg.sort_by = self._combobox_value(self.sort_box, cfg.sort_by)
        cfg.output_dir = (
            self._entry_value(self.output_entry)
            or self._entry_value(getattr(self, "output_entry_settings", None))
            or cfg.output_dir
        )
        cfg.mirror_url = self._entry_value(self.mirror_entry) or cfg.mirror_url
        cfg.crs_override = self._entry_value(self.crs_entry) or cfg.crs_override
        cfg.preset = self._combobox_value(self.preset_box, cfg.preset)
        cfg.selected_indices = [
            name
            for name, var in self.index_vars.items()
            if var.get() and (name not in SENTINEL_ONLY_INDICES or cfg.satellite == SENTINEL2)
        ]
        return cfg.normalized()

    # ------------------------------------------------------------------
    # Log / status / progress
    # ------------------------------------------------------------------
    def log(self, message: str, *, target: str = "auto") -> None:
        text = f"{message}\n"
        widgets = []
        if target in ("auto", "download"):
            widgets.append(self.log_text)
        if target in ("auto", "indices"):
            widgets.append(getattr(self, "indices_log", None))
        if target in ("auto", "settings"):
            widgets.append(getattr(self, "settings_log", None))
        for widget in widgets:
            if widget is None or not hasattr(widget, "insert"):
                continue
            with contextlib.suppress(Exception):  # pragma: no cover - destroyed widget
                widget.insert("end", text)
                widget.see("end")
        self.session.remember_log(message)

    def set_status(self, message: str) -> None:
        self.last_status = message
        self._set_label(self.status_label, message)

    def set_progress(self, current: int, total: int, label: str = "") -> None:
        if self.progress_bar is None:
            return
        fraction = 0.0 if total <= 0 else max(0.0, min(1.0, current / total))
        try:
            maximum = float(getattr(self.progress_bar, "maximum", 1.0) or 1.0)
            self.progress_bar.set(fraction * maximum)
        except Exception:  # pragma: no cover
            pass
        self._set_label(
            self.progress_label, f"{current}/{total} {label}".strip() if total else label
        )

    # ------------------------------------------------------------------
    # Search actions
    # ------------------------------------------------------------------
    def browse_roi(self) -> None:
        path = self.prompter.open_file("Select a ROI file", kind="roi")
        if not path:
            return
        self._set_entry(self.roi_entry, path)
        self.load_roi(path)

    def load_roi(self, path: str | Path) -> None:
        try:
            self._collect_config()
            roi = self.session.load_roi(path, emit=self.log)
        except ROIError as exc:
            self.log(f"ERROR: {exc}")
            self.set_status(f"ROI error: {exc}")
            self.prompter.error("ROI error", str(exc))
            return
        self._set_label(self.roi_label, f"ROI: {roi.label}")
        self.set_status(self.session.status_line(f"ROI loaded: {roi.path.name}"))

    def run_search(self) -> None:
        if self.busy:
            return
        self._collect_config()
        self.session.save_config()

        def work(emitter: Emitter) -> list[catalog.SceneSummary]:
            emitter.log(
                f"Searching {self.session.config.satellite} · "
                f"{self.session.config.start_date} → {self.session.config.end_date}"
            )
            results = self.session.search(emit=emitter)
            emitter.progress(len(results), len(results), "scenes")
            return results

        self._start_job(work, self._after_search, name="search")

    def _after_search(self, results: Any) -> None:
        scenes: list[catalog.SceneSummary] = list(results or [])
        self._render_results(scenes)
        if not scenes:
            message = "No qualifying scenes found"
            self.log(message + " — widen the date range or relax the filters")
            self.set_status(message)
            self.prompter.warning("No qualifying scenes", message)
        else:
            self.log(f"{len(scenes)} qualifying scene(s) listed")
            self.set_status(self.session.status_line(f"{len(scenes)} scene(s)"))

    def _render_results(self, scenes: list[catalog.SceneSummary]) -> None:
        tree = self.results_tree
        if tree is None:
            return
        for key in tree.get_children():
            tree.delete(key)
        for scene in scenes:
            marker = "✔" if self.session.is_selected(scene.id) else ""
            tree.insert("", "end", iid=scene.id, values=scene.as_row() + (marker,))
        self._refresh_selection_label()

    def select_all_results(self) -> None:
        for scene in self.session.results:
            self.session.toggle_selection(scene.id, True)
        self._render_results(self.session.results)

    def clear_selection(self) -> None:
        for scene in self.session.results:
            self.session.toggle_selection(scene.id, False)
        self._render_results(self.session.results)

    def toggle_scene(self, scene_id: str) -> None:
        try:
            self.session.toggle_selection(scene_id)
        except KeyError:
            return
        tree = self.results_tree
        if tree is not None and scene_id in tree.get_children():
            tree.item(scene_id, values=self._row_values(scene_id))
        self._refresh_selection_label()

    def _row_values(self, scene_id: str) -> tuple[Any, ...]:
        for scene in self.session.results:
            if scene.id == scene_id:
                marker = "✔" if self.session.is_selected(scene_id) else ""
                return scene.as_row() + (marker,)
        return ()

    def _refresh_selection_label(self) -> None:
        self._set_label(self.selection_label, f"{self.session.selected_count} selected")

    # ------------------------------------------------------------------
    # Download actions
    # ------------------------------------------------------------------
    def browse_output_dir(self) -> None:
        path = self.prompter.open_directory("Select the output folder")
        if not path:
            return
        self._set_entry(self.output_entry, path)
        self._set_entry(getattr(self, "output_entry_settings", None), path)
        self.session.update_config(output_dir=path)
        self.set_status(f"Output folder: {path}")

    def download_selected(self) -> None:
        if self.busy:
            return
        self._collect_config()
        if not self.session.selected_count:
            self.prompter.warning("Nothing selected", "Select at least one scene in the Search tab")
            self.set_status("No scenes selected")
            return

        def work(emitter: Emitter) -> Any:
            emitter.log("Starting download…")
            return self.session.download(emit=emitter)

        self._start_job(
            work,
            self._after_download,
            name="download",
            progress_aware=True,
        )

    def _after_download(self, result: Any) -> None:
        scenes = getattr(result, "scenes", []) or []
        self.log(f"Download complete: {len(scenes)} scene(s)")
        self.set_progress(len(scenes), len(scenes), "scenes")
        self.set_status(self.session.status_line(f"{len(scenes)} scene(s) downloaded"))
        self.refresh_scene_list()
        if scenes:
            self.prompter.info(
                "Download complete",
                f"{len(scenes)} scene(s) written to\n{self.session.config.scenes_dir}",
            )

    # ------------------------------------------------------------------
    # Indices actions
    # ------------------------------------------------------------------
    def refresh_scene_list(self) -> None:
        listbox = self.scene_listbox
        if self.output_entry is not None:
            self._collect_config()
        scenes = self.session.scene_infos()
        if listbox is not None and hasattr(listbox, "delete"):
            listbox.delete(0, "end")
            for scene in scenes:
                suffix = f" · {scene.date}" if scene.date else ""
                listbox.insert("end", f"{scene.name}{suffix}")
        products = self.session.output_summary()["products"]
        if products:
            total = sum(len(paths) for paths in products.values())
            self._set_label(
                self.product_label,
                f"{total} product(s) in {', '.join(sorted(products))}",
            )
        else:
            self._set_label(self.product_label, "No products yet")
        self._sync_index_availability()
        return None

    def _selected_scene_names(self) -> list[str]:
        listbox = self.scene_listbox
        if listbox is None or not hasattr(listbox, "curselection"):
            return []
        scenes = self.session.scene_infos()
        names = []
        for index in listbox.curselection():
            if index < len(scenes):
                names.append(scenes[index].name)
        return names

    def _sync_index_availability(self) -> None:
        """Grey out indices the selected satellite cannot produce."""
        satellite = self.session.config.satellite
        full = self.session.full_mode_enabled()
        # Sentinel-only indices are greyed out for other satellites.
        for name, check in self.index_checks.items():
            if name not in SENTINEL_ONLY_INDICES:
                continue
            available = satellite == SENTINEL2
            with contextlib.suppress(Exception):
                check.configure(state="normal" if available else "disabled")
            if not available and self.index_vars[name].get():
                self.index_vars[name].set(False)
        self._set_label(
            self.full_hint_label,
            "Full processing enabled" if full else "Full processing disabled — enable it in Settings",
        )
        if self.preset_box is not None and hasattr(self.preset_box, "configure"):
            with contextlib.suppress(Exception):  # pragma: no cover
                self.preset_box.configure(state="readonly" if full else "disabled")

    def generate_indices(self) -> None:
        if self.busy:
            return
        self._collect_config()
        selected = [name for name, var in self.index_vars.items() if var.get()]
        if not selected:
            self.prompter.warning("No index selected", "Tick at least one index")
            return
        scenes = self._selected_scene_names()
        if not scenes and not self.session.scene_infos():
            self.prompter.warning(
                "No scenes", "Download a scene first — the Indices tab lists downloaded scenes"
            )
            return

        def work(emitter: Emitter) -> Any:
            return self.session.generate(
                emit=emitter, scene_names=scenes or None, index_names=selected
            )

        self._start_job(work, self._after_generate, name="indices", progress_aware=True)

    def _after_generate(self, result: Any) -> None:
        products = getattr(result, "products", []) or []
        self.log(f"Index generation complete: {len(products)} product(s)")
        self.set_progress(len(products), len(products), "products")
        self.set_status(self.session.status_line(f"{len(products)} product(s) generated"))
        self.refresh_scene_list()
        self.prompter.info(
            "Indices generated",
            f"{len(products)} product(s) written to\n{self.session.config.products_dir}",
        )

    def generate_metric(self) -> None:
        if self.busy:
            return
        self._collect_config()
        if not self.session.full_mode_enabled():
            self.prompter.warning(
                "Full processing required",
                "METRIC presets need the heavy stack.\n"
                "Press 'Enable full processing' in Settings, then try again.",
            )
            self.set_status("Full processing is not enabled")
            return

        preset = self._combobox_value(self.preset_box, self.session.config.preset)
        scenes = self._selected_scene_names() or None

        def work(emitter: Emitter) -> Any:
            return self.session.generate_preset(emit=emitter, preset=preset, scene_names=scenes)

        self._start_job(work, self._after_metric, name="metric", progress_aware=True)

    def _after_metric(self, result: Any) -> None:
        runs = getattr(result, "preset_runs", []) or []
        written = sum(len(run.written) for run in runs)
        self.log(f"METRIC preset finished: {written} product(s)")
        self.set_status(self.session.status_line(f"METRIC: {written} product(s)"))
        self.refresh_scene_list()
        self.set_progress(written, written, "products")

    # ------------------------------------------------------------------
    # Settings actions
    # ------------------------------------------------------------------
    def save_settings(self) -> None:
        self._collect_config()
        self.session.update_config(
            output_dir=self._entry_value(getattr(self, "output_entry_settings", None))
            or self.session.config.output_dir,
            start_date=self._entry_value(self.settings_start_entry)
            or self.session.config.start_date,
            end_date=self._entry_value(self.settings_end_entry) or self.session.config.end_date,
            cloud_threshold=self._as_float(
                self._entry_value(self.settings_cloud_entry),
                self.session.config.cloud_threshold,
            ),
            min_coverage_ratio=self._as_float(
                self._entry_value(self.settings_coverage_entry),
                self.session.config.min_coverage_ratio,
            ),
            crs_override=self._entry_value(self.crs_entry) or "",
            mirror_url=self._entry_value(self.mirror_entry) or "",
        )
        path = self.session.save_config()
        self.log(f"Settings saved to {path}", target="settings")
        self.set_status("Settings saved")

    def refresh_env_status(self) -> None:
        try:
            status = self.bootstrapper.status(self.session.config)
        except Exception as exc:  # pragma: no cover - defensive
            self.log(f"Could not inspect the environment: {exc}", target="settings")
            return
        full = self.session.full_mode_enabled()
        label = "Environment: Full" if full else status.label
        if full and not status.full_ready:
            label = "Environment: Full (pending install)"
        self._set_label(self.env_label, label)
        if self.enable_full_button is not None:
            with contextlib.suppress(Exception):  # pragma: no cover
                self.enable_full_button.configure(state="disabled" if full else "normal")

    def prepare_environment(self) -> None:
        if self.busy:
            return
        mirror = self._entry_value(self.mirror_entry) or None

        def work(emitter: Emitter) -> Any:
            return self.bootstrapper.ensure_ready(mirror, emitter.log)

        self._start_job(work, self._after_env, name="bootstrap", progress_aware=False)

    def enable_full_processing(self) -> None:
        if self.busy:
            return
        mirror = self._entry_value(self.mirror_entry) or None

        def work(emitter: Emitter) -> Any:
            emitter.log("Enabling full processing — installing the heavy stack…")
            return self.bootstrapper.install_full(mirror, emitter.log)

        self._start_job(work, self._after_full, name="install-full", progress_aware=False)

    def _after_env(self, status: Any) -> None:
        self.session.update_config(mode="lite")
        self.session.save_config()
        self.refresh_env_status()
        self.set_status("Environment ready")
        self.log("Environment prepared", target="settings")
        del status

    def _after_full(self, _code: Any) -> None:
        self.session.set_full_mode(True)
        self.session.save_config()
        self.refresh_env_status()
        self._sync_index_availability()
        self.log("Full processing enabled", target="settings")
        self.set_status("Full processing enabled")
        self.prompter.info(
            "Full processing enabled",
            "The METRIC stack is installed.\nMETRIC presets are now available in the Indices tab.",
        )

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    def open_help(self) -> None:
        self.prompter.help(build_help_text())
        self.set_status("Help opened")

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------
    def _start_job(
        self,
        func: Callable[[Emitter], Any],
        on_result: Callable[[Any], None] | None,
        *,
        name: str = "job",
        progress_aware: bool = True,
    ) -> BackgroundJob:
        self.busy = True
        self._on_result = on_result
        self._progress_aware = progress_aware
        self._set_busy_controls(True)
        self.set_status(f"Working… ({name})")
        job = self.job_runner(func, name)
        self.current_job = job
        if job.finished:
            self._consume(job)
        else:
            self._schedule_poll()
        return job

    def _schedule_poll(self) -> None:
        after = getattr(self.tk, "after", None)
        if after is not None:
            after(POLL_INTERVAL_MS, self._poll_job)

    def _poll_job(self) -> None:
        job = self.current_job
        if job is None:
            return
        self._consume(job)
        if not job.finished or job.is_alive:
            self._schedule_poll()

    def _consume(self, job: BackgroundJob) -> None:
        for event in job.poll():
            self._handle_event(event)
        if job.finished:
            self.busy = False
            self.current_job = None
            self._set_busy_controls(False)

    def _handle_event(self, event: JobEvent) -> None:
        if event.kind == "log":
            self.log(str(event.payload))
        elif event.kind == "progress":
            payload = event.payload
            if self._progress_aware:
                self.set_progress(payload.current, payload.total, payload.label)
            else:
                self.set_status(f"Working… {payload.label or payload.fraction:.0%}")
        elif event.kind == "error":
            error = event.payload
            self.log(f"ERROR: {error}")
            self.set_status(f"Failed: {error}")
            self.prompter.error("Operation failed", str(error))
        elif event.kind == "cancelled":
            self.log("Operation cancelled")
            self.set_status("Cancelled")
        elif event.kind == "result" and self._on_result is not None:
            self._on_result(event.payload)

    def _set_busy_controls(self, busy: bool) -> None:
        for button, enabled_states in (
            (self.search_button, ("normal", "disabled")),
            (self.download_button, ("normal", "disabled")),
            (self.enable_full_button, ("normal", "disabled")),
        ):
            if button is None:
                continue
            with contextlib.suppress(Exception):  # pragma: no cover
                button.configure(state=enabled_states[1] if busy else enabled_states[0])
        if self.cancel_button is not None:
            with contextlib.suppress(Exception):  # pragma: no cover
                self.cancel_button.configure(state="normal" if busy else "disabled")

    def cancel_job(self) -> None:
        if self.current_job is not None:
            self.current_job.cancel()
            self.log("Cancelling…")
            self.set_status("Cancelling…")

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _set_entry(self, entry: Any, value: Any) -> None:
        if entry is None:
            return
        text = "" if value is None else str(value)
        if hasattr(entry, "set"):
            entry.set(text)
        elif hasattr(entry, "delete") and hasattr(entry, "insert"):
            entry.delete(0, "end")
            entry.insert(0, text)

    def _entry_value(self, entry: Any) -> str:
        if entry is None or not hasattr(entry, "get"):
            return ""
        try:
            return str(entry.get()).strip()
        except Exception:  # pragma: no cover - destroyed widget
            return ""

    def _set_combobox(self, box: Any, value: str) -> None:
        if box is None or not hasattr(box, "set"):
            return
        box.set(value)

    def _combobox_value(self, box: Any, default: str) -> str:
        if box is None or not hasattr(box, "get"):
            return default
        try:
            value = str(box.get()).strip()
        except Exception:  # pragma: no cover
            return default
        return value or default

    def _set_label(self, label: Any, text: str) -> None:
        if label is None:
            return
        try:
            label.configure(text=text)
        except Exception:  # pragma: no cover
            if hasattr(label, "text"):
                label.text = text

    @staticmethod
    def _as_float(value: Any, default: float) -> float:
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------
    def mainloop(self) -> None:
        if self.root is None:
            self.build()
        mainloop = getattr(self.tk, "mainloop", None)
        if mainloop is None:
            raise RuntimeError("This toolkit cannot run an event loop")
        mainloop()

    def run(self) -> None:
        """Build the window and enter the event loop."""
        self.build()
        self.mainloop()


def sentinel_notice(index_name: str) -> str | None:
    """Shown when a Sentinel-only index is requested for another satellite."""
    if index_name.upper() in SENTINEL_ONLY_INDICES:
        return f"{index_name.upper()} is only available for Sentinel-2 scenes"
    return None


__all__ = [
    "LANDSAT_BANDS",
    "POLL_INTERVAL_MS",
    "SENTINEL_BANDS",
    "WINDOW_TITLE",
    "DesktopApp",
    "SyncJobRunner",
    "ToolkitPrompter",
    "background_runner",
    "sentinel_notice",
]

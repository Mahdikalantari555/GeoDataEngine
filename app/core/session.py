"""Session controller — the GUI's headless brain.

Everything the tabs need lives here: configuration persistence, ROI loading,
search, download, index generation and METRIC preset runs.  Every operation
takes an optional ``emit`` callback (``emit(message)`` / ``emit("progress",
current, total, label)``) so the same code path is driven by the Tkinter
``after()`` queue in production and by a plain list in the tests.

The engine is reached through :class:`EngineBridge`; a fake bridge implements
the same three methods, which means the whole download/generate flow is
testable without network access or rasterio.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from . import catalog, indices, presets
from .config import SENTINEL2, SENTINEL_ONLY_INDICES, AppConfig, ConfigStore
from .indices import SceneIndexError
from .layout import ensure_layout, list_products, list_scene_dirs
from .roi import ROI, ROIError, load_roi

Emit = Callable[..., None]


def _noop_emit(*_args: Any, **_kwargs: Any) -> None:
    return None


def _log(emit: Emit, message: str) -> None:
    emit(message)


def _progress(emit: Emit, current: int, total: int, label: str = "") -> None:
    try:
        emit("progress", current, total, label)
    except TypeError:  # emitter that only accepts messages
        emit(f"[{current}/{total}] {label}")


class EngineBridge(Protocol):
    """The slice of the engine the GUI depends on."""

    def search(
        self, satellite: str, roi: ROI, date_range: tuple[str, str], *, max_cloud_cover: float
    ) -> list[dict[str, Any]]: ...

    def download(
        self,
        satellite: str,
        roi: ROI,
        date_range: tuple[str, str],
        selected_ids: list[str],
        output_dir: Path,
        *,
        max_cloud_cover: float,
        min_coverage_ratio: float,
        sort_by: str,
        emit: Emit = _noop_emit,
    ) -> list[dict[str, Any]]: ...

    def metric_runner(self) -> presets.MetricRunner: ...


class LiveEngineBridge:
    """Engine bridge backed by the real Planetary Computer fetchers."""

    def __init__(self, fetcher_factory: Callable[[str], Any] | None = None) -> None:
        self._factory = fetcher_factory
        self._same_day_fallback = True

    # -- helpers -------------------------------------------------------
    def _fetcher(self, satellite: str, max_cloud_cover: float) -> Any:
        return catalog.build_fetcher(
            satellite,
            max_cloud_cover=max_cloud_cover,
            fetcher_factory=self._factory,
        )

    # -- protocol ------------------------------------------------------
    def search(
        self, satellite: str, roi: ROI, date_range: tuple[str, str], *, max_cloud_cover: float
    ) -> list[dict[str, Any]]:
        fetcher = self._fetcher(satellite, max_cloud_cover)
        try:
            return list(fetcher.search_scenes(roi.geometry, date_range) or [])
        except Exception as exc:
            raise catalog.CatalogError(f"STAC search failed: {exc}") from exc

    def download(
        self,
        satellite: str,
        roi: ROI,
        date_range: tuple[str, str],
        selected_ids: list[str],
        output_dir: Path,
        *,
        max_cloud_cover: float,
        min_coverage_ratio: float,
        sort_by: str,
        emit: Emit = _noop_emit,
    ) -> list[dict[str, Any]]:
        fetcher = self._fetcher(satellite, max_cloud_cover)
        if not selected_ids:
            return []
        try:
            results = fetcher.fetch_scenes(
                roi.geometry,
                date_range,
                str(output_dir),
                min_cloud_cover=0.0,
                sort_by=sort_by,
                min_coverage_ratio=min_coverage_ratio,
                selected_ids=selected_ids,
            )
        except Exception as exc:
            raise catalog.CatalogError(f"Download failed: {exc}") from exc

        wanted = set(selected_ids)
        chosen = [r for r in results if str(r.get("scene_id")) in wanted]
        _log(emit, f"Downloaded {len(chosen)} of {len(selected_ids)} selected scene(s)")
        return chosen

    def metric_runner(self) -> presets.MetricRunner:
        return presets.DefaultMetricRunner()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class DownloadResult:
    """One downloaded scene."""

    scene_id: str
    date: str
    directory: Path
    bands: dict[str, Path] = field(default_factory=dict)
    mtl_file: Path | None = None

    @property
    def bands_downloaded(self) -> int:
        return len(self.bands)


@dataclass
class SessionResult:
    """Aggregate outcome of a session operation."""

    message: str
    scenes: list[DownloadResult] = field(default_factory=list)
    products: list[indices.GeneratedProduct] = field(default_factory=list)
    preset_runs: list[presets.PresetRun] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.scenes or self.products or self.preset_runs)


@dataclass
class DownloadOptions:
    """Inputs of :meth:`Session.download`."""

    config: AppConfig
    selected_ids: list[str]

    @property
    def satellite(self) -> str:
        return self.config.satellite


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
class Session:
    """Owns configuration, the ROI and all GUI operations."""

    def __init__(
        self,
        store: ConfigStore | None = None,
        bridge: EngineBridge | None = None,
        *,
        full_mode: bool | None = None,
    ) -> None:
        self.store = store or ConfigStore()
        self.config = self.store.load()
        self.bridge: EngineBridge = bridge or LiveEngineBridge()
        self.roi: ROI | None = None
        self.results: list[catalog.SceneSummary] = []
        self.selected_ids: set[str] = set()
        self._full_mode = full_mode
        self.log_history: list[str] = []

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def save_config(self) -> Path:
        self.config = self.config.normalized()
        return self.store.save(self.config)

    def update_config(self, **changes: Any) -> AppConfig:
        for key, value in changes.items():
            if not hasattr(self.config, key):
                setattr(self.config, key, value)
                continue
            setattr(self.config, key, value)
        self.config = self.config.normalized()
        return self.config

    def full_mode_enabled(self) -> bool:
        """Whether METRIC presets may run in this session."""
        if self._full_mode is not None:
            return self._full_mode
        return self.config.mode == "full"

    def set_full_mode(self, enabled: bool) -> None:
        self._full_mode = bool(enabled)
        self.config.mode = "full" if enabled else "lite"

    def remember_log(self, message: str) -> None:
        self.log_history.append(message)
        del self.log_history[:-500]

    # ------------------------------------------------------------------
    # ROI
    # ------------------------------------------------------------------
    def load_roi(self, path: str | Path, emit: Emit = _noop_emit) -> ROI:
        """Load a ROI file and log any CRS assumptions."""
        roi = load_roi(path, crs_override=self.config.crs_override or None)
        self.roi = roi
        self.config.roi_path = str(roi.path)
        for warning in roi.warnings:
            _log(emit, f"WARNING: {warning}")
        _log(emit, f"ROI loaded: {roi.label}")
        return roi

    def require_roi(self) -> ROI:
        if self.roi is None:
            raise ROIError("Load a ROI file before continuing")
        return self.roi

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search(self, emit: Emit = _noop_emit) -> list[catalog.SceneSummary]:
        """Search the catalog and store the selectable results."""
        roi = self.require_roi()
        if not self.config.start_date or not self.config.end_date:
            raise ValueError("Select a start and end date before searching")

        _log(
            emit,
            f"Searching {self.config.satellite} scenes between "
            f"{self.config.start_date} and {self.config.end_date} "
            f"(cloud ≤ {self.config.cloud_threshold:.0f}%, coverage ≥ "
            f"{self.config.min_coverage_ratio:.2f})",
        )
        items = self.bridge.search(
            self.config.satellite,
            roi,
            self.config.date_range(),
            max_cloud_cover=self.config.cloud_threshold,
        )
        summaries = [catalog.summarize_scene(item, self.config.satellite, roi) for item in items]
        summaries = catalog.filter_by_coverage(summaries, self.config.min_coverage_ratio)
        summaries = catalog.sort_scenes(summaries, self.config.sort_by)

        self.results = summaries
        # Selections are id-keyed, so they survive a re-search.
        known = {scene.id for scene in summaries}
        self.selected_ids &= known

        if not summaries:
            _log(emit, "No qualifying scenes found — relax the cloud or coverage filters")
        else:
            _log(emit, f"{len(summaries)} qualifying scene(s) found")
        return summaries

    def toggle_selection(self, scene_id: str, selected: bool | None = None) -> bool:
        """Select/deselect a scene; returns the resulting selection state."""
        if scene_id not in {scene.id for scene in self.results}:
            raise KeyError(f"Unknown scene: {scene_id}")
        if selected is None:
            selected = scene_id not in self.selected_ids
        if selected:
            self.selected_ids.add(scene_id)
        else:
            self.selected_ids.discard(scene_id)
        return scene_id in self.selected_ids

    def is_selected(self, scene_id: str) -> bool:
        return scene_id in self.selected_ids

    @property
    def selected_count(self) -> int:
        return len(self.selected_ids)

    def selected_scene_ids(self) -> list[str]:
        """Selected ids in the order they appear in the results table."""
        return [scene.id for scene in self.results if scene.id in self.selected_ids]

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def download(self, emit: Emit = _noop_emit) -> SessionResult:
        """Download every selected scene into ``<output>/scenes``."""
        roi = self.require_roi()
        selected = self.selected_scene_ids()
        if not selected:
            raise ValueError("Select at least one scene to download")

        layout = ensure_layout(self.config.output_dir)
        _log(emit, f"Downloading {len(selected)} scene(s) into {layout['scenes']}")

        raw_results = self.bridge.download(
            self.config.satellite,
            roi,
            self.config.date_range(),
            selected,
            layout["scenes"],
            max_cloud_cover=self.config.cloud_threshold,
            min_coverage_ratio=self.config.min_coverage_ratio,
            sort_by=self.config.sort_by,
            emit=emit,
        )

        scenes: list[DownloadResult] = []
        total = len(raw_results) or 1
        for position, raw in enumerate(raw_results, start=1):
            bands = {
                str(band): Path(path)
                for band, path in (raw.get("band_files") or {}).items()
            }
            scene = DownloadResult(
                scene_id=str(raw.get("scene_id", "unknown")),
                date=str(raw.get("date", ""))[:10],
                directory=Path(raw.get("directory", layout["scenes"])),
                bands=bands,
                mtl_file=Path(raw["mtl_file"]) if raw.get("mtl_file") else None,
            )
            scenes.append(scene)
            for band, path in bands.items():
                _log(emit, f"  {scene.scene_id}: saved {band} → {path.name}")
            _progress(emit, position, total, scene.scene_id)

        self.save_config()
        message = f"Downloaded {len(scenes)} scene(s)"
        _log(emit, message)
        return SessionResult(message=message, scenes=scenes)

    # ------------------------------------------------------------------
    # Scenes on disk
    # ------------------------------------------------------------------
    def scene_infos(self) -> list[indices.SceneInfo]:
        return indices.list_scenes(self.config.scenes_dir)

    def scene_infos_for(self, satellite: str) -> list[indices.SceneInfo]:
        return [
            scene
            for scene in self.scene_infos()
            if not scene.satellite or scene.satellite == satellite
        ]

    def get_scene(self, scene_name: str) -> indices.SceneInfo:
        for scene in self.scene_infos():
            if scene.name == scene_name or scene.scene_id == scene_name:
                return scene
        raise KeyError(f"Unknown downloaded scene: {scene_name}")

    # ------------------------------------------------------------------
    # Indices
    # ------------------------------------------------------------------
    def generate(
        self,
        emit: Emit = _noop_emit,
        *,
        scene_names: list[str] | None = None,
        index_names: list[str] | None = None,
    ) -> SessionResult:
        """Generate basic indices for the given (default: all) scenes."""
        index_names = list(index_names if index_names is not None else self.config.selected_indices)
        if not index_names:
            raise SceneIndexError("Select at least one index to generate")

        scenes = (
            [self.get_scene(name) for name in scene_names]
            if scene_names
            else self.scene_infos()
        )
        if not scenes:
            raise ValueError("No downloaded scenes found — download a scene first")

        jobs = [(scene, name) for scene in scenes for name in index_names]

        # Fail fast: refuse the whole request before writing anything when an
        # index is not available for one of the selected satellites.
        invalid: list[str] = []
        for scene, name in jobs:
            try:
                indices.validate_index(name, scene.satellite)
            except indices.UnsupportedIndexError as exc:
                invalid.append(f"{name} → {scene.scene_id}: {exc}")
        if invalid:
            raise indices.UnsupportedIndexError(
                "Some selected indices are not available for the chosen scenes:\n  "
                + "\n  ".join(dict.fromkeys(invalid))
            )

        products: list[indices.GeneratedProduct] = []
        total = len(jobs)
        for position, (scene, name) in enumerate(jobs, start=1):
            _progress(emit, position - 1, total, f"{name} · {scene.scene_id}")
            product = indices.generate_index(
                scene,
                name,
                self.config.output_dir,
                progress=lambda message: _log(emit, f"  {message}"),
            )
            products.append(product)
            _progress(emit, position, total, f"{name} · {scene.scene_id}")

        self.config.selected_indices = [name.upper() for name in index_names]
        self.save_config()
        message = f"Generated {len(products)} product(s)"
        _log(emit, message)
        return SessionResult(message=message, products=products)

    # ------------------------------------------------------------------
    # METRIC presets
    # ------------------------------------------------------------------
    def generate_preset(
        self,
        emit: Emit = _noop_emit,
        *,
        preset: str | None = None,
        scene_names: list[str] | None = None,
    ) -> SessionResult:
        """Run a METRIC preset for the given scenes (requires full mode)."""
        preset = preset or self.config.preset
        presets.require_full_mode(self.full_mode_enabled())

        scenes = (
            [self.get_scene(name) for name in scene_names]
            if scene_names
            else [s for s in self.scene_infos() if s.satellite in presets.METRIC_SATELLITES]
        )
        if not scenes:
            raise presets.PresetError(
                "No Landsat scene found for METRIC processing — download one first"
            )

        runs: list[presets.PresetRun] = []
        total = len(scenes)
        for position, scene in enumerate(scenes, start=1):
            _progress(emit, position - 1, total, scene.scene_id)
            run = presets.run_preset(
                scene,
                preset,
                self.config.output_dir,
                full_enabled=self.full_mode_enabled(),
                runner=self.bridge.metric_runner(),
                progress=lambda message: _log(emit, f"  {message}"),
            )
            runs.append(run)
            _progress(emit, position, total, scene.scene_id)

        self.config.preset = preset
        self.save_config()
        message = f"METRIC preset '{preset}' completed for {len(runs)} scene(s)"
        _log(emit, message)
        return SessionResult(message=message, preset_runs=runs)

    # ------------------------------------------------------------------
    # Output inspection
    # ------------------------------------------------------------------
    def output_summary(self) -> dict[str, Any]:
        output_dir = self.config.output_dir
        return {
            "output_dir": output_dir,
            "scenes": [str(path) for path in list_scene_dirs(output_dir)],
            "products": {
                name: [str(path) for path in paths]
                for name, paths in list_products(output_dir).items()
            },
        }

    def status_line(self, last_result: str = "") -> str:
        """Text for the status bar."""
        mode = "Full" if self.full_mode_enabled() else "Lite"
        parts = [f"Mode: {mode}", f"Satellite: {self.config.satellite}"]
        if self.roi is not None:
            parts.append(f"ROI: {self.roi.path.name}")
        if self.selected_count:
            parts.append(f"Selected: {self.selected_count}")
        if last_result:
            parts.append(last_result)
        return " | ".join(parts)

    def sentinel_only_notice(self, index_name: str) -> str | None:
        """Hint shown when a Sentinel-only index is requested for Landsat."""
        if (
            index_name.upper() in SENTINEL_ONLY_INDICES
            and self.config.satellite != SENTINEL2
        ):
            return f"{index_name.upper()} is only available for Sentinel-2 scenes"
        return None


__all__ = [
    "DownloadOptions",
    "DownloadResult",
    "Emit",
    "EngineBridge",
    "LiveEngineBridge",
    "Session",
    "SessionResult",
]

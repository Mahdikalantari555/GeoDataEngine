"""Output folder layout: ``<output>/scenes`` and ``<output>/products/<product>``.

Every product type gets its own folder with a ``metadata/`` sub-folder.  The
metadata JSON is written next to the GeoTIFF it describes but lives in the
``metadata/`` sub-folder, which keeps the raster folders clean enough to be
dragged straight into QGIS.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import METADATA_DIRNAME, PRODUCTS_DIRNAME, SCENES_DIRNAME


def scenes_dir(output_dir: Path | str) -> Path:
    return Path(output_dir) / SCENES_DIRNAME


def products_dir(output_dir: Path | str) -> Path:
    return Path(output_dir) / PRODUCTS_DIRNAME


def product_dir(output_dir: Path | str, product: str) -> Path:
    """Folder holding rasters of one product type.

    The caller decides the casing: basic indices pass ``"ndvi"`` while METRIC
    products pass the engine output name (``"ETaDaily"``), matching how each
    generator names its files.
    """
    return products_dir(output_dir) / sanitize_scene_id(product)


def product_metadata_dir(output_dir: Path | str, product: str) -> Path:
    return product_dir(output_dir, product) / METADATA_DIRNAME


def ensure_layout(output_dir: Path | str) -> dict[str, Path]:
    """Create the base layout and return the created folders."""
    base = Path(output_dir)
    scenes = scenes_dir(base)
    products = products_dir(base)
    scenes.mkdir(parents=True, exist_ok=True)
    products.mkdir(parents=True, exist_ok=True)
    return {"output": base, "scenes": scenes, "products": products}


def ensure_product_dirs(output_dir: Path | str, product: str) -> dict[str, Path]:
    """Create ``products/<product>`` and its ``metadata`` sub-folder."""
    raster_dir = product_dir(output_dir, product)
    meta_dir = product_metadata_dir(output_dir, product)
    raster_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    return {"raster": raster_dir, "metadata": meta_dir}


def product_raster_path(
    output_dir: Path | str,
    product: str,
    scene_id: str,
    *,
    multi_scene: bool = False,
) -> Path:
    """Path of the raster for ``product``/``scene_id``.

    Products are named ``<scene_id>.tif``.  When several indices are generated
    into the same folder (they are not — each has its own folder — but METRIC
    products can collide after sanitising) the product name is appended to keep
    the file unique.
    """
    ensure_product_dirs(output_dir, product)
    safe = sanitize_scene_id(scene_id)
    name = f"{safe}_{product.lower()}.tif" if multi_scene else f"{safe}.tif"
    return product_dir(output_dir, product) / name


def product_metadata_path(output_dir: Path | str, product: str, scene_id: str) -> Path:
    ensure_product_dirs(output_dir, product)
    return product_metadata_dir(output_dir, product) / f"{sanitize_scene_id(scene_id)}.json"


def sanitize_scene_id(scene_id: str) -> str:
    """Make a scene id safe to use as a file name on Windows and POSIX."""
    cleaned = "".join(
        ch if (ch.isalnum() or ch in "-_.") else "_" for ch in str(scene_id)
    ).strip("._")
    return cleaned or "scene"


def write_json_atomic(path: Path | str, payload: dict[str, Any]) -> Path:
    """Write ``payload`` as indented JSON without leaving half-written files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)
    return path


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_product_metadata(
    *,
    product: str,
    scene_id: str,
    scene_date: str,
    source_bands: list[str],
    crs: str | None = None,
    transform: Any = None,
    width: int | None = None,
    height: int | None = None,
    params: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the per-product metadata document."""
    payload: dict[str, Any] = {
        "product": product,
        "scene_id": scene_id,
        "date": scene_date,
        "source_bands": list(source_bands),
        "crs": str(crs) if crs is not None else None,
        "transform": list(transform)[:6] if transform is not None else None,
        "width": width,
        "height": height,
        "parameters": params or {},
        "created_utc": utc_timestamp(),
    }
    if extra:
        payload.update(extra)
    return payload


def write_product_metadata(
    output_dir: Path | str,
    product: str,
    scene_id: str,
    metadata: dict[str, Any],
) -> Path:
    return write_json_atomic(product_metadata_path(output_dir, product, scene_id), metadata)


def list_products(output_dir: Path | str) -> dict[str, list[Path]]:
    """Return ``{product: [raster paths]}`` for everything generated so far."""
    root = products_dir(output_dir)
    found: dict[str, list[Path]] = {}
    if not root.is_dir():
        return found
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        rasters = sorted(p for p in sub.glob("*.tif"))
        if rasters:
            found[sub.name] = rasters
    return found


def list_scene_dirs(output_dir: Path | str) -> list[Path]:
    """Return downloaded scene folders (those containing an ``MTL`` file)."""
    root = scenes_dir(output_dir)
    if not root.is_dir():
        return []
    scenes = []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if any(sub.glob("MTL*.json")):
            scenes.append(sub)
    return scenes


__all__ = [
    "build_product_metadata",
    "ensure_layout",
    "ensure_product_dirs",
    "list_products",
    "list_scene_dirs",
    "product_dir",
    "product_metadata_dir",
    "product_metadata_path",
    "product_raster_path",
    "products_dir",
    "sanitize_scene_id",
    "scenes_dir",
    "utc_timestamp",
    "write_json_atomic",
    "write_product_metadata",
]

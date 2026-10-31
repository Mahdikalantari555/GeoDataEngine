"""Framework-free core of the GeoDataEngine desktop GUI.

Every module in this package must stay importable without ``tkinter`` and
without the heavy scientific stack (scipy, pandas, xarray, rioxarray,
geopandas, fiona, matplotlib).  The tests in ``tests/gui`` enforce this.
"""

from __future__ import annotations

__all__: list[str] = []

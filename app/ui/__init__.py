"""Tkinter views for the GeoDataEngine desktop GUI.

Importing this package never imports ``tkinter``: the toolkit module is
resolved lazily by :func:`app.ui.toolkit.get_toolkit`, so the views
can be exercised with :class:`app.ui.toolkit.fake.FakeToolkit` on a machine
without Tk installed.
"""

from __future__ import annotations

__all__: list[str] = []

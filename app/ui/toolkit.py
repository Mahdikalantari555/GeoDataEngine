"""A deliberately thin abstraction over the widget toolkit.

The views are written against the small API below instead of importing
``tkinter`` directly.  Two implementations exist:

``TkToolkit``
    Real Tkinter widgets (``app.ui.toolkit`` lazily imports ``tkinter``; the
    desktop build always uses this).

``FakeToolkit`` (``app.ui.fake``)
    In-memory stand-ins that record what the UI asked for, so every view can
    be driven and asserted in tests on machines without a display server —
    which includes the CI sandbox this change was developed in.

Widget contract (implemented by both)::

    Widget.winfo_children() -> list[Widget]
    Widget.destroy() -> None

    Frame/Button/Label/Entry/Checkbutton/Combobox/Listbox/Scale/Text/Scrollbar
        standard construction, ``grid``/``pack``, ``configure``, ``get``/``set``
    Treeview.insert(parent, index, iid=..., values=..., text=...)
    Treeview.delete(*items)
    Treeview.selection() / selection_set(iid) / selection_remove(iid)
    Progressbar.set(value)          value in 0..1 or 0..maximum
    Messagebox / Filedialog style helpers are injected by the view, not the
    toolkit, so user prompts are plain callables that tests replace.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Widget(Protocol):
    """Common widget surface."""

    def winfo_children(self) -> list[Any]: ...

    def destroy(self) -> None: ...


class Toolkit(Protocol):
    """Factory used by the views to build widgets."""

    name: str

    def Frame(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Label(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Button(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Entry(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Checkbutton(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Combobox(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Listbox(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Treeview(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Progressbar(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Text(self, master: Any = None, **kwargs: Any) -> Any: ...

    def LabelFrame(self, master: Any = None, **kwargs: Any) -> Any: ...

    def Scale(self, master: Any = None, **kwargs: Any) -> Any: ...

    def after(self, delay_ms: int, callback: Any) -> Any: ...

    def schedule(self, delay_ms: int, callback: Any) -> Any: ...


def get_toolkit(toolkit: Any | None = None) -> Any:
    """Return ``toolkit`` or the real Tk toolkit, importing tkinter lazily."""
    if toolkit is not None:
        return toolkit
    try:
        from . import tk_toolkit  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - no Tk in this environment
        raise RuntimeError(
            "Tkinter is not available in this Python installation. "
            "Install the Tk bindings (e.g. 'apt install python3-tk') to run the GUI."
        ) from exc
    return tk_toolkit.TkToolkit()


__all__ = ["Toolkit", "Widget", "get_toolkit"]

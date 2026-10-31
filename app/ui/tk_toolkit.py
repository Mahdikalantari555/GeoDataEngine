"""Tkinter implementation of :class:`app.ui.toolkit.Toolkit`.

Unlike the rest of ``app.ui`` this module imports ``tkinter`` at import time,
which is why :func:`app.ui.toolkit.get_toolkit` imports it lazily.  The class
adds the handful of behaviours the views rely on that plain Tk widgets do not
provide (a uniform ``set``/``get`` on combobox and progress bars).
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox, ttk
from typing import Any

__all__ = ["TkToolkit", "TkWidget", "ask_open_file", "ask_directory", "show_info", "show_error"]


class TkWidget:
    """Wraps a Tk widget with the small extra surface the views use."""

    def __init__(self, widget: Any) -> None:
        self.widget = widget

    def __getattr__(self, item: str) -> Any:
        return getattr(self.widget, item)

    # -- geometry ------------------------------------------------------
    def grid(self, **kwargs: Any) -> TkWidget:
        self.widget.grid(**kwargs)
        return self

    def pack(self, **kwargs: Any) -> TkWidget:
        self.widget.pack(**kwargs)
        return self

    def grid_remove(self) -> None:
        self.widget.grid_remove()

    # -- options -------------------------------------------------------
    def configure(self, **kwargs: Any) -> None:
        self.widget.configure(**kwargs)

    config = configure

    def cget(self, key: str) -> Any:
        return self.widget.cget(key)

    def winfo_children(self) -> list[Any]:
        return list(self.widget.winfo_children())

    def destroy(self) -> None:
        self.widget.destroy()

    def after(self, delay_ms: int, callback: Callable[[], Any]) -> Any:
        return self.widget.after(delay_ms, callback)

    def focus_set(self) -> None:
        self.widget.focus_set()

    def bind(self, sequence: str, handler: Callable[[Any], Any]) -> None:
        self.widget.bind(sequence, handler)


class TkEntry(TkWidget):
    def get(self, *_args: Any) -> str:
        return str(self.widget.get())

    def set(self, value: Any) -> None:
        self.widget.delete(0, "end")
        self.widget.insert(0, str(value))

    def delete(self, first: Any = 0, last: Any = None) -> None:
        self.widget.delete(first, "end" if last is None else last)

    def insert(self, index: Any, value: Any) -> None:
        self.widget.insert(index, value)


class TkButton(TkWidget):
    def invoke(self) -> None:
        self.widget.invoke()

    def set_state(self, state: str) -> None:
        self.widget.configure(state=state)


class TkCombobox(TkWidget):
    def get(self) -> str:
        return str(self.widget.get())

    def set(self, value: Any) -> None:
        self.widget.set(str(value))

    def current(self) -> int:
        return int(self.widget.current())

    @property
    def values(self) -> list[str]:
        return list(self.widget.cget("values"))


class TkProgressbar(TkWidget):
    def set(self, value: float) -> None:
        self.widget.configure(value=value)

    def fraction(self) -> float:
        try:
            return float(self.widget.cget("value")) / max(1.0, float(self.widget.cget("maximum")))
        except (TypeError, ValueError):  # pragma: no cover - ttk cget quirk
            return 0.0


class TkStatusLabel(TkWidget):
    def set_text(self, text: str) -> None:
        self.widget.configure(text=text)


class TkToolkit:
    """Factory creating Tk widgets for the views."""

    name = "tk"

    def __init__(self, root: Any | None = None) -> None:
        self.root = root if root is not None else tk.Tk()

    # -- panels --------------------------------------------------------
    def Frame(self, master: Any = None, **kwargs: Any) -> TkWidget:
        return TkWidget(tk.Frame(_real(master) or self.root, **kwargs))

    def LabelFrame(self, master: Any = None, **kwargs: Any) -> TkWidget:
        return TkWidget(tk.LabelFrame(_real(master) or self.root, **kwargs))

    def Label(self, master: Any = None, **kwargs: Any) -> TkWidget:
        return TkWidget(tk.Label(_real(master) or self.root, **kwargs))

    def Button(self, master: Any = None, **kwargs: Any) -> TkButton:
        return TkButton(tk.Button(_real(master) or self.root, **kwargs))

    def Entry(self, master: Any = None, **kwargs: Any) -> TkEntry:
        text = kwargs.pop("text", None)
        entry = TkEntry(tk.Entry(_real(master) or self.root, **kwargs))
        if text:
            entry.set(text)
        return entry

    def Checkbutton(self, master: Any = None, **kwargs: Any) -> TkButton:
        return TkButton(tk.Checkbutton(_real(master) or self.root, **kwargs))

    def Combobox(self, master: Any = None, **kwargs: Any) -> TkCombobox:
        widget = ttk.Combobox(_real(master) or self.root, **kwargs)
        return TkCombobox(widget)

    def Listbox(self, master: Any = None, **kwargs: Any) -> TkWidget:
        return TkWidget(tk.Listbox(_real(master) or self.root, **kwargs))

    def Treeview(self, master: Any = None, **kwargs: Any) -> TkWidget:
        return TkWidget(ttk.Treeview(_real(master) or self.root, **kwargs))

    def Notebook(self, master: Any = None, **kwargs: Any) -> TkWidget:
        return TkWidget(ttk.Notebook(_real(master) or self.root, **kwargs))

    def Progressbar(self, master: Any = None, **kwargs: Any) -> TkProgressbar:
        kwargs.setdefault("maximum", 1.0)
        return TkProgressbar(ttk.Progressbar(_real(master) or self.root, **kwargs))

    def Text(self, master: Any = None, **kwargs: Any) -> TkWidget:
        return TkWidget(tk.Text(_real(master) or self.root, **kwargs))

    def Scale(self, master: Any = None, **kwargs: Any) -> TkWidget:
        return TkWidget(tk.Scale(_real(master) or self.root, **kwargs))

    def Menu(self, master: Any = None, **kwargs: Any) -> TkWidget:
        return TkWidget(tk.Menu(_real(master) or self.root, **kwargs))

    # -- variables -----------------------------------------------------
    def StringVar(self, value: Any = "") -> tk.StringVar:
        return tk.StringVar(value=str(value))

    def IntVar(self, value: Any = 0) -> tk.IntVar:
        return tk.IntVar(value=int(value))

    def DoubleVar(self, value: Any = 0.0) -> tk.DoubleVar:
        return tk.DoubleVar(value=float(value))

    def BooleanVar(self, value: Any = False) -> tk.BooleanVar:
        return tk.BooleanVar(value=bool(value))

    # -- timing --------------------------------------------------------
    def after(self, delay_ms: int, callback: Callable[[], Any]) -> Any:
        return self.root.after(delay_ms, callback)

    def schedule(self, delay_ms: int, callback: Callable[[], Any]) -> Any:
        return self.root.after(delay_ms, callback)

    # -- dialogs -------------------------------------------------------
    def ask_open_file(self, **kwargs: Any) -> str:
        return filedialog.askopenfilename(
            title=kwargs.get("title", "Select a file"),
            filetypes=kwargs.get(
                "filetypes",
                (
                    ("ROI files", "*.geojson *.json *.shp"),
                    ("GeoJSON", "*.geojson *.json"),
                    ("Shapefile", "*.shp"),
                    ("All files", "*.*"),
                ),
            ),
            parent=self.root,
        )

    def ask_directory(self, **kwargs: Any) -> str:
        return filedialog.askdirectory(
            title=kwargs.get("title", "Select a folder"), parent=self.root
        )

    def show_info(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message, parent=self.root)

    def show_error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=self.root)

    def show_warning(self, title: str, message: str) -> None:
        messagebox.showwarning(title, message, parent=self.root)

    def show_text_dialog(self, title: str, body: str) -> None:
        """Scrollable read-only dialog used by the Help button."""
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("820x600")
        text = tk.Text(window, wrap="word")
        scroll = ttk.Scrollbar(window, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", body)
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        ttk.Button(window, text="Close", command=window.destroy).pack(side="bottom")

    def mainloop(self) -> None:
        self.root.mainloop()


def _real(wrapped: Any) -> Any:
    if isinstance(wrapped, TkWidget):
        return wrapped.widget
    return wrapped


# Backwards-friendly module-level dialog helpers -----------------------------
def ask_open_file(parent: Any = None, **kwargs: Any) -> str:  # pragma: no cover
    return TkToolkit(parent).ask_open_file(**kwargs)


def ask_directory(parent: Any = None, **kwargs: Any) -> str:  # pragma: no cover
    return TkToolkit(parent).ask_directory(**kwargs)


def show_info(parent: Any = None, title: str = "", message: str = "") -> None:  # pragma: no cover
    TkToolkit(parent).show_info(title, message)


def show_error(parent: Any = None, title: str = "", message: str = "") -> None:  # pragma: no cover
    TkToolkit(parent).show_error(title, message)

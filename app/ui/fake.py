"""In-memory widget toolkit used by the GUI tests.

It mirrors the subset of Tkinter the views use, records every interaction, and
lets tests fire callbacks (``button.invoke()``, ``entry.insert``/``delete``,
``combobox.set``, …) without a display server or an event loop.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FakeWidget:
    """Base fake widget: geometry managers, options and children."""

    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        self.toolkit = toolkit
        self.master = master
        self.options: dict[str, Any] = dict(kwargs)
        self.children: list[FakeWidget] = []
        self.grid_calls: list[dict[str, Any]] = []
        self.pack_calls: list[dict[str, Any]] = []
        self.destroyed = False
        if master is not None and isinstance(master, FakeWidget):
            master.children.append(self)
        toolkit.created.append(self)

    # -- geometry ------------------------------------------------------
    def grid(self, **kwargs: Any) -> FakeWidget:
        self.grid_calls.append(dict(kwargs))
        return self

    def pack(self, **kwargs: Any) -> FakeWidget:
        self.pack_calls.append(dict(kwargs))
        return self

    def grid_remove(self) -> None:
        self.grid_calls.append({"removed": True})

    # -- options -------------------------------------------------------
    def configure(self, **kwargs: Any) -> None:
        self.options.update(kwargs)

    config = configure

    def cget(self, key: str) -> Any:
        return self.options.get(key)

    def winfo_children(self) -> list[FakeWidget]:
        return list(self.children)

    def destroy(self) -> None:
        self.destroyed = True
        if isinstance(self.master, FakeWidget) and self in self.master.children:
            self.master.children.remove(self)

    def after(self, delay_ms: int, callback: Callable[[], Any]) -> str:
        return self.toolkit.schedule(delay_ms, callback)

    def focus_set(self) -> None:  # pragma: no cover - focus is a no-op in tests
        self.options["focused"] = True


class FakeLabel(FakeWidget):
    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.text = kwargs.get("text", "")

    def configure(self, **kwargs: Any) -> None:
        super().configure(**kwargs)
        if "text" in kwargs:
            self.text = kwargs["text"]

    config = configure


class FakeEntry(FakeWidget):
    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self._value = str(kwargs.get("textvariable_value", ""))

    def get(self) -> str:
        return self._value

    def set(self, value: Any) -> None:
        self._value = str(value)

    def insert(self, index: Any, value: Any) -> None:
        self._value = str(value) if index in (0, "0") else self._value + str(value)

    def delete(self, first: Any = 0, last: Any = None) -> None:
        self._value = ""

    def variable_value(self) -> str:
        return self._value


class FakeVar:
    """Mimics ``tkinter.StringVar``/``BooleanVar``/``DoubleVar``."""

    def __init__(self, toolkit: FakeToolkit, value: Any = "") -> None:
        self.toolkit = toolkit
        self._value = value

    def get(self) -> Any:
        return self._value

    def set(self, value: Any) -> None:
        self._value = value


class FakeButton(FakeWidget):
    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.text = kwargs.get("text", "")
        self.state: str = kwargs.get("state", "normal")
        self.invocations = 0

    @property
    def command(self) -> Callable[[], Any] | None:
        return self.options.get("command")

    def invoke(self) -> Any:
        if self.state == "disabled":
            return None
        self.invocations += 1
        command = self.options.get("command")
        return command() if command else None

    def configure(self, **kwargs: Any) -> None:
        super().configure(**kwargs)
        if "state" in kwargs:
            self.state = kwargs["state"]
        if "text" in kwargs:
            self.text = kwargs["text"]

    config = configure


class FakeCheckbutton(FakeButton):
    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.selected = bool(kwargs.get("selected", False))

    def select(self) -> None:
        self.selected = True
        self.options["variable"].set(True) if "variable" in self.options else None

    def deselect(self) -> None:
        self.selected = False
        self.options["variable"].set(False) if "variable" in self.options else None

    def toggle(self) -> bool:
        if self.selected:
            self.deselect()
        else:
            self.select()
        return self.selected


class FakeCombobox(FakeWidget):
    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.values: list[str] = list(kwargs.get("values") or [])
        self._value = str(kwargs.get("value", ""))

    def get(self) -> str:
        return self._value

    def set(self, value: Any) -> None:
        self._value = str(value)

    def current(self) -> int:
        try:
            return self.values.index(self._value)
        except ValueError:
            return -1

    def bind_selected(self, handler: Callable[[Any], Any]) -> None:
        self.options["bind_selected"] = handler
        if self._value:
            handler(FakeEvent(self._value))


class FakeListbox(FakeWidget):
    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.items: list[str] = []
        self.selected: set[int] = set()

    def insert(self, index: Any, item: str) -> None:
        self.items.append(str(item))

    def delete(self, first: Any, last: Any = None) -> None:
        self.items.clear()
        self.selected.clear()

    def size(self) -> int:
        return len(self.items)

    def get(self, index: int) -> str:
        return self.items[index]

    def selection_set(self, index: int) -> None:
        self.selected = {int(index)}

    def selection_clear(self, first: Any = 0, last: Any = None) -> None:
        self.selected.clear()

    def curselection(self) -> tuple[int, ...]:
        return tuple(sorted(self.selected))

    def activate(self, index: int) -> None:
        self.selection_set(index)
        handler = self.options.get("bind_selected")
        if handler:
            handler(FakeEvent(self.items[index]))


class FakeTreeview(FakeWidget):
    """``ttk.Treeview`` replacement with item storage and selection."""

    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.columns: list[str] = list(kwargs.get("columns") or [])
        self.items: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        self._selection: set[str] = set()
        self.column_specs: dict[str, dict[str, Any]] = {}
        self.headings: dict[str, dict[str, Any]] = {}
        self.bindings: dict[str, Callable[[Any], Any]] = {}

    def column(self, name: str, **kwargs: Any) -> None:
        self.column_specs[name] = dict(kwargs)

    def heading(self, name: str, **kwargs: Any) -> None:
        self.headings[name] = dict(kwargs)

    def insert(self, parent: str, index: Any, *, iid: str | None = None, **kwargs: Any) -> str:
        key = iid or f"I{len(self.order) + 1:03d}"
        self.items[key] = dict(kwargs)
        self.order.append(key)
        return key

    def delete(self, *items: str) -> None:
        for key in items:
            if key in self.items:
                self.items.pop(key)
            if key in self.order:
                self.order.remove(key)
            self._selection.discard(key)

    def get_children(self) -> tuple[str, ...]:
        return tuple(self.order)

    def selection(self) -> tuple[str, ...]:
        return tuple(key for key in self.order if key in self._selection)

    def selection_set(self, *items: str) -> None:
        for key in items:
            if key in self.items:
                self._selection.add(key)

    def selection_remove(self, *items: str) -> None:
        for key in items:
            self._selection.discard(key)

    def selection_toggle(self, *items: str) -> None:
        for key in items:
            if key in self._selection:
                self._selection.discard(key)
            else:
                self._selection.add(key)

    def item(self, key: str, **kwargs: Any) -> dict[str, Any]:
        if kwargs:
            self.items.setdefault(key, {}).update(kwargs)
        return self.items.get(key, {})

    def bind(self, sequence: str, handler: Callable[[Any], Any]) -> None:
        self.bindings[sequence] = handler

    def values_of(self, key: str) -> tuple[Any, ...]:
        raw = self.items.get(key, {}).get("values", ())
        return tuple(raw)


class FakeNotebook(FakeWidget):
    """``ttk.Notebook`` replacement recording tab titles."""

    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.tabs_added: list[tuple[FakeWidget, str]] = []
        self.selected_index = 0

    def add(self, child: FakeWidget, text: str = "") -> None:
        self.tabs_added.append((child, text))

    def tabs(self) -> tuple[FakeWidget, ...]:
        return tuple(child for child, _text in self.tabs_added)

    def tab_titles(self) -> list[str]:
        return [text for _child, text in self.tabs_added]

    def select(self, index: int) -> None:
        self.selected_index = int(index)

    def index(self, child: Any) -> int:
        for position, (candidate, _text) in enumerate(self.tabs_added):
            if candidate is child:
                return position
        return -1


class FakeMenu(FakeWidget):
    """``tk.Menu`` replacement recording added commands."""

    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.commands: dict[str, Callable[[], Any]] = {}

    def add_command(self, *, label: str, command: Callable[[], Any]) -> None:
        self.commands[label] = command

    def add_cascade(self, *, label: str, menu: Any) -> None:
        self.commands[label] = menu

    def invoke(self, label: str) -> Any:
        command = self.commands.get(label)
        return command() if command else None


class FakeProgressbar(FakeWidget):
    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.maximum = float(kwargs.get("maximum", 100))
        self.value = float(kwargs.get("value", 0))
        self.history: list[float] = []

    def set(self, value: float) -> None:
        self.value = float(value)
        self.history.append(self.value)

    def configure(self, **kwargs: Any) -> None:
        super().configure(**kwargs)
        if "maximum" in kwargs:
            self.maximum = float(kwargs["maximum"])
        if "value" in kwargs:
            self.value = float(kwargs["value"])

    config = configure

    def fraction(self) -> float:
        return 0.0 if self.maximum <= 0 else max(0.0, min(1.0, self.value / self.maximum))


class FakeText(FakeWidget):
    def __init__(self, toolkit: FakeToolkit, master: Any = None, **kwargs: Any) -> None:
        super().__init__(toolkit, master, **kwargs)
        self.content = ""
        self.tags: list[str] = []

    def insert(self, index: Any, text: str, *tags: str) -> None:
        self.content += text
        self.tags.extend(tags)

    def delete(self, first: Any, last: Any = None) -> None:
        self.content = ""

    def get(self, first: Any = "1.0", last: Any = "end-1c") -> str:
        return self.content

    def see(self, index: Any) -> None:
        self.options["seen"] = index

    def yview(self, *args: Any) -> None:
        self.options["yview"] = args

    def bind(self, sequence: str, handler: Callable[[Any], Any]) -> None:
        self.options[f"bind:{sequence}"] = handler


class FakeEvent:
    def __init__(self, value: Any = None) -> None:
        self.value = value
        self.widget = None


class FakeToolkit:
    """Toolkit factory that records every widget it creates."""

    name = "fake"

    def __init__(self) -> None:
        self.created: list[FakeWidget] = []
        self.scheduled: list[tuple[int, Callable[[], Any]]] = []
        self.streams: list[Any] = []
        # dialog responses / recordings
        self.next_file = ""
        self.next_directory = ""
        self.info_calls: list[tuple[str, str]] = []
        self.error_calls: list[tuple[str, str]] = []
        self.warning_calls: list[tuple[str, str]] = []
        self.dialogs: list[tuple[str, str]] = []

    # -- panels --------------------------------------------------------
    def Frame(self, master: Any = None, **kwargs: Any) -> FakeWidget:
        return FakeWidget(self, master, **kwargs)

    def LabelFrame(self, master: Any = None, **kwargs: Any) -> FakeWidget:
        return FakeWidget(self, master, **kwargs)

    def Label(self, master: Any = None, **kwargs: Any) -> FakeLabel:
        return FakeLabel(self, master, **kwargs)

    def Button(self, master: Any = None, **kwargs: Any) -> FakeButton:
        return FakeButton(self, master, **kwargs)

    def Entry(self, master: Any = None, **kwargs: Any) -> FakeEntry:
        return FakeEntry(self, master, **kwargs)

    def Checkbutton(self, master: Any = None, **kwargs: Any) -> FakeCheckbutton:
        return FakeCheckbutton(self, master, **kwargs)

    def Combobox(self, master: Any = None, **kwargs: Any) -> FakeCombobox:
        return FakeCombobox(self, master, **kwargs)

    def Listbox(self, master: Any = None, **kwargs: Any) -> FakeListbox:
        return FakeListbox(self, master, **kwargs)

    def Treeview(self, master: Any = None, **kwargs: Any) -> FakeTreeview:
        return FakeTreeview(self, master, **kwargs)

    def Progressbar(self, master: Any = None, **kwargs: Any) -> FakeProgressbar:
        return FakeProgressbar(self, master, **kwargs)

    def Notebook(self, master: Any = None, **kwargs: Any) -> FakeNotebook:
        return FakeNotebook(self, master, **kwargs)

    def Menu(self, master: Any = None, **kwargs: Any) -> FakeMenu:
        return FakeMenu(self, master, **kwargs)

    def Scrollbar(self, master: Any = None, **kwargs: Any) -> FakeWidget:
        return FakeWidget(self, master, **kwargs)

    def Text(self, master: Any = None, **kwargs: Any) -> FakeText:
        return FakeText(self, master, **kwargs)

    def Scale(self, master: Any = None, **kwargs: Any) -> FakeWidget:
        return FakeWidget(self, master, **kwargs)

    # -- variables / timing --------------------------------------------
    def StringVar(self, value: Any = "") -> FakeVar:
        return FakeVar(self, value)

    def IntVar(self, value: Any = 0) -> FakeVar:
        return FakeVar(self, value)

    def DoubleVar(self, value: Any = 0.0) -> FakeVar:
        return FakeVar(self, value)

    def BooleanVar(self, value: Any = False) -> FakeVar:
        return FakeVar(self, value)

    def after(self, delay_ms: int, callback: Callable[[], Any]) -> str:
        return self.schedule(delay_ms, callback)

    def schedule(self, delay_ms: int, callback: Callable[[], Any]) -> str:
        self.scheduled.append((delay_ms, callback))
        return f"after#{len(self.scheduled)}"

    def run_pending(self, limit: int = 50) -> int:
        """Run scheduled callbacks (the test-side equivalent of ``mainloop``)."""
        runs = 0
        while self.scheduled and runs < limit:
            _delay, callback = self.scheduled.pop(0)
            callback()
            runs += 1
        return runs

    # -- dialogs -------------------------------------------------------
    def ask_open_file(self, **_kwargs: Any) -> str:
        return self.next_file

    def ask_directory(self, **_kwargs: Any) -> str:
        return self.next_directory

    def show_info(self, title: str, message: str) -> None:
        self.info_calls.append((title, message))

    def show_error(self, title: str, message: str) -> None:
        self.error_calls.append((title, message))

    def show_warning(self, title: str, message: str) -> None:
        self.warning_calls.append((title, message))

    def show_text_dialog(self, title: str, body: str) -> None:
        self.dialogs.append((title, body))

    # -- helpers -------------------------------------------------------
    def widgets(self, kind: type[FakeWidget]) -> list[FakeWidget]:
        return [widget for widget in self.created if isinstance(widget, kind)]

    def find_button(self, text: str) -> FakeButton | None:
        for widget in self.created:
            if isinstance(widget, FakeButton) and widget.text == text:
                return widget
        return None

    def find_treeview(self) -> FakeTreeview | None:
        for widget in self.created:
            if isinstance(widget, FakeTreeview):
                return widget
        return None

    def find_text(self) -> FakeText | None:
        for widget in self.created:
            if isinstance(widget, FakeText):
                return widget
        return None

    def find_notebook(self) -> FakeNotebook | None:
        for widget in self.created:
            if isinstance(widget, FakeNotebook):
                return widget
        return None

    def find_menu(self) -> FakeMenu | None:
        for widget in self.created:
            if isinstance(widget, FakeMenu):
                return widget
        return None


__all__ = [
    "FakeButton",
    "FakeCheckbutton",
    "FakeCombobox",
    "FakeEntry",
    "FakeEvent",
    "FakeLabel",
    "FakeListbox",
    "FakeMenu",
    "FakeNotebook",
    "FakeProgressbar",
    "FakeText",
    "FakeToolkit",
    "FakeTreeview",
    "FakeVar",
    "FakeWidget",
]

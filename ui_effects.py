"""Small, finite Tk animations that keep native ttk keyboard and state behavior."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from time import monotonic
import tkinter as tk
from tkinter import ttk
from typing import Callable, Mapping


@dataclass
class _Animation:
    after_id: str | None = None


class Animator:
    """Run cubic ease-out transitions; a new animation replaces the same key.

    Callbacks receive an eased progress from 0 to 1. Destroying the owning
    widget cancels its scheduled frames, and completed animations stop ticking.
    """

    def __init__(self, widget: tk.Misc) -> None:
        self.widget = widget
        self._animations: dict[str, _Animation] = {}
        self._destroyed = False
        widget.bind("<Destroy>", self._on_destroy, add="+")

    def _exists(self) -> bool:
        if self._destroyed:
            return False
        try:
            return bool(self.widget.winfo_exists())
        except tk.TclError:
            return False

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self.widget:
            self._destroyed = True
            self.cancel()

    def cancel(self, key: str | None = None) -> None:
        """Cancel one transition, or every transition owned by this controller."""
        keys = list(self._animations) if key is None else [key]
        for name in keys:
            animation = self._animations.pop(name, None)
            if animation is not None and animation.after_id is not None:
                try:
                    self.widget.after_cancel(animation.after_id)
                except tk.TclError:
                    pass

    def animate(
        self,
        key: str,
        duration_ms: int,
        update: Callable[[float], None],
        complete: Callable[[], None] | None = None,
        easing: Callable[[float], float] | None = None,
    ) -> None:
        self.cancel(key)
        if not self._exists():
            return
        animation = _Animation()
        self._animations[key] = animation
        started = monotonic()

        def frame(first: bool = False) -> None:
            if self._animations.get(key) is not animation:
                return
            animation.after_id = None
            if not self._exists():
                self.cancel(key)
                return
            progress = (
                1.0 if duration_ms <= 0
                else 0.0 if first
                else min(1.0, (monotonic() - started) * 1000 / duration_ms)
            )
            try:
                update(easing(progress) if easing else 1.0 - (1.0 - progress) ** 3)
            except tk.TclError:
                self.cancel(key)
                if self._exists():
                    raise
                return
            # An update may destroy its widget or replace this animation.
            if self._animations.get(key) is not animation:
                return
            if not self._exists():
                self.cancel(key)
                return
            if progress >= 1.0:
                self._animations.pop(key, None)
                if complete is not None:
                    complete()
                return
            animation.after_id = self.widget.after(16, frame)

        frame(first=True)


def mix_color(widget: tk.Misc, start: str, end: str, progress: float) -> str:
    """Interpolate any two colors understood by Tk, returning a hex color."""
    amount = max(0.0, min(1.0, progress))
    left = widget.winfo_rgb(start)
    right = widget.winfo_rgb(end)
    return "#" + "".join(
        f"{round((a + (b - a) * amount) / 257):02x}"
        for a, b in zip(left, right)
    )


def spring_out(progress: float) -> float:
    """A restrained overshoot that settles exactly on the target."""
    t = progress - 1.0
    return 1.0 + 2.6 * t ** 3 + 1.6 * t ** 2


def _window_rect(window: tk.Tk | tk.Toplevel) -> tuple[int, int, int, int]:
    return window.winfo_width(), window.winfo_height(), window.winfo_x(), window.winfo_y()


def animate_window_open(
    window: tk.Tk | tk.Toplevel, duration_ms: int = 260,
) -> Animator:
    """Pop into place using size and position, with full opacity throughout.

    Schedule after constructing the window; desired geometry and contents can
    still be set before the event loop. A small overshoot supplies the spring.
    """
    window.withdraw()
    animator = Animator(window)
    window._window_motion = animator
    window._motion_closing = False

    def prepare() -> None:
        if not animator._exists() or window._motion_closing:
            return
        window.update_idletasks()
        width, height, _, _ = _window_rect(window)
        width = max(width, window.winfo_reqwidth())
        height = max(height, window.winfo_reqheight())
        minimum = window.minsize()
        width, height = max(width, minimum[0]), max(height, minimum[1])
        parent = window.master.winfo_toplevel() if window.master else None
        if parent is not None and parent.winfo_ismapped():
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        else:
            x = (window.winfo_screenwidth() - width) // 2
            y = (window.winfo_screenheight() - height) // 2 - 24
        x, y = max(0, x), max(0, y)
        window.minsize(1, 1)

        def position(progress: float) -> None:
            scale = 0.92 + 0.08 * progress
            w, h = round(width * scale), round(height * scale)
            left = x + (width - w) // 2
            top = y + (height - h) // 2 + round(18 * (1 - progress))
            window.geometry(f"{w}x{h}+{left}+{top}")

        def finish() -> None:
            window.geometry(f"{width}x{height}+{x}+{y}")
            window.minsize(*minimum)

        position(0)
        window.deiconify()
        animator.animate("window", duration_ms, position, finish, easing=spring_out)

    # Leave the first idle pass before measuring: Tk can defer geometry changes
    # made after this helper until that pass has finished (notably on Windows).
    window.after_idle(lambda: window.after(0, prepare))
    return animator


def animate_window_close(window: tk.Tk | tk.Toplevel, duration_ms: int = 150) -> None:
    """Shrink slightly toward the centre and slide down before closing."""
    if getattr(window, "_motion_closing", False):
        return
    window._motion_closing = True
    animator = getattr(window, "_window_motion", None) or Animator(window)
    animator.cancel()
    if not window.winfo_ismapped():
        window.destroy()
        return
    width, height, x, y = _window_rect(window)
    window.minsize(1, 1)

    def position(progress: float) -> None:
        scale = 1.0 - 0.055 * progress
        w, h = round(width * scale), round(height * scale)
        window.geometry(f"{w}x{h}+{x + (width-w)//2}+{y + (height-h)//2 + round(14*progress)}")

    animator.animate("window", duration_ms, position, window.destroy, easing=lambda p: p * p)


_button_ids = count(1)


class AnimatedButton(ttk.Button):
    """A ttk button with a short hover transition and native press/focus behavior.

    All ordinary ttk options work, including style and command. Colors default
    to the supplied style's normal/active/pressed/disabled backgrounds. Optional
    ``palette`` overrides use those four keys, with ``hover`` for active.
    """

    def __init__(
        self,
        master: tk.Misc | None = None,
        *,
        animation_ms: int = 120,
        palette: Mapping[str, str] | None = None,
        **kwargs,
    ) -> None:
        self._motion_style = ttk.Style(master)
        self._motion_id = next(_button_ids)
        self._palette_overrides = dict(palette or {})
        self._animation_ms = animation_ms
        self._hovered = False
        base_style = str(kwargs.pop("style", "TButton") or "TButton")
        self._install_style(base_style)
        super().__init__(master, style=self._animated_style, **kwargs)
        self._animator = Animator(self)
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")

    def _install_style(self, base_style: str) -> None:
        self._base_style = base_style
        self._animated_style = f"MotionButton{self._motion_id}.{base_style}"
        lookup = self._motion_style.lookup
        normal = str(lookup(base_style, "background") or "#F0F0F0")
        self._palette = {
            "normal": normal,
            "hover": str(lookup(base_style, "background", ("active",)) or normal),
            "pressed": str(lookup(base_style, "background", ("pressed",)) or normal),
            "disabled": str(lookup(base_style, "background", ("disabled",)) or normal),
        }
        self._palette.update(self._palette_overrides)
        self._set_background(self._palette["normal"])

    def _set_background(self, color: str) -> None:
        self._current_background = color
        self._motion_style.configure(self._animated_style, background=color)
        # A per-button map prevents the parent's active color from bypassing
        # interpolation; other options (foreground, focus, padding) inherit.
        self._motion_style.map(
            self._animated_style,
            background=[
                ("disabled", self._palette["disabled"]),
                ("pressed", self._palette["pressed"]),
                ("!disabled", color),
            ],
        )

    def _sync_visual(self, *, immediate: bool = False) -> None:
        self._animator.cancel("hover")
        disabled = self.instate(("disabled",))
        target = self._palette["hover" if self._hovered and not disabled else "normal"]
        if disabled or immediate or target == self._current_background:
            self._set_background(target)
            return
        start = self._current_background
        self._animator.animate(
            "hover", self._animation_ms,
            lambda progress: self._set_background(mix_color(self, start, target, progress)),
        )

    def _enter(self, _event: tk.Event) -> None:
        self._hovered = True
        self._sync_visual()

    def _leave(self, _event: tk.Event) -> None:
        self._hovered = False
        self._sync_visual()

    def state(self, statespec=None):
        result = super().state(statespec)
        if statespec is not None and hasattr(self, "_animator"):
            self._sync_visual(immediate=True)
        return result

    def configure(self, cnf=None, **kwargs):
        # Keep normal Tk option queries intact; normalize only update mappings.
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
            cnf = None
        style_changed = "style" in kwargs and kwargs["style"] != self._animated_style
        if style_changed:
            if hasattr(self, "_animator"):
                self._animator.cancel("hover")
            self._install_style(str(kwargs["style"] or "TButton"))
            kwargs["style"] = self._animated_style
        result = super().configure(cnf, **kwargs)
        if (style_changed or "state" in kwargs) and hasattr(self, "_animator"):
            self._sync_visual(immediate=True)
        return result

    config = configure

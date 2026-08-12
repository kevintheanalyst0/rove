"""Salida por consola: cabeceras, fases, barras de progreso y estados.

Es la misma consola que ya usabas (misma API), solo limpiada. Se mantiene
en lugar de una librería externa porque es autocontenida y funciona bien.
"""

from __future__ import annotations


class Console:

    def __init__(self, debug: bool = False, colors: bool = True):
        self.debug_enabled = debug
        self.colors = colors

        self.width = 80
        self.progress_active = False

        self.reset = "\033[0m"
        self.blue = "\033[38;5;39m"
        self.cyan = "\033[38;5;51m"
        self.green = "\033[38;5;46m"
        self.yellow = "\033[38;5;220m"
        self.red = "\033[38;5;196m"
        self.gray = "\033[38;5;245m"

    def _line(self) -> str:
        return "═" * self.width

    def _print(self, text: str = "", color: str | None = None) -> None:
        if self.progress_active:
            print()
            self.progress_active = False
        if color and self.colors:
            print(f"{color}{text}{self.reset}")
        else:
            print(text)

    def blank(self) -> None:
        self._print()

    def header(self, title: str, icon: str = "🚀") -> None:
        self._print(self._line())
        self._print(f"{icon}  {title}", self.blue)
        self._print(self._line())

    def phase(self, title: str, icon: str = "📌") -> None:
        self.blank()
        self._print(f"{icon}  {title}", self.cyan)
        self.blank()

    def status(self, label: str, value: str | int | None = None) -> None:
        if value is None:
            self._print(f"   ✓ {label}")
            return
        self._print(f"   ✓ {label:<35}{str(value):>12}")

    def step(self, message: str) -> None:
        self._print(f"   {message}")

    def info(self, message: str) -> None:
        self._print(f"ℹ  {message}", self.gray)

    def success(self, message: str) -> None:
        self._print(f"✅ {message}", self.green)

    def warning(self, message: str) -> None:
        self._print(f"⚠  {message}", self.yellow)

    def error(self, message: str) -> None:
        self._print(f"❌ {message}", self.red)

    def progress(self, current: int, total: int, title: str = "") -> None:
        if total <= 0:
            total = 1

        percent = current / total
        bar_size = 36
        filled = int(bar_size * percent)
        bar = "█" * filled + "░" * (bar_size - filled)

        if title:
            text = f"\r{title:<26}▕{bar}▏ {current}/{total} ({percent * 100:3.0f}%)"
        else:
            text = f"\r▕{bar}▏ {current}/{total} ({percent * 100:3.0f}%)"

        self.progress_active = True
        print(text, end="", flush=True)

        if current >= total:
            print()
            self.progress_active = False

    def completed(self, process: str) -> None:
        self.blank()
        self._print(f"✅ {process} completed", self.green)

    def debug(self, message: str) -> None:
        if not self.debug_enabled:
            return
        self._print(f"[DEBUG] {message}")


console = Console()

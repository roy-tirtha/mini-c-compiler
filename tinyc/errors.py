"""Error / warning handling shared by every compiler phase.

Design: phases never print anything themselves.  They report problems to a
single ErrorReporter and keep going where possible, so the user sees *many*
problems in one run (like gcc/clang) instead of only the first one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Diagnostic:
    """A single message (error or warning) tied to a place in the source."""

    severity: Severity
    phase: str                 # "lexical" | "syntax" | "semantic"
    message: str
    line: int
    col: int
    length: int = 1            # how many characters to underline
    hint: Optional[str] = None  # optional "did you mean ...?" style advice


class TinyCRuntimeError(Exception):
    """Raised while *executing* a compiled program (e.g. division by zero)."""

    def __init__(self, message: str, line: int = 0):
        super().__init__(message)
        self.message = message
        self.line = line


# ANSI colour codes used only when the output is a real terminal.
_COLORS = {"red": "31;1", "yellow": "33;1", "blue": "34;1", "cyan": "36", "bold": "1"}


def _paint(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{_COLORS[color]}m{text}\033[0m"


class ErrorReporter:
    """Collects diagnostics from all phases and renders them nicely."""

    MAX_ERRORS = 25  # stop recording after this many to avoid error floods

    def __init__(self) -> None:
        self.diagnostics: List[Diagnostic] = []
        self._suppressed = 0

    # ---- recording --------------------------------------------------
    def error(self, phase: str, message: str, line: int, col: int,
              length: int = 1, hint: Optional[str] = None) -> None:
        if len(self.errors) >= self.MAX_ERRORS:
            self._suppressed += 1
            return
        self.diagnostics.append(
            Diagnostic(Severity.ERROR, phase, message, line, col, length, hint))

    def warning(self, phase: str, message: str, line: int, col: int,
                length: int = 1, hint: Optional[str] = None) -> None:
        self.diagnostics.append(
            Diagnostic(Severity.WARNING, phase, message, line, col, length, hint))

    # ---- queries ----------------------------------------------------
    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity is Severity.ERROR]

    @property
    def warnings(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity is Severity.WARNING]

    @property
    def has_errors(self) -> bool:
        return any(d.severity is Severity.ERROR for d in self.diagnostics)

    # ---- rendering --------------------------------------------------
    def render(self, source: str, filename: str = "<stdin>", color: bool = False) -> str:
        """Return all diagnostics as human-readable text with source snippets."""
        lines = source.splitlines()
        out: List[str] = []

        for d in sorted(self.diagnostics, key=lambda x: (x.line, x.col)):
            kind_color = "red" if d.severity is Severity.ERROR else "yellow"
            head = _paint(f"{d.severity.value}[{d.phase}]", kind_color, color)
            out.append(f"{head}: {_paint(d.message, 'bold', color)}")

            width = len(str(d.line))
            pad = " " * width
            out.append(f"{pad}{_paint('-->', 'blue', color)} {filename}:{d.line}:{d.col}")

            if 1 <= d.line <= len(lines):
                text = lines[d.line - 1]
                # Keep tabs as tabs so the caret lines up under the right column.
                indent = "".join("\t" if ch == "\t" else " " for ch in text[: d.col - 1])
                # Never underline past the end of the line.
                span = max(1, min(d.length, max(len(text) - (d.col - 1), 1)))
                out.append(f"{pad} {_paint('|', 'blue', color)}")
                out.append(f"{_paint(str(d.line), 'blue', color)} {_paint('|', 'blue', color)} {text}")
                out.append(f"{pad} {_paint('|', 'blue', color)} {indent}"
                           f"{_paint('^' * span, kind_color, color)}")
            if d.hint:
                out.append(f"{pad} {_paint('= hint:', 'cyan', color)} {d.hint}")
            out.append("")

        n_err, n_warn = len(self.errors), len(self.warnings)
        parts = []
        if n_err:
            parts.append(f"{n_err} error{'s' if n_err != 1 else ''}")
        if n_warn:
            parts.append(f"{n_warn} warning{'s' if n_warn != 1 else ''}")
        if parts:
            out.append(" and ".join(parts) + " generated.")
        if self._suppressed:
            out.append(f"... {self._suppressed} more error(s) not shown.")
        return "\n".join(out)

    def render_runtime(self, err: TinyCRuntimeError, color: bool = False) -> str:
        where = f" (line {err.line})" if err.line else ""
        return f"{_paint('runtime error', 'red', color)}: {err.message}{where}"

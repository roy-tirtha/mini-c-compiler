"""Symbol table: remembers every declared variable and its scope.

Scopes form a stack.  Entering a `{ }` block pushes a new scope; leaving pops
it.  Looking a name up searches from the innermost scope outwards, which gives
correct C-style shadowing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Symbol:
    name: str
    type: str                 # "int" | "float"
    line: int                 # where it was declared
    col: int
    unique_name: str          # name used in generated code (x, x.1, x.2 ...)
    initialized: bool = False  # has it been given a value yet?
    used: bool = False         # has its value ever been read?
    warned_uninit: bool = False  # so we warn only once per variable


class SymbolTable:
    def __init__(self) -> None:
        self._scopes: List[Dict[str, Symbol]] = [{}]   # index 0 = global scope
        self._name_counts: Dict[str, int] = {}          # for unique_name generation

    # ---- scope management ------------------------------------------
    def enter_scope(self) -> None:
        self._scopes.append({})

    def exit_scope(self) -> List[Symbol]:
        """Pop the innermost scope and return its symbols (for unused-var checks)."""
        return list(self._scopes.pop().values())

    @property
    def depth(self) -> int:
        return len(self._scopes)

    # ---- declaring & looking up ------------------------------------
    def declare(self, name: str, type_: str, line: int, col: int) -> Symbol:
        """Create a symbol in the current scope.

        Two variables may share a name in different scopes (shadowing), but the
        code generator needs distinct names, so we give each a unique_name.
        """
        count = self._name_counts.get(name, 0)
        self._name_counts[name] = count + 1
        unique = name if count == 0 else f"{name}.{count}"
        sym = Symbol(name, type_, line, col, unique)
        self._scopes[-1][name] = sym
        return sym

    def lookup_current(self, name: str) -> Optional[Symbol]:
        """Find a name in the *current* scope only (detects redeclaration)."""
        return self._scopes[-1].get(name)

    def lookup(self, name: str) -> Optional[Symbol]:
        """Find a name, searching innermost scope first."""
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return None

    def visible_names(self) -> List[str]:
        """All names currently visible (used for 'did you mean' suggestions)."""
        names = set()
        for scope in self._scopes:
            names.update(scope.keys())
        return sorted(names)

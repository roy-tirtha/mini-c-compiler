"""Abstract Syntax Tree (AST) node definitions.

The parser builds a tree of these objects.  Later phases (semantic analysis,
code generation) walk the tree.  Every node remembers its line/column so
errors can point at the right place.

Two fields are filled in *later* by the semantic analyzer:
  * resolved_type : the type of an expression ("int" / "float" / "string")
  * symbol        : the Symbol a name refers to (see symbol_table.py)
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, List, Optional


@dataclass
class Node:
    """Base class: every node knows where it came from in the source."""
    line: int
    col: int


# =====================================================================
# Expressions  (things that produce a value)
# =====================================================================
@dataclass
class Expr(Node):
    # init=False -> not a constructor argument; set later by the analyzer.
    resolved_type: Optional[str] = field(default=None, init=False, repr=False)


@dataclass
class IntLiteral(Expr):
    value: int


@dataclass
class FloatLiteral(Expr):
    value: float


@dataclass
class StringLiteral(Expr):
    value: str


@dataclass
class Identifier(Expr):
    name: str
    symbol: Any = field(default=None, init=False, repr=False)


@dataclass
class BinaryOp(Expr):
    op: str            # + - * / % < <= > >= == != && ||
    left: Expr
    right: Expr


@dataclass
class UnaryOp(Expr):
    op: str            # '-' or '!'
    operand: Expr


# =====================================================================
# Statements  (things that *do* something)
# =====================================================================
@dataclass
class Stmt(Node):
    pass


@dataclass
class VarDecl(Stmt):
    var_type: str                      # "int" | "float"
    name: str
    initializer: Optional[Expr]
    symbol: Any = field(default=None, init=False, repr=False)


@dataclass
class Assign(Stmt):
    name: str
    value: Expr
    symbol: Any = field(default=None, init=False, repr=False)


@dataclass
class Block(Stmt):
    statements: List[Stmt]


@dataclass
class If(Stmt):
    condition: Expr
    then_branch: Stmt
    else_branch: Optional[Stmt]


@dataclass
class While(Stmt):
    condition: Expr
    body: Stmt


@dataclass
class For(Stmt):
    init: Optional[Stmt]
    condition: Optional[Expr]
    update: Optional[Stmt]
    body: Stmt


@dataclass
class Print(Stmt):
    args: List[Expr]


@dataclass
class Read(Stmt):
    name: str
    symbol: Any = field(default=None, init=False, repr=False)


@dataclass
class Break(Stmt):
    pass


@dataclass
class Continue(Stmt):
    pass


@dataclass
class Program(Node):
    statements: List[Stmt]


# =====================================================================
# Pretty printer (used by the --ast command-line flag)
# =====================================================================
def dump(node: Node) -> str:
    """Return an indented, human-readable text view of the tree."""
    out: List[str] = []
    _dump(node, 0, out)
    return "\n".join(out)


def _dump(node: Node, indent: int, out: List[str]) -> None:
    pad = "  " * indent
    scalars: List[str] = []
    children: List[tuple] = []

    for f in fields(node):
        if f.name in ("line", "col", "symbol", "resolved_type"):
            continue
        value = getattr(node, f.name)
        if isinstance(value, Node) or (isinstance(value, list)):
            children.append((f.name, value))
        elif value is not None:
            scalars.append(f"{f.name}={value!r}")

    header = type(node).__name__
    if scalars:
        header += "(" + ", ".join(scalars) + ")"
    rtype = getattr(node, "resolved_type", None)
    if rtype:
        header += f" : {rtype}"
    out.append(f"{pad}{header}")

    for label, value in children:
        out.append(f"{pad}  {label}:")
        items = value if isinstance(value, list) else [value]
        for item in items:
            _dump(item, indent + 2, out)

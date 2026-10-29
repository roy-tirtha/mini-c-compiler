"""Semantic analyzer: checks that a syntactically valid program makes sense.

What it checks
  * variables are declared before use, and not declared twice in one scope
  * types: int / float arithmetic, '%' only on ints, no strings in expressions
  * division / modulo by a literal zero
  * 'break' / 'continue' only inside loops
  * warnings: use before assignment, unused variables, float->int narrowing

What it produces
  * every expression gets `.resolved_type`
  * every variable reference gets `.symbol` (so codegen knows the unique name)

It never stops at the first problem: errors are recorded and analysis goes on.
A special type ERROR is used after a failure so one mistake doesn't trigger a
chain of confusing follow-up errors.
"""

from __future__ import annotations

import difflib

from . import ast_nodes as ast
from .errors import ErrorReporter
from .symbol_table import SymbolTable

PHASE = "semantic"

INT, FLOAT, STRING, ERROR = "int", "float", "string", "<error>"
NUMERIC = (INT, FLOAT)

ARITHMETIC_OPS = {"+", "-", "*", "/", "%"}
COMPARISON_OPS = {"<", "<=", ">", ">=", "==", "!="}
LOGICAL_OPS = {"&&", "||"}


class SemanticAnalyzer:
    def __init__(self, reporter: ErrorReporter) -> None:
        self.rep = reporter
        self.symbols = SymbolTable()
        self.loop_depth = 0          # >0 while inside a while/for body
        self._unused = []            # symbols never read (reported only if no errors)

    # ------------------------------------------------------------------
    # Entry point + visitor dispatch
    # ------------------------------------------------------------------
    def analyze(self, program: ast.Program) -> ast.Program:
        self.visit(program)
        self._close_scope()          # closes the global scope
        # "Unused variable" warnings are noise when the program already has
        # real errors, so only report them for otherwise-correct programs.
        if not self.rep.has_errors:
            for sym in self._unused:
                self._warn(f"variable '{sym.name}' is declared but never used", sym,
                           len(sym.name))
        return program

    def visit(self, node: ast.Node):
        """Call visit_<NodeClassName>() for this node (visitor pattern)."""
        method = getattr(self, "visit_" + type(node).__name__, None)
        if method is None:
            raise NotImplementedError(f"no semantic rule for {type(node).__name__}")
        return method(node)

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _error(self, msg: str, node: ast.Node, length: int = 1, hint=None) -> None:
        self.rep.error(PHASE, msg, node.line, node.col, length, hint)

    def _warn(self, msg: str, node_or_sym, length: int = 1, hint=None) -> None:
        self.rep.warning(PHASE, msg, node_or_sym.line, node_or_sym.col, length, hint)

    def _close_scope(self) -> None:
        """Leave a scope; remember variables that were never read."""
        for sym in self.symbols.exit_scope():
            if not sym.used:
                self._unused.append(sym)

    def _lookup(self, name: str, node: ast.Node):
        """Find a variable or report 'undeclared' (with a did-you-mean hint)."""
        sym = self.symbols.lookup(name)
        if sym is None:
            close = difflib.get_close_matches(name, self.symbols.visible_names(), n=1)
            hint = f"did you mean '{close[0]}'?" if close else \
                   f"declare it first, e.g. 'int {name};'"
            self._error(f"use of undeclared variable '{name}'", node, len(name), hint)
        return sym

    def _check_assignable(self, target_type: str, value_type: str, node, name: str) -> None:
        """Warn when a float value is stored into an int variable."""
        if ERROR in (target_type, value_type):
            return
        if target_type == INT and value_type == FLOAT:
            self._warn(f"implicit conversion from 'float' to 'int' when assigning to "
                       f"'{name}' loses the fractional part", node, len(name),
                       hint="make the variable a float, or accept the truncation")

    @staticmethod
    def _is_zero_literal(expr: ast.Expr) -> bool:
        return isinstance(expr, (ast.IntLiteral, ast.FloatLiteral)) and expr.value == 0

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------
    def visit_Program(self, node: ast.Program) -> None:
        for stmt in node.statements:
            self.visit(stmt)

    def visit_Block(self, node: ast.Block) -> None:
        self.symbols.enter_scope()
        for stmt in node.statements:
            self.visit(stmt)
        self._close_scope()

    def visit_VarDecl(self, node: ast.VarDecl) -> None:
        # Analyse the initialiser FIRST so `int x = x;` can't see the new x.
        value_type = self.visit(node.initializer) if node.initializer else None

        previous = self.symbols.lookup_current(node.name)
        if previous is not None:
            self._error(f"redeclaration of '{node.name}'", node, len(node.name),
                        hint=f"'{node.name}' was already declared at line {previous.line}")
            return

        sym = self.symbols.declare(node.name, node.var_type, node.line, node.col)
        node.symbol = sym
        if node.initializer is not None:
            sym.initialized = True
            self._check_assignable(sym.type, value_type, node, node.name)

    def visit_Assign(self, node: ast.Assign) -> None:
        value_type = self.visit(node.value)          # RHS first (x = x + 1 reads old x)
        sym = self._lookup(node.name, node)
        if sym is None:
            return
        node.symbol = sym
        sym.initialized = True
        self._check_assignable(sym.type, value_type, node, node.name)

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.condition)
        self.visit(node.then_branch)
        if node.else_branch:
            self.visit(node.else_branch)

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.condition)
        self.loop_depth += 1
        self.visit(node.body)
        self.loop_depth -= 1

    def visit_For(self, node: ast.For) -> None:
        # The for-header gets its own scope so `for (int i...)` doesn't leak i.
        self.symbols.enter_scope()
        if node.init:
            self.visit(node.init)
        if node.condition:
            self.visit(node.condition)
        if node.update:
            self.visit(node.update)
        self.loop_depth += 1
        self.visit(node.body)
        self.loop_depth -= 1
        self._close_scope()

    def visit_Print(self, node: ast.Print) -> None:
        for arg in node.args:
            if isinstance(arg, ast.StringLiteral):   # strings are legal ONLY here
                arg.resolved_type = STRING
            else:
                self.visit(arg)

    def visit_Read(self, node: ast.Read) -> None:
        sym = self._lookup(node.name, node)
        if sym is not None:
            node.symbol = sym
            sym.initialized = True                   # read() assigns a value

    def visit_Break(self, node: ast.Break) -> None:
        if self.loop_depth == 0:
            self._error("'break' outside of a loop", node, 5,
                        hint="'break' can only be used inside while/for")

    def visit_Continue(self, node: ast.Continue) -> None:
        if self.loop_depth == 0:
            self._error("'continue' outside of a loop", node, 8,
                        hint="'continue' can only be used inside while/for")

    # ------------------------------------------------------------------
    # Expressions: each returns (and stores) the expression's type
    # ------------------------------------------------------------------
    def visit_IntLiteral(self, node: ast.IntLiteral) -> str:
        node.resolved_type = INT
        return INT

    def visit_FloatLiteral(self, node: ast.FloatLiteral) -> str:
        node.resolved_type = FLOAT
        return FLOAT

    def visit_StringLiteral(self, node: ast.StringLiteral) -> str:
        # Reaching here means the string was used outside print().
        self._error("string literals can only be used as arguments to print()", node,
                    len(node.value) + 2)
        node.resolved_type = ERROR
        return ERROR

    def visit_Identifier(self, node: ast.Identifier) -> str:
        sym = self._lookup(node.name, node)
        if sym is None:
            node.resolved_type = ERROR
            return ERROR
        node.symbol = sym
        sym.used = True
        if not sym.initialized and not sym.warned_uninit:
            sym.warned_uninit = True                 # only warn once per variable
            self._warn(f"variable '{node.name}' is used before it is assigned a value",
                       node, len(node.name), hint=f"initialise it: {sym.type} {node.name} = 0;")
        node.resolved_type = sym.type
        return sym.type

    def visit_UnaryOp(self, node: ast.UnaryOp) -> str:
        t = self.visit(node.operand)
        if t == ERROR:
            result = ERROR
        elif node.op == "-":
            result = t                               # -int -> int, -float -> float
        else:                                        # '!' always yields 0 or 1
            result = INT
        node.resolved_type = result
        return result

    def visit_BinaryOp(self, node: ast.BinaryOp) -> str:
        lt = self.visit(node.left)
        rt = self.visit(node.right)
        op = node.op

        if ERROR in (lt, rt):                        # don't pile errors on errors
            node.resolved_type = ERROR
            return ERROR

        if op in ARITHMETIC_OPS:
            if op in ("/", "%") and self._is_zero_literal(node.right):
                self._error(f"division by zero in '{op}' expression", node.right, 1,
                            hint="the right-hand operand is the constant 0")
            if op == "%":
                if lt != INT or rt != INT:
                    self._error(f"operator '%' needs two int operands, got '{lt}' and '{rt}'",
                                node, 1, hint="'%' is not defined for float values")
                    node.resolved_type = ERROR
                    return ERROR
                result = INT
            else:
                result = FLOAT if FLOAT in (lt, rt) else INT   # int op float -> float
        else:
            # Comparisons and && / || accept any numbers and always give int (0/1).
            result = INT

        node.resolved_type = result
        return result

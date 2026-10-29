"""Code generation: AST -> Three-Address Code (TAC), plus a TAC interpreter.

Three-address code is a simple linear intermediate language where every
instruction has at most one operator, e.g.

        $t1 = b * c
        a   = $t1 + 1
        ifFalse a goto L2

Why TAC?  It is the classic textbook target: easy to read, easy to optimise,
and easy to translate to any real machine.  To make the compiler *useful*
we also include a small interpreter that executes TAC, so you can see the
programs actually run.

Naming conventions in the generated code
  $t1, $t2 ...   compiler temporaries ('$' can't appear in user identifiers)
  L1,  L2  ...   jump labels
  x, x.1 ...     user variables (suffix distinguishes shadowed variables)
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Union

from . import ast_nodes as ast
from .errors import TinyCRuntimeError

BINARY_OPS = {"+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!="}
INT_MIN, INT_MAX = -2_147_483_648, 2_147_483_647


# =====================================================================
# TAC data structures
# =====================================================================
@dataclass(frozen=True)
class Const:
    """A literal operand (number or string)."""
    value: Union[int, float, str]

    def __str__(self) -> str:
        if isinstance(self.value, str):
            return json.dumps(self.value)      # quoted + escaped
        return repr(self.value)


Operand = Union[str, Const]   # a plain str is a variable / temporary name


@dataclass
class Instr:
    """One TAC instruction.

    op      : operation name (see CodeGenerator for the full list)
    arg1/2  : operands
    result  : destination variable, or the label name for jumps/labels
    line    : source line this instruction came from (for runtime errors)
    """
    op: str
    arg1: Optional[Operand] = None
    arg2: Optional[Operand] = None
    result: Optional[str] = None
    line: int = 0

    def __str__(self) -> str:
        op = self.op
        if op in BINARY_OPS:
            return f"{self.result} = {self.arg1} {op} {self.arg2}"
        simple = {
            "assign":     f"{self.result} = {self.arg1}",
            "neg":        f"{self.result} = -{self.arg1}",
            "not":        f"{self.result} = !{self.arg1}",
            "cast_int":   f"{self.result} = (int) {self.arg1}",
            "cast_float": f"{self.result} = (float) {self.arg1}",
            "label":      f"{self.result}:",
            "jump":       f"goto {self.result}",
            "jumpf":      f"ifFalse {self.arg1} goto {self.result}",
            "jumpt":      f"if {self.arg1} goto {self.result}",
            "print":      f"print {self.arg1}",
            "newline":    "newline",
            "read":       f"{self.result} = read {self.arg1}",
        }
        return simple[op]


def format_tac(code: List[Instr]) -> str:
    """Pretty-print TAC: labels flush left, instructions indented."""
    lines = []
    for i, ins in enumerate(code):
        text = str(ins) if ins.op == "label" else "    " + str(ins)
        lines.append(f"{i:03d}  {text}")
    return "\n".join(lines)


# =====================================================================
# Code generator
# =====================================================================
class CodeGenerator:
    def __init__(self) -> None:
        self.code: List[Instr] = []
        self._temp_count = 0
        self._label_count = 0
        self._line = 0                               # source line being compiled
        # Stack of (continue_label, break_label) for the loops we are inside.
        self._loops: List[tuple] = []

    # ---- public ------------------------------------------------------
    def generate(self, program: ast.Program) -> List[Instr]:
        for stmt in program.statements:
            self._stmt(stmt)
        return self.code

    # ---- emit helpers ------------------------------------------------
    def _emit(self, op, arg1=None, arg2=None, result=None) -> None:
        self.code.append(Instr(op, arg1, arg2, result, self._line))

    def _new_temp(self) -> str:
        self._temp_count += 1
        return f"$t{self._temp_count}"

    def _new_label(self) -> str:
        self._label_count += 1
        return f"L{self._label_count}"

    def _label(self, name: str) -> None:
        self._emit("label", result=name)

    # ---- type conversion --------------------------------------------
    def _convert(self, operand: Operand, from_type: str, to_type: str) -> Operand:
        """Insert an int<->float cast when the types differ."""
        if from_type == to_type or to_type not in ("int", "float"):
            return operand
        if isinstance(operand, Const):               # fold constants at compile time
            return Const(int(operand.value) if to_type == "int" else float(operand.value))
        temp = self._new_temp()
        self._emit("cast_int" if to_type == "int" else "cast_float", operand, result=temp)
        return temp

    # ==================================================================
    # Statements
    # ==================================================================
    def _stmt(self, node: ast.Stmt) -> None:
        self._line = node.line
        getattr(self, "_stmt_" + type(node).__name__)(node)

    def _stmt_Block(self, node: ast.Block) -> None:
        for s in node.statements:
            self._stmt(s)

    def _stmt_VarDecl(self, node: ast.VarDecl) -> None:
        sym = node.symbol
        if node.initializer is not None:
            value = self._expr(node.initializer)
            value = self._convert(value, node.initializer.resolved_type, sym.type)
        else:
            # Give uninitialised variables a deterministic value (0).
            value = Const(0 if sym.type == "int" else 0.0)
        self._emit("assign", value, result=sym.unique_name)

    def _stmt_Assign(self, node: ast.Assign) -> None:
        value = self._expr(node.value)
        value = self._convert(value, node.value.resolved_type, node.symbol.type)
        self._emit("assign", value, result=node.symbol.unique_name)

    def _stmt_If(self, node: ast.If) -> None:
        else_label = self._new_label()
        cond = self._expr(node.condition)
        self._emit("jumpf", cond, result=else_label)          # cond false -> skip 'then'
        self._stmt(node.then_branch)
        if node.else_branch is not None:
            end_label = self._new_label()
            self._emit("jump", result=end_label)              # skip 'else' after 'then'
            self._label(else_label)
            self._stmt(node.else_branch)
            self._label(end_label)
        else:
            self._label(else_label)

    def _stmt_While(self, node: ast.While) -> None:
        start, end = self._new_label(), self._new_label()
        self._label(start)
        self._line = node.line
        cond = self._expr(node.condition)
        self._emit("jumpf", cond, result=end)                 # leave loop when false
        self._loops.append((start, end))                      # continue->start, break->end
        self._stmt(node.body)
        self._loops.pop()
        self._emit("jump", result=start)
        self._label(end)

    def _stmt_For(self, node: ast.For) -> None:
        start, update, end = self._new_label(), self._new_label(), self._new_label()
        if node.init:
            self._stmt(node.init)
        self._label(start)
        if node.condition:
            self._line = node.line
            cond = self._expr(node.condition)
            self._emit("jumpf", cond, result=end)
        self._loops.append((update, end))                     # continue jumps to update part
        self._stmt(node.body)
        self._loops.pop()
        self._label(update)
        if node.update:
            self._stmt(node.update)
        self._emit("jump", result=start)
        self._label(end)

    def _stmt_Print(self, node: ast.Print) -> None:
        for i, arg in enumerate(node.args):
            if i > 0:
                self._emit("print", Const(" "))               # space between arguments
            self._emit("print", self._expr(arg))
        self._emit("newline")

    def _stmt_Read(self, node: ast.Read) -> None:
        self._emit("read", node.symbol.type, result=node.symbol.unique_name)

    def _stmt_Break(self, node: ast.Break) -> None:
        self._emit("jump", result=self._loops[-1][1])

    def _stmt_Continue(self, node: ast.Continue) -> None:
        self._emit("jump", result=self._loops[-1][0])

    # ==================================================================
    # Expressions: each returns the operand holding the result
    # ==================================================================
    def _expr(self, node: ast.Expr) -> Operand:
        return getattr(self, "_expr_" + type(node).__name__)(node)

    def _expr_IntLiteral(self, node):    return Const(node.value)
    def _expr_FloatLiteral(self, node):  return Const(node.value)
    def _expr_StringLiteral(self, node): return Const(node.value)
    def _expr_Identifier(self, node):    return node.symbol.unique_name

    def _expr_UnaryOp(self, node: ast.UnaryOp) -> Operand:
        operand = self._expr(node.operand)
        temp = self._new_temp()
        self._emit("neg" if node.op == "-" else "not", operand, result=temp)
        return temp

    def _expr_BinaryOp(self, node: ast.BinaryOp) -> Operand:
        if node.op in ("&&", "||"):
            return self._short_circuit(node)
        left = self._expr(node.left)
        right = self._expr(node.right)
        self._line = node.line
        temp = self._new_temp()
        self._emit(node.op, left, right, temp)
        return temp

    def _short_circuit(self, node: ast.BinaryOp) -> Operand:
        """&& and || must not evaluate the right side when the left decides.

            a && b :  if a is false  -> result 0 (b never evaluated)
            a || b :  if a is true   -> result 1 (b never evaluated)
        """
        result = self._new_temp()
        decided, end = self._new_label(), self._new_label()
        is_and = node.op == "&&"

        left = self._expr(node.left)
        self._emit("jumpf" if is_and else "jumpt", left, result=decided)
        right = self._expr(node.right)
        self._emit("jumpf" if is_and else "jumpt", right, result=decided)

        # Neither operand short-circuited: AND -> 1, OR -> 0
        self._emit("assign", Const(1 if is_and else 0), result=result)
        self._emit("jump", result=end)
        self._label(decided)
        self._emit("assign", Const(0 if is_and else 1), result=result)
        self._label(end)
        return result


# =====================================================================
# TAC interpreter (the "virtual machine")
# =====================================================================
def _wrap32(n: int) -> int:
    """Emulate 32-bit signed integer overflow like real C ints."""
    return ((n - INT_MIN) & 0xFFFFFFFF) + INT_MIN


def _trunc_div(a: int, b: int) -> int:
    """Integer division that truncates toward zero (C semantics)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def format_value(v) -> str:
    """How print() shows a value."""
    if isinstance(v, float):
        s = f"{v:.6g}"
        if s.lstrip("-").isdigit():     # 3.0 -> "3" would look like an int
            s += ".0"
        return s
    return str(v)


class TACInterpreter:
    def __init__(self, code: List[Instr],
                 out: Callable[[str], object] = sys.stdout.write,
                 inp: Callable[[], str] = input,
                 max_steps: int = 5_000_000) -> None:
        self.code = code
        self.out = out
        self.inp = inp
        self.max_steps = max_steps          # guards against infinite loops

    def run(self) -> None:
        code = self.code
        # Pre-compute label -> instruction index for fast jumps.
        labels: Dict[str, int] = {i.result: n for n, i in enumerate(code) if i.op == "label"}
        env: Dict[str, Union[int, float]] = {}     # variable storage
        pc, steps = 0, 0                           # program counter, step counter

        def val(o: Operand):
            return o.value if isinstance(o, Const) else env[o]

        while pc < len(code):
            ins = code[pc]
            pc += 1
            if ins.op == "label":
                continue
            steps += 1
            if steps > self.max_steps:
                raise TinyCRuntimeError(
                    f"execution exceeded {self.max_steps} steps (infinite loop?)", ins.line)

            op = ins.op
            if op in BINARY_OPS:
                env[ins.result] = self._binary(op, val(ins.arg1), val(ins.arg2), ins.line)
            elif op == "assign":
                env[ins.result] = val(ins.arg1)
            elif op == "neg":
                v = -val(ins.arg1)
                env[ins.result] = _wrap32(v) if isinstance(v, int) else v
            elif op == "not":
                env[ins.result] = int(not val(ins.arg1))
            elif op == "cast_int":
                env[ins.result] = _wrap32(int(val(ins.arg1)))   # truncates toward zero
            elif op == "cast_float":
                env[ins.result] = float(val(ins.arg1))
            elif op == "jump":
                pc = labels[ins.result]
            elif op == "jumpf":
                if not val(ins.arg1):
                    pc = labels[ins.result]
            elif op == "jumpt":
                if val(ins.arg1):
                    pc = labels[ins.result]
            elif op == "print":
                v = val(ins.arg1)
                self.out(v if isinstance(v, str) else format_value(v))
            elif op == "newline":
                self.out("\n")
            elif op == "read":
                env[ins.result] = self._read(ins.arg1, ins.line)
            else:                                   # pragma: no cover
                raise TinyCRuntimeError(f"unknown instruction '{op}'", ins.line)

    # ---- arithmetic with C semantics ---------------------------------
    @staticmethod
    def _binary(op: str, a, b, line: int):
        if op == "+":  res = a + b
        elif op == "-": res = a - b
        elif op == "*": res = a * b
        elif op == "/":
            if b == 0:
                raise TinyCRuntimeError("division by zero", line)
            both_int = isinstance(a, int) and isinstance(b, int)
            res = _trunc_div(a, b) if both_int else a / b
        elif op == "%":
            if b == 0:
                raise TinyCRuntimeError("modulo by zero", line)
            res = a - b * _trunc_div(a, b)
        else:  # comparisons produce 1 or 0
            return int({"<": a < b, "<=": a <= b, ">": a > b,
                        ">=": a >= b, "==": a == b, "!=": a != b}[op])
        return _wrap32(res) if isinstance(res, int) else res

    def _read(self, type_: str, line: int):
        """Read one number from the user for read(x)."""
        try:
            text = self.inp().strip()
        except EOFError:
            raise TinyCRuntimeError("read() found no more input", line)
        try:
            return int(text) if type_ == "int" else float(text)
        except ValueError:
            raise TinyCRuntimeError(f"invalid {type_} input: {text!r}", line)

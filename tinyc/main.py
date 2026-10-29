"""Command-line entry point for the Tiny C compiler.

Where does the program text come from?  (checked in this order)
  1. -c "code"            code given directly on the command line
  2. a file argument      python -m tinyc.main examples/basic.tc
  3. piped input          echo "print(1+2);" | python -m tinyc.main
  4. interactive prompt   python -m tinyc.main        (type code, then 'run')

The compiler itself only ever sees one string, so all four are equivalent.

Exit codes:  0 success | 1 compile error | 2 runtime error | 3 file/usage error
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

from . import __version__
from .ast_nodes import Program, dump
from .codegen import CodeGenerator, Instr, TACInterpreter, format_tac
from .errors import ErrorReporter, TinyCRuntimeError
from .lexer import Lexer
from .parser import Parser
from .semantic import SemanticAnalyzer
from .tokens import Token


# =====================================================================
# The compiler pipeline
# =====================================================================
@dataclass
class CompileResult:
    """Everything produced by a compilation. A stage that never ran is None."""
    reporter: ErrorReporter
    tokens: Optional[List[Token]] = None
    ast: Optional[Program] = None
    tac: Optional[List[Instr]] = None

    @property
    def ok(self) -> bool:
        return self.tac is not None and not self.reporter.has_errors


def compile_source(source: str) -> CompileResult:
    """Run all compiler phases. Stops after the first phase that reports errors,
    because later phases would only produce confusing follow-up noise."""
    reporter = ErrorReporter()
    result = CompileResult(reporter)

    # Phase 1: lexical analysis  (text -> tokens)
    result.tokens = Lexer(source, reporter).tokenize()
    if reporter.has_errors:
        return result

    # Phase 2: syntax analysis   (tokens -> AST)
    result.ast = Parser(result.tokens, reporter).parse()
    if reporter.has_errors:
        return result

    # Phase 3: semantic analysis (type/scope checks, annotates the AST)
    SemanticAnalyzer(reporter).analyze(result.ast)
    if reporter.has_errors:
        return result

    # Phase 4: code generation   (AST -> three-address code)
    result.tac = CodeGenerator().generate(result.ast)
    return result


# =====================================================================
# Helpers for the CLI
# =====================================================================
def _use_color(args) -> bool:
    return (not args.no_color and "NO_COLOR" not in os.environ and sys.stderr.isatty())


def _read_input_line() -> str:
    """Line source for read(x). Shows a prompt only on a real terminal."""
    if sys.stdin.isatty():
        return input("input> ")
    line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line.rstrip("\n")


def _print_tokens(tokens: List[Token]) -> None:
    print("== TOKENS ==")
    print(f"{'LINE:COL':<9} {'TYPE':<11} LEXEME")
    for t in tokens:
        loc = f"{t.line}:{t.col}"
        print(f"{loc:<9} {t.type.name:<11} {t.lexeme!r}")
    print()


def process(source: str, filename: str, args, color: bool) -> int:
    """Compile (and by default run) one program. Returns the exit code."""
    result = compile_source(source)

    # Optional debug views of the stages that completed.
    if args.tokens and result.tokens is not None:
        _print_tokens(result.tokens)
    if args.ast and result.ast is not None:
        print("== AST ==")
        print(dump(result.ast))
        print()
    if args.tac and result.tac is not None:
        print("== THREE-ADDRESS CODE ==")
        print(format_tac(result.tac))
        print()
    sys.stdout.flush()

    # Errors and warnings go to stderr.
    if result.reporter.diagnostics:
        print(result.reporter.render(source, filename, color), file=sys.stderr)
    if not result.ok:
        return 1
    if args.no_run:
        return 0

    # Execute the generated code.
    interpreter = TACInterpreter(result.tac, out=sys.stdout.write,
                                 inp=_read_input_line, max_steps=args.max_steps)
    try:
        interpreter.run()
    except TinyCRuntimeError as err:
        sys.stdout.flush()
        print(result.reporter.render_runtime(err, color), file=sys.stderr)
        return 2
    finally:
        sys.stdout.flush()
    return 0


def interactive(args, color: bool) -> int:
    """Prompt mode: type lines of Tiny C, then 'run' to compile and execute."""
    print(f"Tiny C compiler {__version__} - interactive mode")
    print("Type your program line by line. Commands: run | clear | exit  (Ctrl+D also runs)")
    while True:
        lines: List[str] = []
        while True:
            try:
                line = input("tc> " if not lines else "... ")
            except EOFError:                 # Ctrl+D / Ctrl+Z
                print()
                if lines:
                    break                    # run what we have, then ask again
                return 0
            cmd = line.strip()
            if cmd == "run":
                break
            if cmd in ("exit", "quit"):
                return 0
            if cmd == "clear":
                lines = []
                print("(buffer cleared)")
                continue
            lines.append(line)

        if not lines:
            print("(nothing to run)")
            continue
        process("\n".join(lines), "<interactive>", args, color)
        print()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tinyc.main",
        description="Tiny C compiler: lexer -> parser -> semantic check -> TAC -> run.")
    p.add_argument("file", nargs="?", help="Tiny C source file (e.g. examples/basic.tc)")
    p.add_argument("-c", "--code", help="compile this code string directly")
    p.add_argument("--tokens", action="store_true", help="print the token list")
    p.add_argument("--ast", action="store_true", help="print the syntax tree")
    p.add_argument("--tac", action="store_true", help="print the generated three-address code")
    p.add_argument("--no-run", action="store_true", help="compile and check only; do not execute")
    p.add_argument("--max-steps", type=int, default=5_000_000,
                   help="abort execution after this many instructions (default: 5,000,000)")
    p.add_argument("--no-color", action="store_true", help="disable coloured error output")
    p.add_argument("--version", action="version", version=f"tinyc {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    color = _use_color(args)

    try:
        if args.code is not None:
            return process(args.code, "<command-line>", args, color)

        if args.file:
            try:
                with open(args.file, encoding="utf-8") as f:
                    source = f.read()
            except OSError as exc:
                print(f"error: cannot read '{args.file}': {exc.strerror}", file=sys.stderr)
                return 3
            return process(source, args.file, args, color)

        if not sys.stdin.isatty():           # piped input
            return process(sys.stdin.read(), "<stdin>", args, color)

        return interactive(args, color)      # nothing given -> prompt mode
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        # Output was piped into something like `head` that closed early.
        sys.stderr.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())

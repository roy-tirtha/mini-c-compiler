import unittest

from tinyc import ast_nodes as ast
from tinyc.errors import ErrorReporter
from tinyc.lexer import Lexer
from tinyc.parser import Parser


def parse(src):
    rep = ErrorReporter()
    program = Parser(Lexer(src, rep).tokenize(), rep).parse()
    return program, rep


class ParserTests(unittest.TestCase):
    def test_var_decl(self):
        prog, rep = parse("int x = 5; float y;")
        self.assertFalse(rep.has_errors)
        self.assertIsInstance(prog.statements[0], ast.VarDecl)
        self.assertIsNone(prog.statements[1].initializer)

    def test_operator_precedence(self):
        prog, _ = parse("int x = 1 + 2 * 3;")
        expr = prog.statements[0].initializer
        self.assertEqual(expr.op, "+")           # + is the root...
        self.assertEqual(expr.right.op, "*")     # ...and * binds tighter

    def test_left_associativity(self):
        prog, _ = parse("int x = 10 - 4 - 3;")
        expr = prog.statements[0].initializer
        self.assertEqual(expr.op, "-")
        self.assertEqual(expr.left.op, "-")      # (10-4)-3, not 10-(4-3)

    def test_compound_assignment_desugars(self):
        prog, _ = parse("int x; x += 2;")
        assign = prog.statements[1]
        self.assertIsInstance(assign.value, ast.BinaryOp)
        self.assertEqual(assign.value.op, "+")

    def test_increment_desugars(self):
        prog, _ = parse("int i; i++;")
        self.assertEqual(prog.statements[1].value.op, "+")

    def test_if_else_and_dangling_else(self):
        prog, rep = parse("int a; if (a) if (a) a = 1; else a = 2;")
        self.assertFalse(rep.has_errors)
        outer = prog.statements[1]
        self.assertIsNone(outer.else_branch)            # else belongs to inner if
        self.assertIsNotNone(outer.then_branch.else_branch)

    def test_for_loop_parts(self):
        prog, rep = parse("for (int i = 0; i < 3; i++) { print(i); }")
        self.assertFalse(rep.has_errors)
        f = prog.statements[0]
        self.assertIsInstance(f.init, ast.VarDecl)
        self.assertIsNotNone(f.condition)
        self.assertIsNotNone(f.update)

    def test_for_with_empty_clauses(self):
        _, rep = parse("for (;;) { break; }")
        self.assertFalse(rep.has_errors)

    def test_missing_semicolon_points_at_previous_token(self):
        _, rep = parse("int x = 5\nint y;")
        self.assertEqual(len(rep.errors), 1)
        err = rep.errors[0]
        self.assertEqual((err.line, err.col), (1, 10))   # just after the '5'

    def test_recovery_reports_several_errors(self):
        _, rep = parse("int x = ;\nint y = ;\nint z = 3;")
        self.assertEqual(len(rep.errors), 2)

    def test_assignment_in_condition(self):
        _, rep = parse("int x; if (x = 1) { }")
        self.assertIn("assignment is not allowed", rep.errors[0].message)

    def test_missing_closing_paren(self):
        _, rep = parse("int x; while (x < 3 { }")
        self.assertIn("expected ')'", rep.errors[0].message)

    def test_unclosed_block(self):
        _, rep = parse("{ int x = 1;")
        self.assertIn("close the block", rep.errors[0].message)

    def test_stray_closing_brace_terminates(self):
        _, rep = parse("int x; } int y;")
        self.assertEqual(len(rep.errors), 1)

    def test_else_without_if(self):
        _, rep = parse("else { }")
        self.assertIn("'else' without", rep.errors[0].message)

    def test_declaration_as_if_body(self):
        _, rep = parse("if (1) int x = 2;")
        self.assertIn("declaration cannot be the body", rep.errors[0].message)

    def test_multiple_declarators_rejected(self):
        _, rep = parse("int a, b;")
        self.assertIn("only one variable", rep.errors[0].message)

    def test_parser_always_terminates_on_garbage(self):
        # Must not loop forever or crash, whatever the input.
        for junk in (")))", "{{{{", "int", "if", "for (", "= = =", "print(", "@@"):
            parse(junk)


if __name__ == "__main__":
    unittest.main()

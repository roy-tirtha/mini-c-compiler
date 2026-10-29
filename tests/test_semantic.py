import unittest

from tinyc.main import compile_source


def check(src):
    """Return (errors, warnings) message lists for a program."""
    rep = compile_source(src).reporter
    return [e.message for e in rep.errors], [w.message for w in rep.warnings]


def has(messages, fragment):
    return any(fragment in m for m in messages)


class SemanticTests(unittest.TestCase):
    def test_valid_program_has_no_errors(self):
        errors, _ = check("int x = 1; float y = x * 2.5; print(x, y);")
        self.assertEqual(errors, [])

    def test_undeclared_variable(self):
        errors, _ = check("print(y);")
        self.assertTrue(has(errors, "undeclared variable 'y'"))

    def test_did_you_mean_hint(self):
        rep = compile_source("int counter = 1; print(countr);").reporter
        self.assertIn("counter", rep.errors[0].hint)

    def test_assignment_to_undeclared(self):
        errors, _ = check("x = 5;")
        self.assertTrue(has(errors, "undeclared"))

    def test_redeclaration_same_scope(self):
        errors, _ = check("int x; int x;")
        self.assertTrue(has(errors, "redeclaration of 'x'"))

    def test_shadowing_in_inner_scope_is_allowed(self):
        errors, _ = check("int x = 1; { int x = 2; print(x); } print(x);")
        self.assertEqual(errors, [])

    def test_variable_not_visible_outside_block(self):
        errors, _ = check("{ int inner = 1; print(inner); } print(inner);")
        self.assertTrue(has(errors, "undeclared variable 'inner'"))

    def test_for_variable_scoped_to_loop(self):
        errors, _ = check("for (int i = 0; i < 2; i++) { } print(i);")
        self.assertTrue(has(errors, "undeclared variable 'i'"))

    def test_modulo_requires_ints(self):
        errors, _ = check("float f = 2.5; int r = 7 % f;")
        self.assertTrue(has(errors, "'%' needs two int operands"))

    def test_division_by_zero_literal(self):
        errors, _ = check("int x = 4 / 0;")
        self.assertTrue(has(errors, "division by zero"))
        errors, _ = check("int x = 4 % 0;")
        self.assertTrue(has(errors, "division by zero"))

    def test_string_outside_print(self):
        errors, _ = check('int x = 1 + "a";')
        self.assertTrue(has(errors, "string literals can only"))

    def test_break_continue_outside_loop(self):
        errors, _ = check("break; continue;")
        self.assertEqual(len(errors), 2)

    def test_break_inside_loop_ok(self):
        errors, _ = check("while (1) { break; }")
        self.assertEqual(errors, [])

    def test_use_before_assignment_warning(self):
        errors, warnings = check("int x; print(x);")
        self.assertEqual(errors, [])
        self.assertTrue(has(warnings, "used before it is assigned"))

    def test_read_counts_as_assignment(self):
        _, warnings = check("int x; read(x); print(x);")
        self.assertFalse(has(warnings, "before it is assigned"))

    def test_narrowing_warning(self):
        _, warnings = check("int x = 3.9; print(x);")
        self.assertTrue(has(warnings, "float' to 'int'"))

    def test_unused_variable_warning(self):
        _, warnings = check("int unused = 1;")
        self.assertTrue(has(warnings, "never used"))

    def test_unused_warning_suppressed_when_errors_exist(self):
        _, warnings = check("int unused = 1; print(nope);")
        self.assertFalse(has(warnings, "never used"))

    def test_error_does_not_cascade(self):
        errors, _ = check("int x = missing + 1 * 2;")
        self.assertEqual(len(errors), 1)

    def test_types_are_annotated(self):
        result = compile_source("float f = 1 + 2.5;")
        self.assertEqual(result.ast.statements[0].initializer.resolved_type, "float")


if __name__ == "__main__":
    unittest.main()

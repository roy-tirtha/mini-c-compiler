import unittest

from tinyc.codegen import TACInterpreter, format_tac
from tinyc.errors import TinyCRuntimeError
from tinyc.main import compile_source


def run(src, inputs=()):
    """Compile and execute; return everything the program printed."""
    result = compile_source(src)
    assert result.ok, result.reporter.render(src)
    out, feed = [], list(inputs)

    def inp():
        if not feed:
            raise EOFError
        return feed.pop(0)

    TACInterpreter(result.tac, out=out.append, inp=inp, max_steps=100_000).run()
    return "".join(out)


class CodegenTests(unittest.TestCase):
    def test_print_and_arithmetic(self):
        self.assertEqual(run("print(1 + 2 * 3);"), "7\n")

    def test_int_division_truncates_toward_zero(self):
        self.assertEqual(run("print(7 / 2, -7 / 2);"), "3 -3\n")

    def test_modulo_follows_c_sign_rules(self):
        self.assertEqual(run("print(7 % 3, -7 % 3);"), "1 -1\n")

    def test_float_arithmetic_and_formatting(self):
        self.assertEqual(run("float x = 7.5; print(x / 2, 3.0);"), "3.75 3.0\n")

    def test_int_to_float_conversion(self):
        self.assertEqual(run("float f = 5; print(f);"), "5.0\n")

    def test_float_to_int_truncation(self):
        self.assertEqual(run("int i = 3.9; print(i);"), "3\n")

    def test_string_and_multiple_args(self):
        self.assertEqual(run('int a = 2; print("a =", a);'), "a = 2\n")

    def test_if_else(self):
        src = "int x = 5; if (x > 3) { print(1); } else { print(2); }"
        self.assertEqual(run(src), "1\n")
        self.assertEqual(run("int x = 1; if (x > 3) print(1); else print(2);"), "2\n")

    def test_while_loop(self):
        self.assertEqual(run("int i = 0; while (i < 3) { print(i); i++; }"), "0\n1\n2\n")

    def test_for_loop_with_break_and_continue(self):
        src = """
        for (int i = 0; i < 10; i++) {
            if (i % 2 == 0) { continue; }
            if (i > 6) { break; }
            print(i);
        }"""
        self.assertEqual(run(src), "1\n3\n5\n")

    def test_continue_in_for_still_runs_update(self):
        # If 'continue' skipped the update this would loop forever.
        self.assertEqual(run("for (int i = 0; i < 3; i++) { continue; } print(9);"), "9\n")

    def test_nested_loops(self):
        src = "int c = 0; for (int i=0;i<3;i++) { for (int j=0;j<3;j++) { c++; } } print(c);"
        self.assertEqual(run(src), "9\n")

    def test_short_circuit_and(self):
        # Right side would divide by zero if it were (wrongly) evaluated.
        self.assertEqual(run("int z = 0; if (z != 0 && 10 / z > 1) { print(1); } else { print(0); }"), "0\n")

    def test_short_circuit_or(self):
        self.assertEqual(run("int z = 0; if (z == 0 || 10 / z > 1) { print(1); }"), "1\n")

    def test_logical_results_are_0_or_1(self):
        self.assertEqual(run("print(5 && 3, 0 || 0, !7, !0);"), "1 0 0 1\n")

    def test_shadowed_variables_stay_separate(self):
        src = "int x = 1; { int x = 2; print(x); } print(x);"
        self.assertEqual(run(src), "2\n1\n")

    def test_uninitialised_variable_defaults_to_zero(self):
        self.assertEqual(run("int x; print(x);"), "0\n")

    def test_read_input(self):
        self.assertEqual(run("int n; read(n); print(n * 2);", inputs=["21"]), "42\n")
        self.assertEqual(run("float f; read(f); print(f);", inputs=["2.5"]), "2.5\n")

    def test_int_overflow_wraps_like_c(self):
        self.assertEqual(run("int x = 2147483647; x = x + 1; print(x);"), "-2147483648\n")

    def test_recursion_free_factorial(self):
        src = "int f = 1; for (int n = 2; n <= 10; n++) { f *= n; } print(f);"
        self.assertEqual(run(src), "3628800\n")

    # ---- runtime errors --------------------------------------------
    def test_runtime_division_by_zero(self):
        with self.assertRaises(TinyCRuntimeError) as ctx:
            run("int z = 0; print(5 / z);")
        self.assertIn("division by zero", ctx.exception.message)
        self.assertEqual(ctx.exception.line, 1)

    def test_infinite_loop_is_stopped(self):
        with self.assertRaises(TinyCRuntimeError) as ctx:
            run("while (1) { }")
        self.assertIn("exceeded", ctx.exception.message)

    def test_read_bad_input(self):
        with self.assertRaises(TinyCRuntimeError):
            run("int n; read(n);", inputs=["abc"])

    def test_read_without_input(self):
        with self.assertRaises(TinyCRuntimeError):
            run("int n; read(n);")

    # ---- shape of generated code -----------------------------------
    def test_tac_listing(self):
        tac = format_tac(compile_source("int a = 1 + 2;").tac)
        self.assertIn("$t1 = 1 + 2", tac)
        self.assertIn("a = $t1", tac)


if __name__ == "__main__":
    unittest.main()

"""Lexer tests. Run from the project root:  python -m unittest discover -s tests -v"""
import unittest

from tinyc.errors import ErrorReporter
from tinyc.lexer import Lexer
from tinyc.tokens import TokenType as T


def lex(src):
    rep = ErrorReporter()
    tokens = Lexer(src, rep).tokenize()
    return tokens, rep


def types(src):
    return [t.type for t in lex(src)[0]]


class LexerTests(unittest.TestCase):
    def test_keywords_and_identifiers(self):
        self.assertEqual(types("int x while whilex"),
                         [T.INT, T.IDENT, T.WHILE, T.IDENT, T.EOF])

    def test_numbers(self):
        tokens, rep = lex("42 3.14")
        self.assertFalse(rep.has_errors)
        self.assertEqual(tokens[0].value, 42)
        self.assertEqual(tokens[1].value, 3.14)
        self.assertEqual(tokens[1].type, T.FLOAT_LIT)

    def test_multi_char_operators(self):
        self.assertEqual(types("== != <= >= && || ++ -- += -= *= /="),
                         [T.EQ, T.NEQ, T.LE, T.GE, T.AND, T.OR, T.PLUS_PLUS, T.MINUS_MINUS,
                          T.PLUS_ASSIGN, T.MINUS_ASSIGN, T.STAR_ASSIGN, T.SLASH_ASSIGN, T.EOF])

    def test_comments_are_skipped(self):
        self.assertEqual(types("a // comment\n b /* multi\nline */ c"),
                         [T.IDENT, T.IDENT, T.IDENT, T.EOF])

    def test_line_and_column_tracking(self):
        tokens, _ = lex("int a;\n  int b;")
        b = [t for t in tokens if t.lexeme == "b"][0]
        self.assertEqual((b.line, b.col), (2, 7))

    def test_string_escapes(self):
        tokens, rep = lex(r'"a\tb\n"')
        self.assertFalse(rep.has_errors)
        self.assertEqual(tokens[0].value, "a\tb\n")

    def test_unexpected_character(self):
        _, rep = lex("int a = 3 @ 4;")
        self.assertEqual(len(rep.errors), 1)
        self.assertIn("unexpected character", rep.errors[0].message)

    def test_multiple_errors_reported(self):
        _, rep = lex("@ # $")
        self.assertEqual(len(rep.errors), 3)

    def test_unterminated_string(self):
        _, rep = lex('print("hello')
        self.assertIn("unterminated string", rep.errors[0].message)

    def test_unterminated_block_comment(self):
        _, rep = lex("/* never closed")
        self.assertIn("unterminated block comment", rep.errors[0].message)

    def test_malformed_numbers(self):
        for bad in ("9lives", "1.2.3", "12abc"):
            _, rep = lex(bad)
            self.assertEqual(len(rep.errors), 1, bad)
            self.assertIn("malformed number", rep.errors[0].message)

    def test_integer_too_large(self):
        _, rep = lex("99999999999")
        self.assertIn("too large", rep.errors[0].message)

    def test_lone_ampersand_and_pipe(self):
        _, rep = lex("a & b | c")
        self.assertEqual(len(rep.errors), 2)


if __name__ == "__main__":
    unittest.main()

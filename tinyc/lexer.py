"""Lexer (scanner): turns raw source text into a list of Tokens.

Responsibilities
  * skip whitespace and comments (// line  and  /* block */)
  * recognise keywords, identifiers, numbers, strings, operators
  * track line/column of every token for good error messages
  * report lexical errors and *keep scanning* so several can be found at once
"""

from __future__ import annotations

from typing import List

from .errors import ErrorReporter
from .tokens import KEYWORDS, Token, TokenType

PHASE = "lexical"
INT_MAX = 2_147_483_647  # largest 32-bit signed int

# Characters that always form a token on their own.
SINGLE_CHAR_TOKENS = {
    "%": TokenType.PERCENT,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
}

# Escape sequences allowed inside string literals.
ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "0": "\0"}


def _is_digit(c: str) -> bool:
    return "0" <= c <= "9"


def _is_alpha(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z") or c == "_"


class Lexer:
    def __init__(self, source: str, reporter: ErrorReporter) -> None:
        self.src = source
        self.rep = reporter
        self.pos = 0        # index of the next unread character
        self.line = 1       # current line (1-based)
        self.col = 1        # current column (1-based)
        self.tokens: List[Token] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def tokenize(self) -> List[Token]:
        """Scan the whole input and return the token list (ends with EOF)."""
        while not self._at_end():
            self._scan_token()
        self.tokens.append(Token(TokenType.EOF, "", None, self.line, self.col))
        return self.tokens

    # ------------------------------------------------------------------
    # Low-level character helpers
    # ------------------------------------------------------------------
    def _at_end(self) -> bool:
        return self.pos >= len(self.src)

    def _peek(self, offset: int = 0) -> str:
        """Look at a character without consuming it ('' at end of input)."""
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else ""

    def _advance(self) -> str:
        """Consume one character and update line/column counters."""
        c = self.src[self.pos]
        self.pos += 1
        if c == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return c

    def _match(self, expected: str) -> bool:
        """Consume the next char only if it equals `expected`."""
        if self._peek() == expected:
            self._advance()
            return True
        return False

    def _add(self, ttype: TokenType, start: int, line: int, col: int, value=None) -> None:
        self.tokens.append(Token(ttype, self.src[start:self.pos], value, line, col))

    def _error(self, msg: str, line: int, col: int, length: int = 1, hint=None) -> None:
        self.rep.error(PHASE, msg, line, col, length, hint)

    # ------------------------------------------------------------------
    # Main dispatch: scan exactly one token (or skip whitespace/comment)
    # ------------------------------------------------------------------
    def _scan_token(self) -> None:
        start, line, col = self.pos, self.line, self.col
        c = self._advance()

        if c in " \t\r\n":
            return  # whitespace is ignored

        if c == "/":
            if self._match("/"):                       # line comment
                while not self._at_end() and self._peek() != "\n":
                    self._advance()
            elif self._match("*"):                     # block comment
                self._block_comment(line, col)
            elif self._match("="):
                self._add(TokenType.SLASH_ASSIGN, start, line, col)
            else:
                self._add(TokenType.SLASH, start, line, col)
            return

        if _is_alpha(c):
            self._identifier(start, line, col)
        elif _is_digit(c):
            self._number(start, line, col)
        elif c == '"':
            self._string(start, line, col)
        elif c in SINGLE_CHAR_TOKENS:
            self._add(SINGLE_CHAR_TOKENS[c], start, line, col)
        elif c == "*":
            self._add(TokenType.STAR_ASSIGN if self._match("=") else TokenType.STAR,
                      start, line, col)
        elif c == "+":
            ttype = (TokenType.PLUS_PLUS if self._match("+")
                     else TokenType.PLUS_ASSIGN if self._match("=")
                     else TokenType.PLUS)
            self._add(ttype, start, line, col)
        elif c == "-":
            ttype = (TokenType.MINUS_MINUS if self._match("-")
                     else TokenType.MINUS_ASSIGN if self._match("=")
                     else TokenType.MINUS)
            self._add(ttype, start, line, col)
        elif c == "=":
            self._add(TokenType.EQ if self._match("=") else TokenType.ASSIGN, start, line, col)
        elif c == "!":
            self._add(TokenType.NEQ if self._match("=") else TokenType.NOT, start, line, col)
        elif c == "<":
            self._add(TokenType.LE if self._match("=") else TokenType.LT, start, line, col)
        elif c == ">":
            self._add(TokenType.GE if self._match("=") else TokenType.GT, start, line, col)
        elif c == "&":
            if self._match("&"):
                self._add(TokenType.AND, start, line, col)
            else:
                self._error("unexpected '&'", line, col,
                            hint="did you mean '&&' (logical AND)? Bitwise operators are not supported")
        elif c == "|":
            if self._match("|"):
                self._add(TokenType.OR, start, line, col)
            else:
                self._error("unexpected '|'", line, col,
                            hint="did you mean '||' (logical OR)? Bitwise operators are not supported")
        else:
            self._error(f"unexpected character {c!r}", line, col,
                        hint="this character is not part of the Tiny C language")

    # ------------------------------------------------------------------
    # Specific token scanners
    # ------------------------------------------------------------------
    def _block_comment(self, line: int, col: int) -> None:
        """Skip /* ... */ ; report if it never closes."""
        while not self._at_end():
            if self._peek() == "*" and self._peek(1) == "/":
                self._advance()
                self._advance()
                return
            self._advance()
        self._error("unterminated block comment", line, col, 2,
                    hint="add a closing '*/'")

    def _identifier(self, start: int, line: int, col: int) -> None:
        while _is_alpha(self._peek()) or _is_digit(self._peek()):
            self._advance()
        text = self.src[start:self.pos]
        # Keyword or plain identifier?
        self._add(KEYWORDS.get(text, TokenType.IDENT), start, line, col)

    def _number(self, start: int, line: int, col: int) -> None:
        """Scan an int (123) or float (3.14) literal and validate it."""
        while _is_digit(self._peek()):
            self._advance()

        is_float = False
        # A '.' only belongs to the number if a digit follows it.
        if self._peek() == "." and _is_digit(self._peek(1)):
            is_float = True
            self._advance()
            while _is_digit(self._peek()):
                self._advance()

        # Things like 12abc or 1.2.3 are malformed: swallow the whole blob
        # so we report ONE error instead of a cascade.
        if _is_alpha(self._peek()) or (self._peek() == "." and _is_digit(self._peek(1))):
            while _is_alpha(self._peek()) or _is_digit(self._peek()) or self._peek() == ".":
                self._advance()
            bad = self.src[start:self.pos]
            self._error(f"malformed number '{bad}'", line, col, len(bad),
                        hint="identifiers cannot start with a digit; numbers cannot contain letters")
            return

        text = self.src[start:self.pos]
        if is_float:
            self._add(TokenType.FLOAT_LIT, start, line, col, float(text))
        else:
            value = int(text)
            if value > INT_MAX:
                self._error(f"integer literal '{text}' is too large", line, col, len(text),
                            hint=f"the maximum int value is {INT_MAX}")
                return
            self._add(TokenType.INT_LIT, start, line, col, value)

    def _string(self, start: int, line: int, col: int) -> None:
        """Scan a "string literal" (only used with print)."""
        chars: List[str] = []
        while True:
            if self._at_end() or self._peek() == "\n":
                self._error("unterminated string literal", line, col, 1,
                            hint="add a closing double quote (\")")
                return
            c = self._advance()
            if c == '"':
                break
            if c == "\\":                        # escape sequence
                esc_col = self.col - 1
                if self._at_end() or self._peek() == "\n":
                    continue                     # loop will report unterminated
                e = self._advance()
                if e in ESCAPES:
                    chars.append(ESCAPES[e])
                else:
                    self._error(f"invalid escape sequence '\\{e}'", self.line, esc_col, 2,
                                hint="valid escapes: \\n \\t \\\" \\\\ \\0")
            else:
                chars.append(c)
        self._add(TokenType.STRING_LIT, start, line, col, "".join(chars))

"""Token definitions for Tiny C.

A *token* is the smallest meaningful unit of source code (a keyword, a
number, an operator ...).  The lexer turns raw text into a list of Tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TokenType(Enum):
    """Every kind of token the lexer can produce."""

    # ---- literals & identifiers -------------------------------------
    INT_LIT = "INT_LIT"
    FLOAT_LIT = "FLOAT_LIT"
    STRING_LIT = "STRING_LIT"
    IDENT = "IDENT"

    # ---- keywords ---------------------------------------------------
    INT = "int"
    FLOAT = "float"
    IF = "if"
    ELSE = "else"
    WHILE = "while"
    FOR = "for"
    PRINT = "print"
    READ = "read"
    BREAK = "break"
    CONTINUE = "continue"

    # ---- arithmetic operators --------------------------------------
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    PERCENT = "%"

    # ---- assignment operators --------------------------------------
    ASSIGN = "="
    PLUS_ASSIGN = "+="
    MINUS_ASSIGN = "-="
    STAR_ASSIGN = "*="
    SLASH_ASSIGN = "/="
    PLUS_PLUS = "++"
    MINUS_MINUS = "--"

    # ---- comparison operators --------------------------------------
    EQ = "=="
    NEQ = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="

    # ---- logical operators -----------------------------------------
    AND = "&&"
    OR = "||"
    NOT = "!"

    # ---- punctuation ------------------------------------------------
    LPAREN = "("
    RPAREN = ")"
    LBRACE = "{"
    RBRACE = "}"
    COMMA = ","
    SEMICOLON = ";"

    # ---- end of input -----------------------------------------------
    EOF = "EOF"


# Reserved words: the lexer checks every identifier against this table.
KEYWORDS = {
    "int": TokenType.INT,
    "float": TokenType.FLOAT,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "print": TokenType.PRINT,
    "read": TokenType.READ,
    "break": TokenType.BREAK,
    "continue": TokenType.CONTINUE,
}


@dataclass
class Token:
    """One lexical token together with where it appeared in the source."""

    type: TokenType
    lexeme: str          # exact text from the source, e.g. "while" or "3.14"
    value: Any           # decoded value for literals (int/float/str), else None
    line: int            # 1-based line number
    col: int             # 1-based column number

    @property
    def length(self) -> int:
        """Number of source characters covered (used to draw ^^^^ underlines)."""
        return max(len(self.lexeme), 1)

    def __str__(self) -> str:
        return f"{self.line}:{self.col}\t{self.type.name}\t{self.lexeme!r}"

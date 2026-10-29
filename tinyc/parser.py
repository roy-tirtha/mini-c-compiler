"""Parser: turns the token list into an AST (recursive descent).

Grammar (informal)
  program      -> statement* EOF
  statement    -> varDecl | assignment ';' | ifStmt | whileStmt | forStmt
                | printStmt | readStmt | 'break' ';' | 'continue' ';' | block
  varDecl      -> ('int'|'float') IDENT ('=' expression)? ';'
  assignment   -> IDENT ('=' | '+=' | '-=' | '*=' | '/=') expression
                | IDENT ('++' | '--')
  ifStmt       -> 'if' '(' expression ')' statement ('else' statement)?
  whileStmt    -> 'while' '(' expression ')' statement
  forStmt      -> 'for' '(' (varDecl | assignment ';' | ';')
                  expression? ';' assignment? ')' statement
  printStmt    -> 'print' '(' expression (',' expression)* ')' ';'
  readStmt     -> 'read' '(' IDENT ')' ';'
  block        -> '{' statement* '}'

  expression precedence (lowest -> highest):
      ||   &&   == !=   < <= > >=   + -   * / %   unary(- !)   primary

Error recovery ("panic mode"): when a syntax error is found we record it,
skip tokens until a safe point (just after ';' or before a statement keyword
or '}'), and continue.  That way many errors are reported in one run.
"""

from __future__ import annotations

from typing import List

from . import ast_nodes as ast
from .errors import ErrorReporter
from .tokens import Token, TokenType as T

PHASE = "syntax"

# Tokens that can safely begin a new statement -> good places to resume parsing.
STATEMENT_STARTERS = {T.INT, T.FLOAT, T.IF, T.WHILE, T.FOR, T.PRINT, T.READ,
                      T.BREAK, T.CONTINUE, T.LBRACE}

COMPOUND_ASSIGN = {T.PLUS_ASSIGN: "+", T.MINUS_ASSIGN: "-",
                   T.STAR_ASSIGN: "*", T.SLASH_ASSIGN: "/"}


class _ParseAbort(Exception):
    """Internal: unwinds to the nearest statement so we can resynchronise."""


class Parser:
    def __init__(self, tokens: List[Token], reporter: ErrorReporter) -> None:
        self.tokens = tokens
        self.rep = reporter
        self.pos = 0

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------
    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _previous(self) -> Token:
        return self.tokens[self.pos - 1]

    def _at_end(self) -> bool:
        return self._peek().type is T.EOF

    def _check(self, *types: T) -> bool:
        return self._peek().type in types

    def _advance(self) -> Token:
        tok = self._peek()
        if not self._at_end():
            self.pos += 1
        return tok

    def _match(self, *types: T) -> bool:
        if self._check(*types):
            self._advance()
            return True
        return False

    @staticmethod
    def _describe(tok: Token) -> str:
        return "end of file" if tok.type is T.EOF else f"'{tok.lexeme}'"

    # ------------------------------------------------------------------
    # Error helpers
    # ------------------------------------------------------------------
    def _error(self, tok: Token, message: str, hint=None) -> _ParseAbort:
        """Record a syntax error at `tok`; caller does `raise self._error(...)`."""
        self.rep.error(PHASE, message, tok.line, tok.col, tok.length, hint)
        return _ParseAbort()

    def _expect(self, ttype: T, message: str, hint=None) -> Token:
        """Consume a token of the given type or report an error."""
        if self._check(ttype):
            return self._advance()
        if ttype is T.SEMICOLON and self.pos > 0:
            # A missing ';' is best pointed at the END of the previous token.
            prev = self._previous()
            self.rep.error(PHASE, message, prev.line, prev.col + len(prev.lexeme), 1, hint)
            raise _ParseAbort()
        raise self._error(self._peek(), f"{message}, found {self._describe(self._peek())}", hint)

    def _synchronize(self) -> None:
        """Panic-mode recovery: skip tokens until a likely statement boundary."""
        while not self._at_end():
            if self.pos > 0 and self._previous().type is T.SEMICOLON:
                return
            if self._peek().type in STATEMENT_STARTERS or self._check(T.RBRACE):
                return
            self._advance()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def parse(self) -> ast.Program:
        stmts: List[ast.Stmt] = []
        while not self._at_end():
            self._parse_statement_safely(stmts)
        return ast.Program(1, 1, stmts)

    def _parse_statement_safely(self, into: List[ast.Stmt]) -> None:
        """Parse one statement; on error record it, resynchronise and go on."""
        start = self.pos
        try:
            into.append(self._statement())
        except _ParseAbort:
            self._synchronize()
            if self.pos == start:      # guarantee progress -> no infinite loop
                self._advance()

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------
    def _statement(self) -> ast.Stmt:
        tok = self._peek()
        t = tok.type

        if t in (T.INT, T.FLOAT):
            return self._var_decl()
        if t is T.IF:
            return self._if_statement()
        if t is T.WHILE:
            return self._while_statement()
        if t is T.FOR:
            return self._for_statement()
        if t is T.PRINT:
            return self._print_statement()
        if t is T.READ:
            return self._read_statement()
        if t is T.LBRACE:
            return self._block()
        if t in (T.BREAK, T.CONTINUE):
            self._advance()
            self._expect(T.SEMICOLON, f"expected ';' after '{tok.lexeme}'")
            node_cls = ast.Break if t is T.BREAK else ast.Continue
            return node_cls(tok.line, tok.col)
        if t is T.IDENT:
            node = self._assignment_core()
            self._expect(T.SEMICOLON, "expected ';' after assignment")
            return node
        if t is T.ELSE:
            raise self._error(tok, "'else' without a matching 'if'")
        if t is T.RBRACE:
            raise self._error(tok, "unmatched '}'", hint="remove it or add the missing '{'")
        raise self._error(tok, f"expected a statement, found {self._describe(tok)}")

    def _body_statement(self, owner: str) -> ast.Stmt:
        """Body of if/while/for: any statement except a bare declaration."""
        if self._check(T.INT, T.FLOAT):
            raise self._error(self._peek(),
                              f"a declaration cannot be the body of '{owner}'",
                              hint="wrap it in braces: { ... }")
        return self._statement()

    def _block(self) -> ast.Block:
        open_brace = self._expect(T.LBRACE, "expected '{'")
        stmts: List[ast.Stmt] = []
        while not self._check(T.RBRACE) and not self._at_end():
            self._parse_statement_safely(stmts)
        if not self._check(T.RBRACE):
            raise self._error(self._peek(),
                              f"expected '}}' to close the block opened at line {open_brace.line}")
        self._advance()
        return ast.Block(open_brace.line, open_brace.col, stmts)

    def _var_decl(self) -> ast.VarDecl:
        type_tok = self._advance()                       # 'int' / 'float'
        name_tok = self._expect(T.IDENT, f"expected a variable name after '{type_tok.lexeme}'")
        init = None
        if self._match(T.ASSIGN):
            init = self._expression()
        if self._check(T.COMMA):
            raise self._error(self._peek(), "only one variable can be declared per statement",
                              hint="write separate declarations: int a; int b;")
        self._expect(T.SEMICOLON, "expected ';' after variable declaration")
        return ast.VarDecl(name_tok.line, name_tok.col, type_tok.lexeme, name_tok.lexeme, init)

    def _assignment_core(self) -> ast.Assign:
        """IDENT = expr | IDENT += expr | IDENT++ ...  (no trailing ';')

        Compound forms are *desugared* here:  x += e   becomes   x = x + e
        so later phases only have to know about plain assignment.
        """
        name_tok = self._advance()
        nxt = self._peek()

        if nxt.type is T.ASSIGN:
            self._advance()
            value = self._expression()
        elif nxt.type in COMPOUND_ASSIGN:
            self._advance()
            rhs = self._expression()
            lhs = ast.Identifier(name_tok.line, name_tok.col, name_tok.lexeme)
            value = ast.BinaryOp(nxt.line, nxt.col, COMPOUND_ASSIGN[nxt.type], lhs, rhs)
        elif nxt.type in (T.PLUS_PLUS, T.MINUS_MINUS):
            self._advance()
            lhs = ast.Identifier(name_tok.line, name_tok.col, name_tok.lexeme)
            one = ast.IntLiteral(nxt.line, nxt.col, 1)
            op = "+" if nxt.type is T.PLUS_PLUS else "-"
            value = ast.BinaryOp(nxt.line, nxt.col, op, lhs, one)
        else:
            raise self._error(
                nxt,
                f"expected '=' after '{name_tok.lexeme}', found {self._describe(nxt)}",
                hint="a statement can start with a declaration, an assignment, "
                     "print, read, if, while, for or a block")
        return ast.Assign(name_tok.line, name_tok.col, name_tok.lexeme, value)

    def _condition(self, keyword: str) -> ast.Expr:
        """Parse '(' expression ')' used by if / while."""
        self._expect(T.LPAREN, f"expected '(' after '{keyword}'")
        expr = self._expression()
        if self._check(T.ASSIGN):
            raise self._error(self._peek(), "assignment is not allowed inside a condition",
                              hint="use '==' to compare values")
        self._expect(T.RPAREN, f"expected ')' after the {keyword} condition")
        return expr

    def _if_statement(self) -> ast.If:
        tok = self._advance()
        cond = self._condition("if")
        then_branch = self._body_statement("if")
        else_branch = None
        if self._match(T.ELSE):                 # dangling else binds to nearest if
            else_branch = self._body_statement("else")
        return ast.If(tok.line, tok.col, cond, then_branch, else_branch)

    def _while_statement(self) -> ast.While:
        tok = self._advance()
        cond = self._condition("while")
        body = self._body_statement("while")
        return ast.While(tok.line, tok.col, cond, body)

    def _for_statement(self) -> ast.For:
        tok = self._advance()
        self._expect(T.LPAREN, "expected '(' after 'for'")

        # ---- initialiser ----
        init = None
        if self._check(T.INT, T.FLOAT):
            init = self._var_decl()                       # consumes its own ';'
        elif self._check(T.IDENT):
            init = self._assignment_core()
            self._expect(T.SEMICOLON, "expected ';' after for-loop initialiser")
        else:
            self._expect(T.SEMICOLON, "expected ';' after for-loop initialiser")

        # ---- condition ----
        cond = None
        if not self._check(T.SEMICOLON):
            cond = self._expression()
        self._expect(T.SEMICOLON, "expected ';' after for-loop condition")

        # ---- update ----
        update = None
        if not self._check(T.RPAREN):
            if not self._check(T.IDENT):
                raise self._error(self._peek(), "expected an assignment as the for-loop update, "
                                                f"found {self._describe(self._peek())}")
            update = self._assignment_core()
        self._expect(T.RPAREN, "expected ')' after for-loop clauses")

        body = self._body_statement("for")
        return ast.For(tok.line, tok.col, init, cond, update, body)

    def _print_statement(self) -> ast.Print:
        tok = self._advance()
        self._expect(T.LPAREN, "expected '(' after 'print'")
        args = [self._expression()]
        while self._match(T.COMMA):
            args.append(self._expression())
        self._expect(T.RPAREN, "expected ')' after print arguments")
        self._expect(T.SEMICOLON, "expected ';' after print statement")
        return ast.Print(tok.line, tok.col, args)

    def _read_statement(self) -> ast.Read:
        tok = self._advance()
        self._expect(T.LPAREN, "expected '(' after 'read'")
        name = self._expect(T.IDENT, "expected a variable name inside read()")
        self._expect(T.RPAREN, "expected ')' after read variable")
        self._expect(T.SEMICOLON, "expected ';' after read statement")
        return ast.Read(tok.line, tok.col, name.lexeme)

    # ------------------------------------------------------------------
    # Expressions (precedence climbing, one method per level)
    # ------------------------------------------------------------------
    def _expression(self) -> ast.Expr:
        return self._or()

    def _binary_level(self, next_level, operators) -> ast.Expr:
        """Generic left-associative binary operator parsing."""
        left = next_level()
        while self._peek().type in operators:
            op = self._advance()
            right = next_level()
            left = ast.BinaryOp(op.line, op.col, op.lexeme, left, right)
        return left

    def _or(self):         return self._binary_level(self._and, {T.OR})
    def _and(self):        return self._binary_level(self._equality, {T.AND})
    def _equality(self):   return self._binary_level(self._comparison, {T.EQ, T.NEQ})
    def _comparison(self): return self._binary_level(self._term, {T.LT, T.LE, T.GT, T.GE})
    def _term(self):       return self._binary_level(self._factor, {T.PLUS, T.MINUS})
    def _factor(self):     return self._binary_level(self._unary, {T.STAR, T.SLASH, T.PERCENT})

    def _unary(self) -> ast.Expr:
        if self._check(T.MINUS, T.NOT):
            op = self._advance()
            return ast.UnaryOp(op.line, op.col, op.lexeme, self._unary())
        return self._primary()

    def _primary(self) -> ast.Expr:
        tok = self._peek()
        if tok.type is T.INT_LIT:
            self._advance()
            return ast.IntLiteral(tok.line, tok.col, tok.value)
        if tok.type is T.FLOAT_LIT:
            self._advance()
            return ast.FloatLiteral(tok.line, tok.col, tok.value)
        if tok.type is T.STRING_LIT:
            self._advance()
            return ast.StringLiteral(tok.line, tok.col, tok.value)
        if tok.type is T.IDENT:
            self._advance()
            return ast.Identifier(tok.line, tok.col, tok.lexeme)
        if tok.type is T.LPAREN:
            self._advance()
            expr = self._expression()
            self._expect(T.RPAREN, "expected ')' to close the parenthesised expression")
            return expr
        raise self._error(tok, f"expected an expression, found {self._describe(tok)}")

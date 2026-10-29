"""Tiny C compiler package.

Pipeline:  source text -> Lexer -> Parser -> SemanticAnalyzer -> CodeGenerator -> TACInterpreter

NOTE: keep this file light. Importing tinyc.main from here would make
`python -m tinyc.main` emit a runpy warning.
"""

__version__ = "1.0.0"

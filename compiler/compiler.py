"""Public entry point of the CG-Lang compiler front end.

``compile_code`` runs lexical analysis, parsing and semantic analysis and
returns a plain dictionary:

* success: ``{"status": "PASS"}``
* failure: ``{"status": "FAIL", "type": ..., "line": ..., "column": ...,
  "message": ...}`` where ``type`` is ``LEXICAL_ERROR``, ``SYNTAX_ERROR`` or
  ``SEMANTIC_ERROR``.

Two further failure types exist as safety nets so that the function never
raises: ``INVALID_INPUT`` (the argument is not a string) and
``INTERNAL_ERROR`` (an unexpected exception inside the compiler). The latter
indicates a defect in the compiler and is treated as a potential bug by the
testing framework.
"""

from .lexer import Lexer, LexerError
from .parser import Parser, ParserError
from .semantic import SemanticAnalyzer, SemanticError


def _failure(error_type, line, column, message):
    return {
        "status": "FAIL",
        "type": error_type,
        "line": line,
        "column": column,
        "message": message,
    }


def compile_code(source_code):
    if not isinstance(source_code, str):
        return _failure(
            "INVALID_INPUT",
            None,
            None,
            f"Source must be a string, got {type(source_code).__name__}",
        )

    try:
        try:
            tokens = Lexer(source_code).tokenize()
        except LexerError as e:
            return _failure("LEXICAL_ERROR", e.line, e.column, e.message)

        try:
            program = Parser(tokens).parse_program()
        except ParserError as e:
            return _failure("SYNTAX_ERROR", e.line, e.column, e.message)

        try:
            SemanticAnalyzer().analyze(program)
        except SemanticError as e:
            return _failure("SEMANTIC_ERROR", e.line, e.column, e.message)

    except Exception as e:  # noqa: BLE001 - last-resort guard, see module docstring
        return _failure(
            "INTERNAL_ERROR", None, None, f"{type(e).__name__}: {e}"
        )

    return {"status": "PASS"}

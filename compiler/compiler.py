# compiler/compiler.py

from .lexer import Lexer, LexerError
from .parser import Parser, ParserError
from .semantic import SemanticAnalyzer, SemanticError


def compile_code(source_code: str):
    # Step 1: Lexing
    try:
        lexer = Lexer(source_code)
        tokens = lexer.tokenize()
    except LexerError as e:
        return {
            "status": "FAIL",
            "type": "LEXICAL_ERROR",
            "line": e.line,
            "column": e.column,
            "message": e.message
        }

    # Step 2: Parsing
    try:
        parser = Parser(tokens)
        ast = parser.parse_program()
    except ParserError as e:
        return {
            "status": "FAIL",
            "type": "SYNTAX_ERROR",
            "line": e.line,
            "column": e.column,
            "message": e.message
        }

    # Step 3: Semantic Analysis
    try:
        analyzer = SemanticAnalyzer()
        analyzer.analyze(ast)
    except SemanticError as e:
        return {
            "status": "FAIL",
            "type": "SEMANTIC_ERROR",
            "line": e.line,
            "column": e.column,
            "message": e.message
        }

    # All good
    return {"status": "PASS"}


# Quick manual test
if __name__ == "__main__":
    tests = [
        "x = 10 + 5;",
        "x = + 10;",
        "y = x + 5;",
    ]
    for t in tests:
        print(t, "->", compile_code(t))

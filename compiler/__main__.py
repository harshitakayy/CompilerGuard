"""Command-line front end: ``python -m compiler [options] FILE | -c CODE``."""

import argparse
import json
import sys

from .compiler import compile_code
from .lexer import Lexer, LexerError
from .parser import Parser, ParserError


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m compiler", description="Compile a CG-Lang program."
    )
    parser.add_argument("file", nargs="?", help="source file ('-' reads stdin)")
    parser.add_argument("-c", "--code", help="compile this source string")
    parser.add_argument("--tokens", action="store_true", help="print the token stream")
    parser.add_argument("--ast", action="store_true", help="print the AST as JSON")
    args = parser.parse_args(argv)

    if args.code is not None:
        source = args.code
    elif args.file == "-":
        source = sys.stdin.read()
    elif args.file:
        with open(args.file, encoding="utf-8") as handle:
            source = handle.read()
    else:
        parser.error("provide a FILE or -c CODE")

    if args.tokens or args.ast:
        try:
            tokens = Lexer(source).tokenize()
            if args.tokens:
                for token in tokens:
                    print(token)
            if args.ast:
                print(json.dumps(Parser(tokens).parse_program().to_dict(), indent=2))
        except (LexerError, ParserError):
            pass  # the structured error is reported by compile_code below

    result = compile_code(source)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Compiler facade: lex -> parse -> semantic analysis -> run.

`compile_source()` NEVER raises. It returns a structured result dict:
  status      PASS | FAIL | CRASH      (CRASH = unexpected internal exception = real bug)
  error_type  LEXICAL_ERROR | SYNTAX_ERROR | SEMANTIC_ERROR | RUNTIME_ERROR | LIMIT_ERROR | None
  signature   short normalised id of the outcome (used for coverage / error patterns)
"""
import re
import traceback
from .errors import CompilerError
from .lexer import tokenize
from .parser import Parser
from .semantic import SemanticAnalyzer
from .interpreter import Interpreter
from .ast_nodes import ast_to_dict

MAX_SOURCE = 100000

# Deliberately plantable bugs (fault injection / mutation analysis of the compiler itself).
FAULTS = {
    "sub_right_assoc": "Parser treats '-' as right-associative (10 - 3 - 2 gives 9)",
    "mod_wrong": "Interpreter evaluates '%' as integer division '//'",
    "paren_unbalanced_accept": "Parser accepts '(' ... ';' with the closing ')' missing",
    "div_zero_unchecked": "Division by zero is not checked (internal crash)",
    "undefined_var_unchecked": "Undefined variables are accepted and silently read as 0",
    "no_depth_limit": "Nesting-depth guard removed (deep nesting crashes with RecursionError)",
}


def _normalize(msg):
    return re.sub(r"'[^']*'", "'_'", msg or "")


def signature_of(res):
    if res["status"] == "PASS":
        return "PASS"
    if res["status"] == "CRASH":
        return "CRASH: " + (res.get("crash") or "Exception")
    return "%s: %s" % (res["error_type"], _normalize(res["message"]))


def compile_source(source, faults=(), detail=False, run=True):
    faults = frozenset(faults or ())
    cov = set()
    res = {"status": "PASS", "error_type": None, "message": None, "line": None, "col": None,
           "output": [], "warnings": [], "crash": None, "traceback": None}
    try:
        if not isinstance(source, str):
            raise CompilerError("INPUT_ERROR", "Source must be text")
        if len(source) > MAX_SOURCE:
            raise CompilerError("LIMIT_ERROR", "Source too large")
        tokens = tokenize(source, cov)
        if detail:
            res["tokens"] = [{"type": t.type, "text": t.text, "line": t.line, "col": t.col}
                             for t in tokens if t.type != "EOF"]
        program = Parser(tokens, faults, cov).parse()
        if detail:
            res["ast"] = ast_to_dict(program)
        res["warnings"] = SemanticAnalyzer(faults, cov).analyze(program)
        if run:
            res["output"] = Interpreter(faults, cov).run(program)
    except CompilerError as e:
        res.update(status="FAIL", error_type=e.error_type, message=e.message,
                   line=e.line, col=e.col, output=[])
    except RecursionError:
        if "no_depth_limit" in faults:
            res.update(status="CRASH", crash="RecursionError", message="maximum recursion depth exceeded",
                       output=[])
        else:
            res.update(status="FAIL", error_type="LIMIT_ERROR",
                       message="Expression too deeply nested", output=[])
    except Exception as e:                          # unexpected -> a REAL compiler bug
        res.update(status="CRASH", crash=type(e).__name__, message=str(e), output=[],
                   traceback=traceback.format_exc(limit=4))
    res["signature"] = signature_of(res)
    cov.add("sig:" + res["signature"])
    res["coverage"] = sorted(cov)
    return res

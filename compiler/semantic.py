"""Semantic analysis: undefined variables, constant division by zero, unused-variable warnings."""
from .ast_nodes import *
from .errors import CompilerError


class SemanticAnalyzer:
    def __init__(self, faults=(), cov=None):
        self.faults = set(faults)
        self.cov = cov if cov is not None else set()
        self.assigned, self.used = {}, set()
        self.warnings = []

    def analyze(self, program):
        self.block(program.stmts, set())
        for name, (line, col) in self.assigned.items():
            if name not in self.used:
                self.warnings.append({"line": line, "col": col,
                                      "message": "Variable '%s' is assigned but never used" % name})
        return self.warnings

    def block(self, stmts, defined):
        for s in stmts:
            defined = self.stmt(s, defined)
        return defined

    def stmt(self, s, defined):
        if isinstance(s, Assign):
            self.expr(s.expr, defined)
            self.assigned.setdefault(s.name, (s.line, s.col))
            self.cov.add("sem:assign")
            return defined | {s.name}
        if isinstance(s, Print):
            self.expr(s.expr, defined)
            return defined
        if isinstance(s, If):
            self.expr(s.cond, defined)
            a = self.block(s.then, set(defined))
            if s.otherwise is not None:
                b = self.block(s.otherwise, set(defined))
                self.cov.add("sem:if-else-merge")
                return defined | (a & b)      # defined on *both* paths only
            return defined
        if isinstance(s, While):
            self.expr(s.cond, defined)
            self.block(s.body, set(defined))
            return defined
        return defined

    def expr(self, e, defined):
        if isinstance(e, Var):
            self.used.add(e.name)
            self.cov.add("sem:var-use")
            if e.name not in defined and "undefined_var_unchecked" not in self.faults:
                raise CompilerError("SEMANTIC_ERROR", "Undefined variable '%s'" % e.name, e.line, e.col)
        elif isinstance(e, Unary):
            self.expr(e.operand, defined)
        elif isinstance(e, (BinOp, Compare)):
            self.expr(e.left, defined)
            self.expr(e.right, defined)
            if (isinstance(e, BinOp) and e.op in "/%" and isinstance(e.right, Num)
                    and e.right.value == 0 and "div_zero_unchecked" not in self.faults):
                self.cov.add("sem:div-by-zero")
                raise CompilerError("SEMANTIC_ERROR", "Division by zero", e.line, e.col)

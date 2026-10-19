"""Tree-walking interpreter used to *run* compiled CG-Lang programs."""
from .ast_nodes import *
from .errors import CompilerError

MAX_STEPS = 200000
MAX_BITS = 10000


class Interpreter:
    def __init__(self, faults=(), cov=None):
        self.faults = set(faults)
        self.cov = cov if cov is not None else set()
        self.env, self.out, self.steps = {}, [], 0

    def run(self, program):
        self.block(program.stmts)
        return self.out

    def tick(self, node):
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise CompilerError("RUNTIME_ERROR",
                                "Execution step limit exceeded (possible infinite loop)",
                                getattr(node, "line", 0), getattr(node, "col", 0))

    def block(self, stmts):
        for s in stmts:
            self.stmt(s)

    def stmt(self, s):
        self.tick(s)
        if isinstance(s, Assign):
            self.env[s.name] = self.eval(s.expr)
        elif isinstance(s, Print):
            v = self.eval(s.expr)
            self.out.append(str(v))
            self.cov.add("run:print")
        elif isinstance(s, If):
            if self.eval(s.cond):
                self.block(s.then)
            elif s.otherwise is not None:
                self.block(s.otherwise)
        elif isinstance(s, While):
            while self.eval(s.cond):
                self.tick(s)
                self.block(s.body)

    def eval(self, e):
        if isinstance(e, Num):
            return e.value
        if isinstance(e, Var):
            if "undefined_var_unchecked" in self.faults:
                return self.env.get(e.name, 0)           # FAULT: silently yields 0
            if e.name not in self.env:
                raise CompilerError("RUNTIME_ERROR", "Undefined variable '%s'" % e.name, e.line, e.col)
            return self.env[e.name]
        if isinstance(e, Unary):
            return -self.eval(e.operand)
        if isinstance(e, Compare):
            l, r = self.eval(e.left), self.eval(e.right)
            return {"==": l == r, "!=": l != r, "<": l < r, "<=": l <= r,
                    ">": l > r, ">=": l >= r}[e.op]
        if isinstance(e, BinOp):
            l, r = self.eval(e.left), self.eval(e.right)
            try:
                if e.op == "+":
                    v = l + r
                elif e.op == "-":
                    v = l - r
                elif e.op == "*":
                    v = l * r
                elif e.op == "/":
                    if "div_zero_unchecked" in self.faults:
                        v = l / r                         # FAULT: ZeroDivisionError escapes
                    else:
                        if r == 0:
                            raise CompilerError("RUNTIME_ERROR", "Division by zero", e.line, e.col)
                        v = l / r
                else:
                    if r == 0 and "div_zero_unchecked" not in self.faults:
                        raise CompilerError("RUNTIME_ERROR", "Division by zero", e.line, e.col)
                    v = (l // r) if "mod_wrong" in self.faults else (l % r)   # FAULT: % as //
            except OverflowError:
                raise CompilerError("RUNTIME_ERROR", "Numeric overflow", e.line, e.col)
            if isinstance(v, int) and v.bit_length() > MAX_BITS:
                raise CompilerError("RUNTIME_ERROR", "Numeric overflow (value too large)", e.line, e.col)
            return v
        raise CompilerError("RUNTIME_ERROR", "Unknown expression", 0, 0)

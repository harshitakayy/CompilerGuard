"""Recursive-descent parser for CG-Lang.

Grammar
  program   := statement* EOF
  statement := 'print' expr ';' | IDENT '=' expr ';'
             | 'if' '(' cond ')' block ['else' block]
             | 'while' '(' cond ')' block
  block     := '{' statement* '}'
  cond      := expr ('==' | '!=' | '<' | '<=' | '>' | '>=') expr
  expr      := term (('+' | '-') term)*
  term      := unary (('*' | '/' | '%') unary)*
  unary     := '-' unary | primary
  primary   := NUMBER | IDENT | '(' expr ')'
"""
from .ast_nodes import *
from .errors import CompilerError

RELOPS = {"EQ", "NE", "LT", "LE", "GT", "GE"}
MAX_DEPTH = 100


class Parser:
    def __init__(self, tokens, faults=(), cov=None):
        self.toks = tokens
        self.i = 0
        self.faults = set(faults)
        self.cov = cov if cov is not None else set()
        self.depth = 0

    # ---- helpers
    @property
    def cur(self):
        return self.toks[self.i]

    def error(self, msg, tok=None):
        tok = tok or self.cur
        return CompilerError("SYNTAX_ERROR", msg, tok.line, tok.col)

    def expect(self, ttype):
        tok = self.cur
        if tok.type != ttype:
            raise self.error("Expected %s but got %s" % (ttype, tok.type))
        self.i += 1
        return tok

    def enter(self):
        self.depth += 1
        if self.depth > MAX_DEPTH and "no_depth_limit" not in self.faults:
            raise CompilerError("LIMIT_ERROR", "Nesting too deep (limit %d)" % MAX_DEPTH,
                                self.cur.line, self.cur.col)

    def leave(self):
        self.depth -= 1

    # ---- grammar
    def parse(self):
        stmts = []
        while self.cur.type != "EOF":
            stmts.append(self.statement())
        self.cov.add("parse:program")
        return Program(stmts)

    def block(self):
        self.expect("LBRACE")
        self.enter()
        stmts = []
        while self.cur.type != "RBRACE":
            if self.cur.type == "EOF":
                raise self.error("Expected RBRACE but got EOF")
            stmts.append(self.statement())
        self.leave()
        self.expect("RBRACE")
        self.cov.add("parse:block")
        return stmts

    def statement(self):
        tok = self.cur
        if tok.type == "PRINT":
            self.i += 1
            e = self.expr()
            self.expect("SEMICOLON")
            self.cov.add("parse:print")
            return Print(e, tok.line, tok.col)
        if tok.type == "IDENT":
            self.i += 1
            self.expect("ASSIGN")
            e = self.expr()
            self.expect("SEMICOLON")
            self.cov.add("parse:assign")
            return Assign(tok.text, e, tok.line, tok.col)
        if tok.type == "IF":
            self.i += 1
            self.expect("LPAREN")
            c = self.condition()
            self.expect("RPAREN")
            then = self.block()
            other = None
            if self.cur.type == "ELSE":
                self.i += 1
                other = self.block()
                self.cov.add("parse:else")
            self.cov.add("parse:if")
            return If(c, then, other, tok.line, tok.col)
        if tok.type == "WHILE":
            self.i += 1
            self.expect("LPAREN")
            c = self.condition()
            self.expect("RPAREN")
            body = self.block()
            self.cov.add("parse:while")
            return While(c, body, tok.line, tok.col)
        raise self.error("Expected statement but got %s" % tok.type)

    def condition(self):
        left = self.expr()
        tok = self.cur
        if tok.type not in RELOPS:
            raise self.error("Expected comparison operator but got %s" % tok.type)
        self.i += 1
        right = self.expr()
        self.cov.add("parse:compare:" + tok.type)
        return Compare(tok.text, left, right, tok.line, tok.col)

    def expr(self):
        left = self.term()
        while self.cur.type in ("PLUS", "MINUS"):
            op = self.cur
            self.i += 1
            if op.type == "MINUS" and "sub_right_assoc" in self.faults:
                right = self.expr()          # FAULT: makes '-' right-associative
            else:
                right = self.term()
            self.cov.add("parse:binop:" + op.text)
            left = BinOp(op.text, left, right, op.line, op.col)
        return left

    def term(self):
        left = self.unary()
        while self.cur.type in ("STAR", "SLASH", "PERCENT"):
            op = self.cur
            self.i += 1
            right = self.unary()
            self.cov.add("parse:binop:" + op.text)
            left = BinOp(op.text, left, right, op.line, op.col)
        return left

    def unary(self):
        tok = self.cur
        if tok.type == "MINUS":
            self.i += 1
            self.enter()
            operand = self.unary()
            self.leave()
            self.cov.add("parse:unary")
            return Unary("-", operand, tok.line, tok.col)
        return self.primary()

    def primary(self):
        tok = self.cur
        if tok.type == "NUMBER":
            self.i += 1
            return Num(tok.value, tok.line, tok.col)
        if tok.type == "IDENT":
            self.i += 1
            return Var(tok.text, tok.line, tok.col)
        if tok.type == "LPAREN":
            self.i += 1
            self.enter()
            e = self.expr()
            self.leave()
            if self.cur.type == "RPAREN":
                self.i += 1
            elif "paren_unbalanced_accept" in self.faults and self.cur.type == "SEMICOLON":
                pass                          # FAULT: silently accepts a missing ')'
            else:
                raise self.error("Expected RPAREN but got %s" % self.cur.type)
            self.cov.add("parse:paren")
            return e
        raise self.error("Expected expression but got %s" % tok.type)

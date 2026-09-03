# compiler/semantic.py
from .ast import Assignment, BinOp, Number, Identifier, If, While


class SemanticError(Exception):
    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(message)


class SemanticAnalyzer:
    def __init__(self):
        self.declared_vars = set()

    def analyze(self, program_node):
        for stmt in program_node.statements:
            self.check_statement(stmt)

    def check_statement(self, stmt):
        if isinstance(stmt, Assignment):
            self.check_expression(stmt.expression)
            self.declared_vars.add(stmt.identifier)

        elif isinstance(stmt, If):
            self.check_expression(stmt.condition)
            for s in stmt.then_branch:
                self.check_statement(s)
            if stmt.else_branch:
                for s in stmt.else_branch:
                    self.check_statement(s)

        elif isinstance(stmt, While):
            self.check_expression(stmt.condition)
            for s in stmt.body:
                self.check_statement(s)

    def check_expression(self, node):
        if isinstance(node, Number):
            return
        if isinstance(node, Identifier):
            if node.name not in self.declared_vars:
                raise SemanticError(
                    f"Variable '{node.name}' is undefined",
                    node.line,
                    node.column
                )
            return
        if isinstance(node, BinOp):
            self.check_expression(node.left)
            self.check_expression(node.right)
            return

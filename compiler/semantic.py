# compiler/semantic.py

from .ast import Assignment, BinOp, Number, Identifier


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
            # Check the right-hand side BEFORE declaring the variable
            self.check_expression(stmt.expression)
            self.declared_vars.add(stmt.identifier)

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

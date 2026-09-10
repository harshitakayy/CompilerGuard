# compiler/semantic.py
from .ast import Assignment, BinOp, Number, Identifier, If, While


class SemanticError(Exception):
    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(message)


class SemanticAnalyzer:
    def __init__(self):#constructor->      naya analyzer object banate waqt chalega
        self.declared_vars = set()#khaali SET (list jaisa, but duplicate values nahi rakhta)
        # ismein hum track karenge ab tak kaunse variables assign ho chuke hain


    def analyze(self, program_node):
        for stmt in program_node.statements:
            self.check_statement(stmt)

    def check_statement(self, stmt):
        if isinstance(stmt, Assignment):# agar ye ek Assignment hai (jaise "x = 10 + 5;")
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

    def check_expression(self, node):# Ek expression (tree ka part) ko recursively check karta hai
        # Dekhta hai node KIS TYPE ka hai, phir uske hisaab se handle karta hai

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
            self.check_expression(node.left)#checks left
            self.check_expression(node.right)#ye ryt ko 
            return# return safe nothing basically

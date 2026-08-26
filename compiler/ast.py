# compiler/ast.py

class ASTNode:
    pass


class Program(ASTNode):
    def __init__(self, statements):
        self.statements = statements

    def __repr__(self):
        return f"Program({self.statements})"


class Assignment(ASTNode):
    def __init__(self, identifier, expression, line, column):
        self.identifier = identifier
        self.expression = expression
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Assignment({self.identifier} = {self.expression})"


class BinOp(ASTNode):
    def __init__(self, left, op, right, line, column):
        self.left = left
        self.op = op
        self.right = right
        self.line = line
        self.column = column

    def __repr__(self):
        return f"BinOp({self.left} {self.op} {self.right})"


class Number(ASTNode):
    def __init__(self, value, line, column):
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Number({self.value})"


class Identifier(ASTNode):
    def __init__(self, name, line, column):
        self.name = name
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Identifier({self.name})"

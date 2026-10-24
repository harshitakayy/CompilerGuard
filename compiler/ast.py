"""Abstract syntax tree node definitions for CG-Lang.

``Program``, ``Assignment``, ``BinOp``, ``Number`` and ``Identifier`` are
produced by the parser. ``If`` and ``While`` are reserved for a future grammar
extension: the parser does not currently construct them.
"""


class ASTNode:
    """Base class for all AST nodes."""

    def to_dict(self):
        """Return a JSON-serialisable representation of the subtree."""
        data = {"node": type(self).__name__}
        for key, value in vars(self).items():
            data[key] = _serialise(value)
        return data


def _serialise(value):
    if isinstance(value, ASTNode):
        return value.to_dict()
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    return value


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


class If(ASTNode):
    """Reserved for a future extension (not produced by the parser)."""

    def __init__(self, condition, then_branch, else_branch, line, column):
        self.condition = condition
        self.then_branch = then_branch
        self.else_branch = else_branch
        self.line = line
        self.column = column

    def __repr__(self):
        return (
            f"If({self.condition}, then={self.then_branch}, "
            f"else={self.else_branch})"
        )


class While(ASTNode):
    """Reserved for a future extension (not produced by the parser)."""

    def __init__(self, condition, body, line, column):
        self.condition = condition
        self.body = body
        self.line = line
        self.column = column

    def __repr__(self):
        return f"While({self.condition}, body={self.body})"

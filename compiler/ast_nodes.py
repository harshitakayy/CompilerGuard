"""AST node definitions (named ast_nodes.py so it never shadows Python's stdlib `ast`)."""
from dataclasses import dataclass, field, fields, is_dataclass
from typing import List, Optional, Any


@dataclass
class Num:
    value: Any
    line: int = 0
    col: int = 0


@dataclass
class Var:
    name: str
    line: int = 0
    col: int = 0


@dataclass
class Unary:
    op: str
    operand: Any
    line: int = 0
    col: int = 0


@dataclass
class BinOp:
    op: str
    left: Any
    right: Any
    line: int = 0
    col: int = 0


@dataclass
class Compare:
    op: str
    left: Any
    right: Any
    line: int = 0
    col: int = 0


@dataclass
class Assign:
    name: str
    expr: Any
    line: int = 0
    col: int = 0


@dataclass
class Print:
    expr: Any
    line: int = 0
    col: int = 0


@dataclass
class If:
    cond: Any
    then: List[Any] = field(default_factory=list)
    otherwise: Optional[List[Any]] = None
    line: int = 0
    col: int = 0


@dataclass
class While:
    cond: Any
    body: List[Any] = field(default_factory=list)
    line: int = 0
    col: int = 0


@dataclass
class Program:
    stmts: List[Any] = field(default_factory=list)


def ast_to_dict(node):
    if is_dataclass(node):
        d = {"node": type(node).__name__}
        for f in fields(node):
            if f.name in ("line", "col"):
                continue
            d[f.name] = ast_to_dict(getattr(node, f.name))
        return d
    if isinstance(node, list):
        return [ast_to_dict(x) for x in node]
    return node

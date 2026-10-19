# compiler/ast.py
# Ye file batati hai ki parsed code ka "tree structure" kaisa dikhega
#har ek code is diff type of node jo tree mein alag leaf hota h
class ASTNode:#sb isi se inherit krenge nodes
    pass#just label nothing inisde it


class Program(ASTNode):
    def __init__(self, statements):# Constructor - jab Program(...) banega, ye chalega
        self.statements = statements# statements ki poori list store kar li (jaise: [x=10, y=20])

    def __repr__(self):# VERY IMPORTANT, this is for print(object printing), this will be shown for debugging
        return f"Program({self.statements})"


class Assignment(ASTNode):
    def __init__(self, identifier, expression, line, column):#constuctor takes 4 things
        self.identifier = identifier#variable
        self.expression = expression#ryt side of x=10+5;
        self.line = line#error reporting ke liye if needed line number
        self.column = column

    def __repr__(self):
        return f"Assignment({self.identifier} = {self.expression})"#print ke time pe


class BinOp(ASTNode):
    def __init__(self, left, op, right, line, column):
        self.left = left
        self.op = op
        self.right = right
        self.line = line
        self.column = column #to store everything via object defn

    def __repr__(self):
        return f"BinOp({self.left} {self.op} {self.right})"


class Number(ASTNode): # Ek plain number, jaise 10, 42
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


 # NAYA: if-else statement ko represent karta hai
    # jaise: if (x > 5) { y = 10; } else { y = 20; }

class If(ASTNode): 
    def __init__(self, condition, then_branch, else_branch, line, column):
        self.condition = condition
        self.then_branch = then_branch    # list of statements
        self.else_branch = else_branch    # list of statements or None
        self.line = line
        self.column = column

    def __repr__(self):
        return f"If({self.condition}, then={self.then_branch}, else={self.else_branch})"


class While(ASTNode):
    def __init__(self, condition, body, line, column):
        self.condition = condition
        self.body = body   # list of statements
        self.line = line
        self.column = column

    def __repr__(self):
        return f"While({self.condition}, body={self.body})"
# compiler/parser.py

from .ast import Program, Assignment, BinOp, Number, Identifier
#ast.py se saari node-classes import kar li, taaki tree banate waqt
# inko use kar sake

class ParserError(Exception):
    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(message)


class Parser:# Constructor - Lexer se aayi hui tokens ki list leta hai

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def current(self):
        return self.tokens[self.pos]

    def peek_next(self):
        if self.pos + 1 < len(self.tokens):
            return self.tokens[self.pos + 1]
        return self.tokens[-1]

    def eat(self, token_type):
                # "Eat" ka matlab: expected token check karo, phir aage badho
        # Ye SABSE IMPORTANT helper function hai, baaki sab isko use karte hain

        #token type= expected example x=10;
        tok = self.current()#current token type
        if tok.type != token_type:
            raise ParserError(
                f"Expected {token_type} but got {tok.type}",
                tok.line,
                tok.column
            )
        self.pos += 1
        return tok

    
# PROGRAM → STATEMENT*  (grammar rule)
        # Matlab: jab tak EOF na mile, statements padhte rah
    def parse_program(self):
        statements = []
        while self.current().type != 'EOF':
            statements.append(self.parse_statement())
        return Program(statements)

    def parse_statement(self):
        # STATEMENT → ID = EXPR ;  (grammar rule)
        # Matlab: variable naam, fir "=", fir expression, fir ";"

        id_tok = self.eat('ID')
        self.eat('ASSIGN')
        expr = self.parse_expression()
        self.eat('SEMICOLON')
        return Assignment(id_tok.value, expr, id_tok.line, id_tok.column)

    def parse_expression(self):
        # EXPR → TERM (('+' | '-') TERM)*  (grammar rule)
        # Matlab: pehle ek term padho, fir jab tak +/- mile, aur terms jodte raho

        node = self.parse_term()
        while self.current().type in ('PLUS', 'MINUS'):
            op_tok = self.current()
            self.eat(op_tok.type)
            right = self.parse_term()
            node = BinOp(node, op_tok.value, right, op_tok.line, op_tok.column)
            # ab tak jo bhi bana tha (node) aur naya term (right) ko
            # ek BinOp me jod diya - isse chaining hoti hai: "10 + 5 - 3"
        return node

    def parse_term(self):
        # TERM → FACTOR (('*' | '/') FACTOR)*  (grammar rule)
        # Bilkul parse_expression() jaisa hi, lekin * aur / ke liye
        # (isliye multiplication/division, addition se pehle priority milti hai -
        #  BODMAS/precedence yahi se aata hai)

        node = self.parse_factor()
        while self.current().type in ('MULTIPLY', 'DIVIDE'):
            op_tok = self.current()
            self.eat(op_tok.type)
            right = self.parse_factor()
            node = BinOp(node, op_tok.value, right, op_tok.line, op_tok.column)
        return node

    def parse_factor(self): # FACTOR → NUMBER | ID | ( EXPR )  (grammar rule)
        # Ye sabse "chhota" unit hai - ek number, ek variable, ya bracket wala expression

        tok = self.current()

        if tok.type == 'NUMBER':
            self.eat('NUMBER')#usko consume kia
            return Number(tok.value, tok.line, tok.column)

        if tok.type == 'ID':
            self.eat('ID')
            return Identifier(tok.value, tok.line, tok.column)

        if tok.type == 'LPAREN':
            self.eat('LPAREN')
            node = self.parse_expression()
            self.eat('RPAREN')
            return node

        raise ParserError(###error again if not anything from above
            f"Expected expression but got {tok.type}",
            tok.line,
            tok.column
        )
# compiler/parser.py

from .ast import Program, Assignment, BinOp, Number, Identifier


class ParserError(Exception):
    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(message)


class Parser:
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
        tok = self.current()
        if tok.type != token_type:
            raise ParserError(
                f"Expected {token_type} but got {tok.type}",
                tok.line,
                tok.column
            )
        self.pos += 1
        return tok

    def parse_program(self):
        statements = []
        while self.current().type != 'EOF':
            statements.append(self.parse_statement())
        return Program(statements)

    def parse_statement(self):
        id_tok = self.eat('ID')
        self.eat('ASSIGN')
        expr = self.parse_expression()
        self.eat('SEMICOLON')
        return Assignment(id_tok.value, expr, id_tok.line, id_tok.column)

    def parse_expression(self):
        node = self.parse_term()
        while self.current().type in ('PLUS', 'MINUS'):
            op_tok = self.current()
            self.eat(op_tok.type)
            right = self.parse_term()
            node = BinOp(node, op_tok.value, right, op_tok.line, op_tok.column)
        return node

    def parse_term(self):
        node = self.parse_factor()
        while self.current().type in ('MULTIPLY', 'DIVIDE'):
            op_tok = self.current()
            self.eat(op_tok.type)
            right = self.parse_factor()
            node = BinOp(node, op_tok.value, right, op_tok.line, op_tok.column)
        return node

    def parse_factor(self):
        tok = self.current()

        if tok.type == 'NUMBER':
            self.eat('NUMBER')
            return Number(tok.value, tok.line, tok.column)

        if tok.type == 'ID':
            self.eat('ID')
            return Identifier(tok.value, tok.line, tok.column)

        if tok.type == 'LPAREN':
            self.eat('LPAREN')
            node = self.parse_expression()
            self.eat('RPAREN')
            return node

        raise ParserError(
            f"Expected expression but got {tok.type}",
            tok.line,
            tok.column
        )

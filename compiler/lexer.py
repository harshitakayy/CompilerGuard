# compiler/lexer.py

class LexerError(Exception):
    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(message)


class Token:
    def __init__(self, type_, value, line, column):
        self.type = type_
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.type}, {repr(self.value)}, line={self.line}, col={self.column})"


TOKEN_TYPES = {
    '+': 'PLUS',
    '-': 'MINUS',
    '*': 'MULTIPLY',
    '/': 'DIVIDE',
    '=': 'ASSIGN',
    '(': 'LPAREN',
    ')': 'RPAREN',
    ';': 'SEMICOLON',
}


class Lexer:
    def __init__(self, source_code):
        self.source = source_code
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens = []

    def current_char(self):
        if self.pos < len(self.source):
            return self.source[self.pos]
        return None

    def advance(self):
        char = self.current_char()
        if char == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        self.pos += 1

    def peek(self):
        peek_pos = self.pos + 1
        if peek_pos < len(self.source):
            return self.source[peek_pos]
        return None

    def skip_whitespace(self):
        while self.current_char() is not None and self.current_char() in ' \t\n\r':
            self.advance()

    def read_number(self):
        start_line, start_col = self.line, self.column
        result = ''
        while self.current_char() is not None and self.current_char().isdigit():
            result += self.current_char()
            self.advance()
        return Token('NUMBER', result, start_line, start_col)

    def read_identifier(self):
        start_line, start_col = self.line, self.column
        result = ''
        while self.current_char() is not None and (self.current_char().isalnum() or self.current_char() == '_'):
            result += self.current_char()
            self.advance()
        return Token('ID', result, start_line, start_col)

    def tokenize(self):
        while self.current_char() is not None:
            char = self.current_char()

            if char in ' \t\n\r':
                self.skip_whitespace()
                continue

            if char.isdigit():
                self.tokens.append(self.read_number())
                continue

            if char.isalpha() or char == '_':
                self.tokens.append(self.read_identifier())
                continue

            if char in TOKEN_TYPES:
                start_line, start_col = self.line, self.column
                token_type = TOKEN_TYPES[char]
                self.advance()
                self.tokens.append(Token(token_type, char, start_line, start_col))
                continue

            # Unknown character = lexical error
            raise LexerError(
                f"Unexpected character '{char}'",
                self.line,
                self.column
            )

        self.tokens.append(Token('EOF', None, self.line, self.column))
        return self.tokens


# Quick manual test (only runs if you execute this file directly)
if __name__ == "__main__":
    code = "x = 10 + 5;"
    lexer = Lexer(code)
    for tok in lexer.tokenize():
        print(tok)

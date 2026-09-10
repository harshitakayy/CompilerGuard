# compiler/lexer.py
class LexerError(Exception): #built -in exception ko handle krta h
    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(message) #from parent class exception 


class Token:
    def __init__(self, type_, value, line, column):
        self.type = type_
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.type}, {repr(self.value)}, line={self.line}, col={self.column})"


SINGLE_CHAR_TOKENS = {
    '+': 'PLUS',
    '-': 'MINUS',
    '*': 'MULTIPLY',
    '/': 'DIVIDE',
    '(': 'LPAREN',
    ')': 'RPAREN',
    ';': 'SEMICOLON',
    '{': 'LBRACE',
    '}': 'RBRACE',
}

KEYWORDS = {
    'if': 'IF',
    'else': 'ELSE',
    'while': 'WHILE',
}


class Lexer:
    def __init__(self, source_code):#poora input code (jaise "x = 10;") ek jagah store kar diya
        self.source = source_code
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens = []

    def current_char(self):
        if self.pos < len(self.source):
            return self.source[self.pos]
        return None

    def advance(self):#ye moving of char explain krta hai, like new line pe move krna after finding\n
        char = self.current_char()
        if char == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        self.pos += 1

    def peek(self):#not moving just seeing next char
        peek_pos = self.pos + 1
        if peek_pos < len(self.source):
            return self.source[peek_pos]
        return None# jab hmne saara peek kr lia n kuch nhi bacha

    def skip_whitespace(self):
        while self.current_char() is not None and self.current_char() in ' \t\n\r':
            self.advance()#to move to next character

    def read_number(self):# Ek pura number padhna, jaise "123"
        start_line, start_col = self.line, self.column#number kaha se shuru ho raha hai, wo yaad rakh liya (error reporting ke liye)
        result = ''#khali string jismein digit store krenge 
        while self.current_char() is not None and self.current_char().isdigit():
            result += self.current_char()
            self.advance()#to move to next character
        return Token('NUMBER', result, start_line, start_col)

    def read_identifier(self):
        start_line, start_col = self.line, self.column
        result = ''#khali string jismein digit store krenge
        while self.current_char() is not None and (self.current_char().isalnum() or self.current_char() == '_'):
            result += self.current_char()
            self.advance()
        if result in KEYWORDS:
            return Token(KEYWORDS[result], result, start_line, start_col)
        return Token('ID', result, start_line, start_col)

    def read_operator_or_comparison(self):
        start_line, start_col = self.line, self.column
        char = self.current_char()
        nxt = self.peek()

        if char == '=' and nxt == '=':
            self.advance(); self.advance()
            return Token('EQ', '==', start_line, start_col)
        if char == '!' and nxt == '=':
            self.advance(); self.advance()
            return Token('NEQ', '!=', start_line, start_col)
        if char == '<' and nxt == '=':
            self.advance(); self.advance()
            return Token('LTE', '<=', start_line, start_col)
        if char == '>' and nxt == '=':
            self.advance(); self.advance()
            return Token('GTE', '>=', start_line, start_col)
        if char == '=':
            self.advance()
            return Token('ASSIGN', '=', start_line, start_col)
        if char == '<':
            self.advance()
            return Token('LT', '<', start_line, start_col)
        if char == '>':
            self.advance()
            return Token('GT', '>', start_line, start_col)

        raise LexerError(f"Unexpected character '{char}'", start_line, start_col)

    def tokenize(self):# MAIN function - poora source code padh ke sab tokens ki list banata hai
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

            if char in ('=', '!', '<', '>'):
                self.tokens.append(self.read_operator_or_comparison())
                continue

            if char in SINGLE_CHAR_TOKENS:
                start_line, start_col = self.line, self.column#position yaad rkho
                token_type = SINGLE_CHAR_TOKENS[char]#uska type nikal lo dictionary se
                self.advance()
                self.tokens.append(Token(token_type, char, start_line, start_col))#uska token bana ke list me daal do
                continue

            raise LexerError(f"Unexpected character '{char}'", self.line, self.column)

        self.tokens.append(Token('EOF', None, self.line, self.column))#(batata hai input yahi khatam hua)
        return self.tokens# ppori ki poori list return kr di


if __name__ == "__main__":# Ye sirf tab chalta hai jab ye file directly run kare
    code = "if (x > 5) { y = 10; } else { y = 20; }"
    lexer = Lexer(code)#sample code ka object test kia
    for tok in lexer.tokenize():
        print(tok)

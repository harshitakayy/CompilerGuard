# CompilerGuard

CompilerGuard is an AI-guided compiler testing framework designed to automatically generate test programs, detect compiler errors, and use AI to generate targeted test cases.

## Problem

Testing a compiler manually with a small number of test programs may not expose different syntax and parsing edge cases.

CompilerGuard automates this process by generating valid and invalid programs and testing them against a mini compiler.

## Proposed Solution

The system combines:

- Grammar-based test generation
- Mutation-based invalid test generation
- Automated test execution
- Structured compiler error detection
- AI-guided targeted test generation

## System Architecture

```text
                         COMPILERGUARD
                              |
                +-------------+-------------+
                |                           |
                v                           v
          MINI COMPILER              TEST GENERATOR
                |                    /            \
                |                   /              \
                |            Valid Tests      Invalid Mutations
                |                   \              /
                +--------------------+------------+
                                     |
                                     v
                                TEST RUNNER
                                     |
                                     v
                              ERROR ANALYSIS
                                     |
                                     v
                                 AI ENGINE
                                     |
                                     v
                           TARGETED TEST CASES
                                     |
                                     v
                              MINI COMPILER
```

## CG-Lang

CompilerGuard currently uses a small programming language called **CG-Lang**.

Supported constructs include:

- Variable assignment
- Numbers
- Variables
- Addition
- Subtraction
- Multiplication
- Division
- Parenthesized expressions

### Example

```text
x = 10 + 5;
y = x * 2;
z = (y + 4) / 2;
```

## Current Implementation

### 1. Test Generator

The test generator uses the CG-Lang grammar to automatically create valid programs.

Example generated programs:

```text
x = 5;
y = 10 + 20;
z = (5 + 2) * 3;
```

The programs are generated automatically rather than being manually written.

### 2. Mutation Generator

The mutation generator takes valid programs and deliberately modifies them to create invalid programs.

Examples:

```text
x = + 10;
x = 10 +;
x = (10 + 5;
x 10 + 5;
x = 10 + 5
```

These invalid programs are used to test how the compiler handles syntax errors.

### 3. Test Runner

The test runner automatically sends generated programs to the compiler and records the results.

The compiler returns structured results such as:

```text
PASS
```

or:

```text
FAIL
SYNTAX_ERROR
Expected expression but got PLUS
```

The runner then summarizes the testing results.

### 4. AI Engine

Compiler error information is sent to an AI model.

The AI analyzes the observed error patterns and generates new test cases designed to explore similar compiler edge cases.

Example:

```text
Compiler Error:
Expected RPAREN but got SEMICOLON

        ↓

AI

        ↓

Generated Test:
x = (10 + 5;
```

These AI-generated tests are then sent back to the compiler for testing.

## AI-Guided Testing Pipeline

```text
Generated Tests
       |
       v
    Compiler
       |
       v
Compiler Results
       |
       v
 Error Patterns
       |
       v
      AI
       |
       v
Targeted Test Cases
       |
       v
    Compiler
       |
       v
New Results
```

The AI component is therefore used as a **targeted test generation mechanism**, rather than simply being added as a standalone chatbot feature.

## Current Prototype Results

The current prototype successfully demonstrates:

- 10/10 valid programs accepted
- 10/10 invalid programs rejected
- 10 compiler error patterns collected
- 5 AI-generated targeted test cases
- AI-generated tests executed against the compiler

Example output:

```text
========== VALID TESTING ==========
Total Tests : 10
Correct     : 10
Incorrect   : 0

========== INVALID TESTING ==========
Total Tests : 10
Correct     : 10
Incorrect   : 0

========== AI-GUIDED TESTING ==========
Compiler errors collected : 10
Sending error patterns to AI...
Targeted tests generated  : 5

AI-generated test results:
AI Test #1 -> SYNTAX_ERROR
AI Test #2 -> SYNTAX_ERROR
AI Test #3 -> SYNTAX_ERROR
AI Test #4 -> SYNTAX_ERROR
AI Test #5 -> SYNTAX_ERROR
```

## Project Structure

```text
CompilerGuard/
│
├── compiler/
│   ├── __init__.py
│   ├── lexer.py
│   ├── parser.py
│   ├── ast.py
│   ├── semantic.py
│   └── compiler.py
│
├── generator/
│   ├── generator.py
│   └── mutations.py
│
├── ai/
│   └── ai_generator.py
│
├── tests/
│   └── test_runner.py
│
└── README.md
```

## Technologies Used

- Python
- Compiler Design Concepts
- Context-Free Grammars
- Lexical Analysis
- Syntax Analysis
- Semantic Analysis
- Automated Testing
- AI / LLM API
- Git
- GitHub

## Future Work

The current implementation is the initial prototype. Planned extensions include:

- Feedback-driven AI test generation
- Test case minimization
- Semantic error fuzzing
- Larger CG-Lang grammar
- Test coverage analysis
- Compiler failure classification
- Web-based testing dashboard

## Team Contributions

### Compiler Development

- Language grammar
- Lexer
- Parser
- AST
- Semantic analysis
- Structured compiler error handling

### Testing and AI

- Grammar-based test generation
- Invalid test mutation
- Automated test runner
- Compiler result collection
- AI-guided targeted test generation
- Integration of AI-generated tests with the compiler

## Project Goal

CompilerGuard aims to demonstrate how AI can be integrated into compiler testing to automatically explore syntax and semantic edge cases and improve the effectiveness of compiler testing.
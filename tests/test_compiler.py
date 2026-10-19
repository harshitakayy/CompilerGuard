"""Unit tests: python -m unittest discover -s tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from compiler import compile_source, FAULTS
from fuzzer.engine import run_campaign
from fuzzer import reference


class CompilerBasics(unittest.TestCase):
    def run_ok(self, src, expected):
        r = compile_source(src)
        self.assertEqual(r["status"], "PASS", r)
        self.assertEqual(r["output"], expected)

    def test_arithmetic_and_precedence(self):
        self.run_ok("print 1 + 2 * 3;", ["7"])
        self.run_ok("print 10 - 3 - 2;", ["5"])
        self.run_ok("print (1 + 2) * 3;", ["9"])
        self.run_ok("print 7 % 4; print 7 / 2;", ["3", "3.5"])
        self.run_ok("print 5 - -3;", ["8"])

    def test_control_flow(self):
        self.run_ok("x = 0; while (x < 3) { x = x + 1; } print x;", ["3"])
        self.run_ok("x = 5; if (x > 3) { print 1; } else { print 2; }", ["1"])

    def test_error_classes(self):
        cases = {"x = @;": "LEXICAL_ERROR", "x = (1;": "SYNTAX_ERROR", "print y;": "SEMANTIC_ERROR",
                 "x = 1 / 0;": "SEMANTIC_ERROR", "y = 0; print 1 / y;": "RUNTIME_ERROR",
                 "x = " + "(" * 300 + "1" + ")" * 300 + ";": "LIMIT_ERROR"}
        for src, et in cases.items():
            self.assertEqual(compile_source(src)["error_type"], et, src[:30])

    def test_error_positions(self):
        r = compile_source("x = 1;\ny = (2;")
        self.assertEqual((r["line"], r["col"]), (2, 7))

    def test_never_raises(self):
        for src in ["", "\x00", "\u00e9", "}" * 50, "(" * 5000, "9" * 9000]:
            self.assertNotEqual(compile_source(src)["status"], "CRASH", src[:20])


class FuzzerFindsPlantedBugs(unittest.TestCase):
    def test_clean_compiler_has_no_bugs(self):
        self.assertEqual(run_campaign(20, 100, seed=3)["summary"]["bug_count"], 0)

    def test_every_planted_fault_is_detected(self):
        for fault in FAULTS:
            c = run_campaign(30, 150, seed=1, faults=(fault,))
            self.assertGreater(c["summary"]["bug_count"], 0, "fault not detected: " + fault)

    def test_reference_agrees_with_compiler(self):
        for src in ["print 10 - 3 - 2;", "x = 2; while (x < 5) { x = x * 2; } print x;"]:
            self.assertEqual(reference.run(src)["output"], compile_source(src)["output"])


if __name__ == "__main__":
    unittest.main()

"""Line-level path coverage of a compiler under test (sys.settrace).

Available on CPython. Coverage is measured over executable lines of function
bodies in the instrumented files only.
"""

import dis
import inspect
import sys

_EXEC_CACHE = {}


def executable_lines(path):
    if path in _EXEC_CACHE:
        return _EXEC_CACHE[path]
    with open(path, encoding="utf-8") as handle:
        code = compile(handle.read(), path, "exec")
    lines, stack = set(), [code]
    while stack:
        co = stack.pop()
        if co.co_flags & inspect.CO_OPTIMIZED:
            lines.update((path, ln) for _, ln in dis.findlinestarts(co) if ln)
        stack += [c for c in co.co_consts if inspect.iscode(c)]
    _EXEC_CACHE[path] = lines
    return lines


def trace_lines(func, files):
    """Run ``func()``; return ``(result, set of (file, line))`` executed."""
    files, seen = set(files), set()

    def local(frame, event, arg):
        if event == "line":
            seen.add((frame.f_code.co_filename, frame.f_lineno))
        return local

    def global_(frame, event, arg):
        return local if frame.f_code.co_filename in files else None

    old = sys.gettrace()
    sys.settrace(global_)
    try:
        result = func()
    finally:
        sys.settrace(old)
    return result, seen

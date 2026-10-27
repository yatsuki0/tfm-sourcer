"""Optional stage: undo the obfuscator's constant hiding so the source reads like normal code.

The obfuscator moves every literal into static fields of "holder" classes, computes numbers
with fake arithmetic, and wraps uses in identity functions:

    _o631668322._o1641368864887(_o736138528867._o3743336367547)    // is just 1
    public static var _o6224771648617:int = 6875 + -4403;          // is just 2472

This stage repeats three safe rewrites until nothing changes:

1. inline   static fields with a literal value that are never written to
2. unwrap   identity functions (`f(x:T):T { return x; }`) around a literal of type T
3. fold     literal arithmetic and parentheses where no other operator touches them

The holder fields themselves are left in place.
"""
import ast
import math
import operator
import os
import re

from .files import iter_scripts, read, write

NUMBER = r'(?:\d+(?:\.\d+)?(?:e[-+]?\d+)?)'
STRING = r'"(?:[^"\\\r\n]|\\.)*"'
DECL_RE = re.compile(r'^[ \t]*public static (?:var|const) (_o\w+):(int|uint|Number|String|Boolean) = (.+);\r?$', re.M)
WRITE_RES = [re.compile(r'\b(_o\w+)\s*(?:[-+*/|&^%]|<<|>>>?)?=(?!=)'),
             re.compile(r'\b(_o\w+)\s*(?:\+\+|--)'),
             re.compile(r'(?:\+\+|--)\s*(?:\w+\.)*(_o\w+)')]
# A field reference, optionally qualified by its class. `name:` (no space) is a declaration.
REF_RE = re.compile(r'(?<![\w.$])(?:(_o\w+)\.)?(_o\w+)\b(?!:)')
STATIC_DECL_LINE = re.compile(r'[ \t]*(?:public|private|protected|internal) static (?:var|const) ')
IDENTITY_RE = re.compile(r'public static function (\w+)\(param1:(\w+)\) : \2\s*\{\s*return param1;\s*\}')

# Operands that are already plain literals; negative numbers are kept in parentheses.
LITERAL_ARG = {
    'int': r'-?\d+|\(-\d+\)',
    'uint': r'\d+',
    'Number': r'-?' + NUMBER + r'|\(-' + NUMBER + r'\)',
    'String': STRING,
    'Boolean': r'true|false',
}

BINARY = re.compile(r'(?P<pre>[(,\[=?:]|\breturn)(?P<ws>\s*)'
                    r'(?P<a>-?' + NUMBER + r') (?P<op>[-+*/]) (?P<b>-?' + NUMBER + r')'
                    r'(?=\s*[),;\]:?])')
# Parentheses around a plain non-negative number, unless they're a call, `new Vector.<T>(5)`
# or `(5).method()`.
PAREN = re.compile(r'(?<![\w)\]$>])\((?P<n>' + NUMBER + r')\)(?!\s*\.)')
OPS = {'+': operator.add, '-': operator.sub, '*': operator.mul, '/': operator.truediv}
AST_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def run(cfg, max_rounds=10):
    files = {path: read(path) for path in iter_scripts(cfg.src)}
    constants = find_constants(files)
    wrappers = find_identity_wrappers(files)
    print('  %d constants to inline, %d identity wrappers' % (len(constants), len(wrappers)))

    totals = {'inline': 0, 'unwrap': 0, 'fold': 0}
    for path, text in files.items():
        own_class = os.path.basename(path)[:-3]
        original = text
        for _ in range(max_rounds):
            before = text
            text, n = inline(text, constants, own_class)
            totals['inline'] += n
            text, n = unwrap(text, wrappers)
            totals['unwrap'] += n
            text, n = fold(text)
            totals['fold'] += n
            if text == before:
                break
        if text != original:
            write(path, text)
    for name, count in totals.items():
        print('  %-8s %d' % (name, count))


def find_constants(files):
    """{field name: (declaring class, literal)} for literal fields that are never written."""
    written = set()
    for text in files.values():
        for regex in WRITE_RES:
            written.update(regex.findall(text))
    constants, seen = {}, set()
    for path, text in files.items():
        cls = os.path.basename(path)[:-3]
        for name, type_, init in DECL_RE.findall(text):
            if name in seen:            # declared twice: ambiguous, leave alone
                constants.pop(name, None)
                continue
            seen.add(name)
            value = literal_value(type_, init.strip())
            if value is not None and name not in written:
                constants[name] = (cls, value)
    return constants


def literal_value(type_, init):
    """AS3 source for the value of a literal initializer, or None if it isn't one."""
    if type_ == 'String':
        return init if re.fullmatch(STRING, init) else None
    if type_ == 'Boolean':
        if init in ('true', 'false'):
            return init
        m = re.fullmatch(r'Boolean\((' + STRING + r')\)', init)
        return ('true' if len(m.group(1)) > 2 else 'false') if m else None
    value = evaluate(init)
    if value is None:
        return None
    if type_ == 'int':
        value = to_int32(value)
    elif type_ == 'uint':
        value = to_int32(value) & 0xFFFFFFFF
    return format_number(value)


def evaluate(expression):
    """Value of an expression made only of number literals, + - * / and parentheses."""
    if not re.fullmatch(r'[\d\s.e+\-*/()]+', expression):
        return None
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError:
        return None

    def ev(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp) and type(node.op) in AST_OPS:
            return AST_OPS[type(node.op)](ev(node.left), ev(node.right))
        raise ValueError
    try:
        value = ev(tree.body)
    except (ValueError, ZeroDivisionError):
        return None
    return value if math.isfinite(value) else None


def to_int32(value):
    """AS3 int() conversion: truncate toward zero, wrap to 32 bits."""
    n = int(value) & 0xFFFFFFFF
    return n - (1 << 32) if n & 0x80000000 else n


def format_number(value):
    if float(value).is_integer() and abs(value) < 2 ** 53:
        text = str(int(value))
    else:
        text = repr(float(value))
    return '(%s)' % text if text.startswith('-') else text


def inline(text, constants, own_class):
    count = 0

    def replace(m):
        nonlocal count
        cls, name = m.group(1), m.group(2)
        entry = constants.get(name)
        if not entry or (cls or own_class) != entry[0]:
            return m.group(0)
        # In its own class's static initializers a field may be read before it's assigned
        # (then it's still 0 or null), so those uses keep the reference.
        if own_class == entry[0] and STATIC_DECL_LINE.match(text, text.rfind('\n', 0, m.start()) + 1):
            return m.group(0)
        count += 1
        value = entry[1]
        # `5.toString()` doesn't parse; a number followed by `.` keeps parentheses.
        if value[0].isdigit() and text.startswith('.', m.end()):
            return '(%s)' % value
        return value
    return REF_RE.sub(replace, text), count


def find_identity_wrappers(files):
    """{(class, function): type} for `static function f(param1:T):T { return param1; }`."""
    wrappers = {}
    for path, text in files.items():
        cls = os.path.basename(path)[:-3]
        for name, type_ in IDENTITY_RE.findall(text):
            if type_ in LITERAL_ARG:
                wrappers[(cls, name)] = type_
    return wrappers


def unwrap(text, wrappers):
    count = 0
    for (cls, name), type_ in wrappers.items():
        call = cls + '.' + name + '('
        if call not in text:
            continue
        regex = re.compile(r'(?<![\w.$])' + re.escape(cls) + r'\.' + re.escape(name) +
                           r'\((' + LITERAL_ARG[type_] + r')\)')
        # A bare negative keeps parentheses, so `-f(-5)` can't become the decrement `--5`.
        text, n = regex.subn(lambda m: '(%s)' % m.group(1) if m.group(1).startswith('-') else m.group(1), text)
        count += n
    return text, count


def fold(text):
    count = 0

    def binary(m):
        nonlocal count
        a, b = float(m['a']), float(m['b'])
        if m['op'] == '/' and b == 0:
            return m.group(0)
        count += 1
        return m['pre'] + m['ws'] + format_number(OPS[m['op']](a, b))

    def paren(m):
        nonlocal count
        count += 1
        return m['n']

    while True:
        new = BINARY.sub(binary, text)
        new = PAREN.sub(paren, new)
        if new == text:
            return text, count
        text = new

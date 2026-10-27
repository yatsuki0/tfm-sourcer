"""Stage 3: repair what FFDec decompiles wrongly, so the source compiles and behaves like the original.

Each fixer is a pattern, not a hard-coded file or name, so it keeps working when a new game
version changes the obfuscated names. Every fixer reports how often it applied.
"""
import os
import re

from . import project
from .files import iter_scripts, read, write

MEMBER = r'(?:public|private|protected|internal)'


def newline_of(text):
    return '\r\n' if '\r\n' in text else '\n'


# --- Source fixers ----------------------------------------------------------------------------

def const_assigned_in_constructor(text, ctx):
    """FFDec moves field initializers into the constructor, so `const x:T;` is then assigned
    there, which the compiler rejects. Instance constants without an initializer become vars."""
    return re.subn(r'^([ \t]*' + MEMBER + r' )const( \w+:[^=;\r\n]+;)', r'\1var\2', text, flags=re.M)


def this_in_field_initializer(text, ctx):
    """`public var a:int = this.b;` -- Flex 4.10 resolves `this` in a field initializer as the
    class, not the instance. Dropping `this.` refers to the same instance field."""
    count = 0

    def fix(m):
        nonlocal count
        rest, n = re.subn(r'\bthis\.', '', m.group(2))
        count += n
        return m.group(1) + rest

    text = re.sub(r'^([ \t]*' + MEMBER + r' (?:var|const) \w+:[^=\r\n]+=)(.*)$', fix, text, flags=re.M)
    return text, count


def null_property_access(text, ctx):
    """Obfuscator junk such as `null.x = 1`. Casting through Object compiles and still throws
    at runtime exactly like the original bytecode."""
    return re.subn(r'(?<![\w.$"])null\.(?=[A-Za-z_])', '(null as Object).', text)


ACTIVATION_RE = re.compile(
    r'^(?P<indent>[ \t]*)_opush\(_onewactivation\(\)\);\r?\n'
    r'[ \t]*var _temp_\d+:\* = (?P<value>new <(?P<type>[\w.]+)>\[.*\]);\r?\n'
    r'[ \t]*_opop\(\)\._oslot\[\d+\] = (?P=value);', re.M)


def activation_slot(text, ctx):
    """FFDec leaves raw bytecode (`_opush(_onewactivation())`, `_opop()._oslot[N] = v`) when it
    can't name a local captured by a closure. The slot is the function's only local of the
    value's type, so the three lines become a plain assignment to that local."""
    def fix(m):
        function_start = text.rfind(' function ', 0, m.start())
        locals_ = set(re.findall(r'var (\w+):Vector\.<' + re.escape(m['type']) + r'>',
                                 text[function_start:m.start()]))
        if len(locals_) != 1:
            raise SystemExit('activation_slot: cannot tell which local gets %s (candidates: %s)'
                             % (m['value'][:60], sorted(locals_)))
        return '%s%s = %s;' % (m['indent'], locals_.pop(), m['value'])

    return ACTIVATION_RE.subn(fix, text)


VARINT_RE = re.compile(
    r'(?P<head>if\(\(\w+ & 0x80\) == 128 && [^\r\n]+\)\r?\n'
    r'[ \t]*\{\r?\n[ \t]*continue;\r?\n[ \t]*\}\r?\n)'
    r'(?P<indent>[ \t]*)(?P<flag>this\.\w+) = (?P<value>[^;\r\n]+);\r?\n'
    r'(?P<loop_indent>[ \t]*)\}\r?\n'
    r'[ \t]*return;')


def varint_missing_break(text, ctx):
    """The socket reader decodes each packet's length as a varint in a `while` loop. FFDec drops
    the `break` after the last length byte, so the loop reads the packet body as more length
    bytes and every packet fails with Error #2030 (hidden by a catch): the game gets no data."""
    nl = newline_of(text)

    def fix(m):
        i, li = m['indent'], m['loop_indent']
        return (m['head'] +
                i + m['flag'] + ' = ' + m['value'] + ';' + nl +
                i + '// The decompiler dropped this break: without it the packet body is read as more length bytes.' + nl +
                i + 'break;' + nl +
                li + '}' + nl +
                li + 'if(!' + m['flag'] + ')' + nl +
                li + '{' + nl +
                i + 'return;' + nl +
                li + '}')

    return VARINT_RE.subn(fix, text)


SWF_LENGTH_RE = re.compile(r'^(?P<indent>[ \t]*)this\.(?P<field>\w+) = stage\.loaderInfo\.bytes\.length;', re.M)


def original_swf_length(text, ctx):
    """The handshake reports the client's own SWF byte length. Report the original file's
    length, as the original client does, instead of the rebuilt one's."""
    m = SWF_LENGTH_RE.search(text)
    if not m:
        return text, 0
    nl = newline_of(text)
    decl = re.search(r'^([ \t]*)public var ' + m['field'] + r':int;', text, re.M)
    if not decl:
        raise SystemExit('original_swf_length: declaration of %s not found' % m['field'])
    member_indent = decl.group(1)
    constant = (member_indent + '// Byte length of the original Transformice.swf. The handshake reports the client\'s SWF length and the' + nl +
                member_indent + '// server checks it, so a rebuilt SWF must report the original value instead of its own.' + nl +
                member_indent + 'public static const ORIGINAL_SWF_LENGTH:int = %d;' % ctx['original_size'] + nl +
                nl)
    text = text[:m.start()] + m['indent'] + 'this.' + m['field'] + ' = ORIGINAL_SWF_LENGTH;' + text[m.end():]
    return text[:decl.start()] + constant + text[decl.start():], 1


def junk_literal_statements(text, ctx):
    """Newer FFDec versions keep obfuscator leftovers such as a lone `true;` statement. They do
    nothing, so the lines are removed."""
    junk = r'[ \t]*(?:true|false);[ \t]*\r?\n'
    count = len(re.findall('^' + junk, text, flags=re.M))
    # Between two blank member separators, drop one of them too so no double blank line is left.
    text = re.sub(r'^([ \t]*\r?\n)(?:' + junk + r')+[ \t]*\r?\n', r'\1', text, flags=re.M)
    return re.sub('^' + junk, '', text, flags=re.M), count


SOURCE_FIXERS = [const_assigned_in_constructor, this_in_field_initializer, null_property_access,
                 activation_slot, varint_missing_break, original_swf_length, junk_literal_statements]


# --- Fixers driven by compiler errors -----------------------------------------------------------

def missing_return(cfg, error):
    """`Function does not return a value` after a try/catch whose branches both return: Flex 4.10
    can't see that the end is unreachable. Add an unreachable return of the right default."""
    lines = read(error.file).splitlines(keepends=True)
    index = error.line - 1
    close = lines[index]
    indent = close[:len(close) - len(close.lstrip())]
    signature = next(l for l in reversed(lines[:index]) if ' function ' in l)
    return_type = signature.rsplit(':', 1)[-1].strip()
    default = {'int': '0', 'uint': '0', 'Number': 'NaN', 'Boolean': 'false'}.get(return_type, 'null')
    nl = newline_of(close)
    lines.insert(index, indent + '   return %s;%s' % (default, nl))
    write(error.file, ''.join(lines))


ERROR_FIXERS = {'Function does not return a value.': missing_return}


def run(cfg, max_passes=5):
    target = project.Target(cfg.swf)
    ctx = {'original_size': target.original_size}
    totals = dict.fromkeys((f.__name__ for f in SOURCE_FIXERS), 0)
    for path in iter_scripts(cfg.src):
        text = original = read(path)
        for fixer in SOURCE_FIXERS:
            text, count = fixer(text, ctx)
            totals[fixer.__name__] += count
        if text != original:
            write(path, text)
    for name, count in totals.items():
        print('  %-32s %d' % (name, count))

    scratch = os.path.join(cfg.work, 'fixcheck.swf')
    for _ in range(max_passes):
        ok, errors = project.build(cfg, output=scratch, echo=not cfg.quiet)
        if ok:
            print('Source compiles.')
            return
        unknown = [e for e in errors if e.message not in ERROR_FIXERS]
        if unknown:
            for e in unknown:
                print('%s(%d): %s' % (os.path.relpath(e.file, cfg.root), e.line, e.message))
            raise SystemExit('%d compile error(s) need a manual fix (see docs/decompiler-fixes.md).' % len(unknown))
        # Fix bottom-up within each file so earlier line numbers stay valid.
        for e in sorted(errors, key=lambda e: (e.file, -e.line)):
            ERROR_FIXERS[e.message](cfg, e)
            print('  %-32s %s(%d)' % (ERROR_FIXERS[e.message].__name__, os.path.basename(e.file), e.line))
    raise SystemExit('Source still does not compile after %d passes.' % max_passes)

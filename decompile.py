"""Turn Transformice.swf into a compilable ActionScript 3 project (transformice/ by default).

    python decompile.py setup                 install and configure the Flex 4.10 compiler
    python decompile.py all [--readable]      export, deobfuscate, fix (and readable), then build
    python decompile.py info [FILE]           show what's inside a SWF

Single stages: export, deobfuscate, fix, readable (optional). Paths are in tfm-sourcer.config.json;
--swf and --project override them for one run, e.g.:

    python decompile.py all --swf D:/versions/Transformice_1.857.swf --project D:/tfm-1.857

FFDec's and the compiler's output is shown in full; --quiet shows a progress line and summaries instead,
--no-warnings leaves out the compiler's warnings.

Once the project's src exists, build it with: python build.py [--project PATH]
"""
import argparse
import os
import sys

from decompiler import config, deobfuscate, export, fixes, project, readable, setup_sdk
from decompiler.names import from_raw
from decompiler.swf import Swf


def cmd_setup(cfg, args):
    setup_sdk.run(cfg)


def cmd_export(cfg, args):
    export.run(cfg, force=args.force)


def cmd_deobfuscate(cfg, args):
    deobfuscate.run(cfg)


def cmd_fix(cfg, args):
    print('Applying decompiler fixes:')
    fixes.run(cfg)


def cmd_readable(cfg, args):
    print('Inlining obfuscated constants:')
    readable.run(cfg)


# What to run after each single stage, printed when it's run on its own.
NEXT = {
    cmd_export: 'python decompile.py deobfuscate',
    cmd_deobfuscate: 'python decompile.py fix',
    cmd_fix: 'python build.py (or first the optional: python decompile.py readable)',
    cmd_readable: 'python build.py',
}


def cmd_all(cfg, args):
    steps = [cmd_export, cmd_deobfuscate, cmd_fix] + ([cmd_readable] if args.readable else [])
    for number, step in enumerate(steps, 1):
        print('\n[%d/%d] %s' % (number, len(steps) + 1, step.__name__[4:]))
        step(cfg, args)
    print('\n[%d/%d] build' % (len(steps) + 1, len(steps) + 1))
    ok, _ = project.build(cfg)
    if not ok:
        raise SystemExit(1)
    print('\nDone. The source is in %s' % cfg.src)
    print('After changing it, rebuild with: python build.py')


def cmd_info(cfg, args):
    path = args.file or cfg.swf
    if not os.path.isfile(path):
        raise SystemExit('SWF not found: %s' % path)
    swf = Swf(path)
    print('%s, SWF version %d, %d bytes (%d unpacked)' % (swf.signature, swf.version, swf.file_size, len(swf.body) + 8))
    print('Stage %dx%d, %d fps, background %s' % (swf.width, swf.height, swf.frame_rate, swf.background()))
    info = swf.product_info()
    if info:
        print('Built by %s %s (build %d) on %s' % (info['product'], info['version'], info['build'],
                                                  info['compiled'].strftime('%Y-%m-%d %H:%M UTC')))
    for name, version in swf.abc_versions():
        print('Bytecode "%s": ABC %s' % (name, version))
    classes = swf.symbol_classes()
    if 0 in classes:
        print('Main class: %s' % from_raw(classes[0]))
    print('\nTags:')
    for code, name, count, size in swf.tag_summary():
        print('  %3d %-28s x%-3d %10d bytes' % (code, name, count, size))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    paths = argparse.ArgumentParser(add_help=False)
    paths.add_argument('--swf', metavar='PATH', help='input SWF (default: "swf" in the config)')
    paths.add_argument('--project', metavar='PATH', help='project folder (default: "project" in the config)')
    paths.add_argument('--quiet', action='store_true',
                       help="summarize FFDec's and the compiler's output instead of showing all of it")
    paths.add_argument('--no-warnings', action='store_true', help="don't show compiler warnings")

    sub = parser.add_subparsers(dest='command', required=True)

    def command(name, func, help_text):
        p = sub.add_parser(name, parents=[paths], help=help_text)
        p.set_defaults(func=func)
        return p

    command('setup', cmd_setup, 'install and configure the Flex 4.10 compiler')
    p = command('all', cmd_all, 'run every stage, then build')
    p.add_argument('--force', action='store_true', help="replace the project's existing src/")
    p.add_argument('--readable', action='store_true', help='also run the optional readable stage')
    p = command('export', cmd_export, "export scripts and assets with FFDec into the project's src/")
    p.add_argument('--force', action='store_true', help="replace the project's existing src/")
    command('deobfuscate', cmd_deobfuscate, 'rename obfuscated identifiers')
    command('fix', cmd_fix, 'repair decompiler errors')
    command('readable', cmd_readable, 'optional: inline obfuscated constants')
    p = command('info', cmd_info, "show what's inside a SWF")
    p.add_argument('file', nargs='?', help='SWF file (default: the input SWF)')

    args = parser.parse_args()
    # Tool output is passed through as-is; a character the console's code page can't show
    # (FFDec prints some U+FFFD) becomes "?" instead of stopping the run.
    sys.stdout.reconfigure(errors='replace')
    cfg = config.load(swf=args.swf, project=args.project)
    cfg.quiet = args.quiet
    cfg.no_warnings = args.no_warnings
    args.func(cfg, args)
    if args.func in NEXT:
        print('\nNext: %s' % NEXT[args.func])


if __name__ == '__main__':
    main()

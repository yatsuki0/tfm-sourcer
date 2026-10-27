"""The project's build settings, taken from the original SWF, and building it.

The decompiler writes the project's asconfig.json once; from then on build.py (and VS Code)
build it from that file alone.
"""
import collections
import json
import os
import re
import subprocess
import sys

from . import names
from .swf import Swf

ERROR_RE = re.compile(r'^(?P<file>.+?\.as)\((?P<line>\d+)\): col: (?P<col>\d+) Error: (?P<message>.*)$', re.M)
CompileError = collections.namedtuple('CompileError', 'file line col message')


class Target:
    """Main class and stage settings, read from the original SWF."""

    def __init__(self, swf_path):
        swf = Swf(swf_path)
        self.main_class = names.from_raw(swf.symbol_classes()[0])
        self.frame_rate = swf.frame_rate
        self.background = swf.background() or '#ffffff'
        self.swf_version = swf.version
        self.width = swf.width
        self.height = swf.height
        self.original_size = swf.file_size


def write_asconfig(cfg):
    """asconfig.json in the project folder, for build.py and the VS Code ActionScript & MXML
    extension. Paths are relative to the project folder, which is what you open in VS Code."""
    target = Target(cfg.swf)

    def relative(path):
        return os.path.relpath(path, cfg.project).replace(os.sep, '/')

    asconfig = {
        'config': 'flex',
        'compilerOptions': {
            'source-path': [relative(cfg.src)],
            'output': relative(cfg.output),
            'default-background-color': target.background,
            'default-frame-rate': target.frame_rate,
            'default-size': {'width': target.width, 'height': target.height},
            'target-player': '32.0',
            'swf-version': target.swf_version,
        },
        'mainClass': target.main_class,
    }
    with open(os.path.join(cfg.project, 'asconfig.json'), 'w', encoding='utf-8') as fh:
        json.dump(asconfig, fh, indent='\t')
        fh.write('\n')


def build(cfg, output=None, debug=False, echo=True):
    """Runs build.py. Returns (ok, [CompileError]).

    With echo, prints its output: all of it, or with cfg.quiet only the "Built ..." line of a successful build."""
    args = [sys.executable, os.path.join(cfg.root, 'build.py'), '--project', cfg.project]
    if output:
        args += ['--output', output]
    if debug:
        args.append('--debug')
    if cfg.no_warnings:
        args.append('--no-warnings')
    # One stream, so warnings and errors (stderr) stay in order with the rest (stdout).
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace')
    log = result.stdout
    errors = [CompileError(m['file'], int(m['line']), int(m['col']), m['message'].strip())
              for m in ERROR_RE.finditer(log)]
    errors = list(dict.fromkeys(errors))  # mxmlc reports some errors twice
    if echo:
        built = [line for line in log.splitlines() if line.startswith('Built ')]
        print(built[-1] if cfg.quiet and result.returncode == 0 and built else log.rstrip())
    return result.returncode == 0, errors

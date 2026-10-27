"""Builds the game: <project>/src -> <project>/bin/Transformice.swf, with the Flex 4.10 compiler.

    python build.py                   release build
    python build.py --debug           Transformice-debug.swf, with line numbers for the debug player
    python build.py --no-warnings     don't show compiler warnings
    python build.py --project PATH    build the project in PATH instead of the one set in the config

Build settings come from the project's asconfig.json, which the VS Code ActionScript & MXML
extension reads too, so both builds match. Tool paths come from tfm-sourcer.config.json.
Doesn't need the decompiler or the original SWF.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(ROOT, 'tfm-sourcer.config.json')


def load_json(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def tool_path(config, key):
    value = config.get(key)
    return os.path.normpath(os.path.join(ROOT, os.path.expandvars(value))) if value else None


def find_mxmlc(config, explicit=None):
    for sdk in (explicit, tool_path(config, 'flex_sdk'), os.environ.get('FLEX_HOME')):
        if sdk:
            mxmlc = os.path.join(sdk, 'bin', 'mxmlc.bat' if os.name == 'nt' else 'mxmlc')
            if os.path.isfile(mxmlc):
                return mxmlc
    sys.exit('Flex SDK not found. Set "flex_sdk" in tfm-sourcer.config.json and run: python decompile.py setup')


def mxmlc_args(project, asconfig, output=None, debug=False, warnings=True):
    """Paths in asconfig.json are relative to the project folder."""
    options = asconfig['compilerOptions']
    source_paths = [os.path.join(project, p) for p in options['source-path']]
    candidates = [os.path.join(root, *asconfig['mainClass'].split('.')) + '.as' for root in source_paths]
    main_file = next((path for path in candidates if os.path.isfile(path)), None)
    if not main_file:
        sys.exit('Main class %s not found in %s' % (asconfig['mainClass'], source_paths))

    output = os.path.normpath(output or os.path.join(project, options['output']))
    if debug and not output.endswith('-debug.swf'):
        output = output[:-len('.swf')] + '-debug.swf'
    size = options['default-size']
    args = [main_file,
            '-source-path=' + ','.join(source_paths),
            '-output=' + output,
            '-default-background-color=0x' + options['default-background-color'].lstrip('#'),
            '-default-frame-rate=%d' % options['default-frame-rate'],
            '-default-size=%d,%d' % (size['width'], size['height']),
            '-target-player=' + options['target-player'],
            '-swf-version=%d' % options['swf-version']]
    if debug:
        args.append('-debug=true')
    if not warnings:
        args.append('-warnings=false')
    return args, output


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--debug', action='store_true', help='debug build with line numbers')
    parser.add_argument('--no-warnings', action='store_true', help="don't show compiler warnings")
    parser.add_argument('--output', help='write the SWF here instead of the asconfig.json output')
    parser.add_argument('--project', metavar='PATH', help='project folder (default: "project" in tfm-sourcer.config.json)')
    parser.add_argument('--sdk', metavar='PATH', help='Flex SDK folder (default: "flex_sdk" in tfm-sourcer.config.json)')
    args = parser.parse_args()

    example = os.path.join(ROOT, 'tfm-sourcer.config.example.json')
    if not os.path.isfile(CONFIG_FILE) and os.path.isfile(example):
        shutil.copy2(example, CONFIG_FILE)
        print('Created tfm-sourcer.config.json from the example. Check the tool paths in it if a step fails.\n')
    config = load_json(CONFIG_FILE) if os.path.isfile(CONFIG_FILE) else {}
    mxmlc = find_mxmlc(config, args.sdk)
    project = os.path.abspath(args.project) if args.project else \
        tool_path(config, 'project') or os.path.join(ROOT, 'transformice')
    asconfig_path = os.path.join(project, 'asconfig.json')
    if not os.path.isfile(asconfig_path):
        sys.exit('%s not found. Is %s a project folder? (python decompile.py all creates one)' % (asconfig_path, project))
    mxmlc_options, output = mxmlc_args(project, load_json(asconfig_path), args.output, args.debug, not args.no_warnings)

    env = dict(os.environ)
    java_home = tool_path(config, 'java_home')
    if java_home:
        env['JAVA_HOME'] = java_home
        env['PATH'] = os.path.join(java_home, 'bin') + os.pathsep + env.get('PATH', '')

    os.makedirs(os.path.dirname(output), exist_ok=True)
    result = subprocess.run([mxmlc] + mxmlc_options, env=env)
    if result.returncode == 0:
        print('Built %s (%d bytes)' % (output, os.path.getsize(output)))
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()

"""Builds the game: <project>/src -> <project>/bin/Transformice.swf, with the Flex 4.10 compiler.

    python build.py                   release build
    python build.py --debug           Transformice-debug.swf, with line numbers for the debug player
    python build.py --no-warnings     don't show compiler warnings
    python build.py --pack            also write bin/packed/Transformice.swf, packed like the original
    python build.py --project PATH    build the project in PATH instead of the one set in the config

Build settings come from the project's asconfig.json, which the VS Code ActionScript & MXML
extension reads too, so both builds match. Tool paths come from tfm-sourcer.config.json.
Doesn't need the decompiler or the original SWF.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib

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
    parser.add_argument('--pack', action='store_true',
                        help='also write bin/packed/<name>.swf: the original loader with the rebuilt game inside '
                             '(only for a project decompiled from a packed SWF)')
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
    loader_dir = os.path.join(project, 'loader')
    if args.pack and not os.path.isfile(os.path.join(loader_dir, 'chunks.json')):
        sys.exit('--pack: %s has no loader/chunks.json. Only a project decompiled from a packed SWF '
                 '(the client as downloaded) can be packed.' % project)

    env = dict(os.environ)
    java_home = tool_path(config, 'java_home')
    if java_home:
        env['JAVA_HOME'] = java_home
        env['PATH'] = os.path.join(java_home, 'bin') + os.pathsep + env.get('PATH', '')

    os.makedirs(os.path.dirname(output), exist_ok=True)
    result = subprocess.run([mxmlc] + mxmlc_options, env=env)
    if result.returncode == 0:
        print('Built %s (%d bytes)' % (output, os.path.getsize(output)))
        if args.pack:
            packed = os.path.join(os.path.dirname(output), 'packed', os.path.basename(output))
            pack(loader_dir, output, packed)
            print('Packed %s (%d bytes)' % (packed, os.path.getsize(packed)))
    sys.exit(result.returncode)


def pack(loader_dir, game_path, output):
    """Puts the rebuilt game into the original loader, the way the original was packed.

    The loader joins its DefineBinaryData chunks in the order saved in chunks.json and runs the
    result. The new game is cut into as many pieces, which replace the chunks in that order.
    The loader's code isn't touched."""
    order = load_json(os.path.join(loader_dir, 'chunks.json'))['order']
    with open(game_path, 'rb') as fh:
        game = fh.read()
    size = len(game) // len(order)
    pieces = [game[i * size:(i + 1) * size] for i in range(len(order) - 1)] + [game[(len(order) - 1) * size:]]
    with open(os.path.join(loader_dir, 'loader.swf'), 'rb') as fh:
        loader = fh.read()
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, 'wb') as fh:
        fh.write(replace_binary_data(loader, dict(zip(order, pieces))))


def replace_binary_data(swf, replacements):
    """The SWF with the data of the DefineBinaryData tags in replacements ({id: bytes}) replaced."""
    signature, version = swf[:3], swf[3]
    if signature == b'CWS':
        body = zlib.decompress(swf[8:])
    elif signature == b'FWS':
        body = swf[8:]
    else:
        sys.exit('--pack: the loader is %s; only FWS and CWS loaders are supported' % signature.decode('ascii', 'replace'))
    nbits = body[0] >> 3
    pos = (5 + 4 * nbits + 7) // 8 + 4          # stage RECT, frame rate, frame count
    parts = [body[:pos]]
    while pos < len(body):
        code_len = struct.unpack_from('<H', body, pos)[0]
        code, length = code_len >> 6, code_len & 0x3F
        pos += 2
        if length == 0x3F:
            length = struct.unpack_from('<I', body, pos)[0]
            pos += 4
        data = body[pos:pos + length]
        pos += length
        if code == 87:
            chunk_id = struct.unpack_from('<H', data, 0)[0]
            if chunk_id in replacements:
                data = data[:6] + replacements.pop(chunk_id)
        if code == 87 or len(data) >= 0x3F:
            parts.append(struct.pack('<HI', code << 6 | 0x3F, len(data)) + data)
        else:
            parts.append(struct.pack('<H', code << 6 | len(data)) + data)
        if code == 0:
            break
    if replacements:
        sys.exit('--pack: the loader has no binary chunks with ids %s' % sorted(replacements))
    body = b''.join(parts)
    payload = zlib.compress(body) if signature == b'CWS' else body
    return signature + bytes([version]) + struct.pack('<I', 8 + len(body)) + payload


if __name__ == '__main__':
    main()

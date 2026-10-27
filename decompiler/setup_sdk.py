"""Installs and configures Apache Flex SDK 4.10.0 with Flash Player 32's playerglobal.swc.

Flex 4.10 is the compiler that built the original SWF (see its ProductInfo tag). It writes
ABC 46.16 bytecode, which Flash Player 32 loads. AIR SDK compilers write ABC 47.16, which
Flash Player 32 refuses: the player closes as soon as the SWF opens.
"""
import hashlib
import os
import shutil
import subprocess
import urllib.request
import zipfile

FLEX_URL = 'https://archive.apache.org/dist/flex/4.10.0/binaries/apache-flex-sdk-4.10.0-bin.zip'
FLEX_MD5 = '79047fff27eaaef8765c1f2ec3ce31b7'
# Adobe's own Flash Player 32 API library, still served from its old updater location.
PLAYERGLOBAL_URL = 'https://fpdownload.macromedia.com/get/flashplayer/updaters/32/playerglobal32_0.swc'
PLAYERGLOBAL_MD5 = '513a4f254444e43b94bb0758398ea23c'


def run(cfg):
    print('Setting up the compiler in %s\n' % cfg.flex_sdk)
    report('Apache Flex SDK 4.10.0', 'already installed' if os.path.isfile(cfg.mxmlc) else install_flex(cfg))
    report('playerglobal.swc 32.0', install_playerglobal(cfg))
    report('flex-config.xml', configure(cfg))
    report('Compiler', check_compiler(cfg))
    if cfg.ffdec and os.path.isfile(cfg.ffdec):
        report('FFDec', 'found')
    else:
        report('FFDec', 'NOT FOUND at %s: set "ffdec" in the config before decompiling' % cfg.ffdec)
    print('\nSetup complete. Next: python decompile.py all')


def report(item, status):
    print('  %-24s %s' % (item, status))


def check_compiler(cfg):
    result = subprocess.run([cfg.mxmlc, '-version'], env=cfg.env(), capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit('The compiler doesn\'t run. Is Java 8 installed (or "java_home" set in the config)?\n'
                         + (result.stdout + result.stderr).strip())
    output = (result.stdout + result.stderr).strip()
    return 'runs (%s)' % (output.splitlines()[-1] if cfg.quiet else output.replace('\n', '; '))


def install_flex(cfg):
    os.makedirs(cfg.work, exist_ok=True)
    archive = os.path.join(cfg.work, os.path.basename(FLEX_URL))
    if not os.path.isfile(archive) or md5(archive) != FLEX_MD5:
        print('Downloading %s (70 MB)...' % FLEX_URL)
        try:
            download(FLEX_URL, archive, cfg.quiet)
        except OSError as e:
            raise SystemExit('Could not download the Flex SDK (%s). Run setup again to retry.' % e)
    if md5(archive) != FLEX_MD5:
        raise SystemExit('Checksum mismatch for %s' % archive)
    print('Extracting to %s...' % cfg.flex_sdk)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(cfg.flex_sdk)
    return 'downloaded and installed'


def install_playerglobal(cfg):
    target = os.path.join(cfg.flex_sdk, 'frameworks', 'libs', 'player', '32.0', 'playerglobal.swc')
    if os.path.isfile(target):
        return 'already installed'
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if cfg.playerglobal:
        # Optional override in tfm-sourcer.config.json, e.g. the copy in a Harman AIR SDK.
        shutil.copy2(cfg.playerglobal, target)
        return 'copied from %s' % cfg.playerglobal
    print('Downloading %s...' % PLAYERGLOBAL_URL)
    try:
        download(PLAYERGLOBAL_URL, target, cfg.quiet)
    except OSError as e:
        raise SystemExit('Could not download playerglobal.swc (%s).\nSet "playerglobal" in tfm-sourcer.config.json to a '
                         'local copy; every Harman AIR SDK has one in frameworks/libs/player/32.0/.' % e)
    if md5(target) != PLAYERGLOBAL_MD5:
        os.remove(target)
        raise SystemExit('Checksum mismatch for the downloaded playerglobal.swc')
    return 'downloaded from Adobe and installed'


def configure(cfg):
    """Point flex-config.xml at the bundled playerglobal and target Flash Player 32, so the
    compiler works without the PLAYERGLOBAL_HOME environment variable."""
    path = os.path.join(cfg.flex_sdk, 'frameworks', 'flex-config.xml')
    with open(path, encoding='utf-8', newline='') as fh:
        text = fh.read()
    new = text.replace('{playerglobalHome}', 'libs/player') \
              .replace('<target-player>11.1</target-player>', '<target-player>32.0</target-player>')
    if new != text:
        if not os.path.isfile(path + '.orig'):
            shutil.copy2(path, path + '.orig')
        with open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(new)
        return 'configured for Flash Player 32'
    return 'already configured'


def download(url, path, quiet=False, timeout=60):
    """Download to `path`, showing progress. The data goes to `path + '.part'` first, so an
    interrupted download never looks complete, and a stalled connection fails after `timeout`
    seconds instead of hanging. archive.apache.org is often slow, so progress matters."""
    part = path + '.part'
    with urllib.request.urlopen(url, timeout=timeout) as response, open(part, 'wb') as fh:
        total = int(response.headers.get('Content-Length') or 0)
        done = 0
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if not quiet:
                print('\r  %s' % progress(done, total), end='', flush=True)
    if not quiet:
        print()
    if total and done != total:
        raise OSError('incomplete download: %d of %d bytes' % (done, total))
    os.replace(part, path)


def progress(done, total):
    mb = 1024 * 1024
    if not total:
        return '%.1f MB' % (done / mb)
    return '%.1f of %.1f MB (%d%%)' % (done / mb, total / mb, done * 100 // total)


def md5(path):
    digest = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()

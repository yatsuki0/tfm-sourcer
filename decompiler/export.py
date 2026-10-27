"""Stage 1: export scripts and embedded assets from the SWF with FFDec, and lay them out in the project's src/."""
import os
import re
import shutil
import subprocess
import sys
import time

from . import project
from .files import iter_scripts, read, write

# FFDec gives up on a method after 60 s by default and writes a stub that throws
# "Not decompiled due to timeout". The client's packet handler (~11,600 instructions)
# needs about 5.5 minutes, so the limits are raised well above that.
FFDEC_CONFIG = 'decompilationTimeoutSingleMethod=3600,decompilationTimeoutFile=7200,exportTimeout=14400'
STUB_MARKER = 'Not decompiled'
PROGRESS_RE = re.compile(r'^Exported script (\d+)/(\d+)')


def run(cfg, force=False):
    cfg.require('swf', 'ffdec')
    if os.path.isdir(cfg.src) and os.listdir(cfg.src) and not force:
        raise SystemExit('%s already exists. Pass --force to replace it with a fresh export.' % cfg.src)
    export = os.path.join(cfg.work, 'export')
    shutil.rmtree(export, ignore_errors=True)
    os.makedirs(export)

    print('Decompiling %s with FFDec (about 8 minutes)...' % cfg.swf)
    run_ffdec(cfg, export)

    shutil.rmtree(cfg.src, ignore_errors=True)
    shutil.copytree(os.path.join(export, 'scripts'), cfg.src)
    os.makedirs(cfg.assets, exist_ok=True)
    # The scripts reference assets as [Embed(source="/_assets/<id>_<class>.bin")], which is
    # exactly how FFDec names the exported binaryData and font files.
    for kind in ('binaryData', 'fonts'):
        folder = os.path.join(export, kind)
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                shutil.copy2(os.path.join(folder, name), cfg.assets)

    # FFDec's line endings vary between versions; keep the source consistently CRLF.
    for path in iter_scripts(cfg.src):
        text = read(path)
        normalized = text.replace('\r\n', '\n').replace('\n', '\r\n')
        if normalized != text:
            write(path, normalized)

    stubs = [path for path in iter_scripts(cfg.src) if STUB_MARKER in read(path)]
    if stubs:
        raise SystemExit('FFDec skipped methods in:\n  ' + '\n  '.join(stubs))
    print('Exported %d scripts and %d assets to %s' % (sum(1 for _ in iter_scripts(cfg.src)),
                                                      len(os.listdir(cfg.assets)), cfg.src))
    project.write_asconfig(cfg)


def run_ffdec(cfg, export):
    """Runs FFDec and shows its output, or with cfg.quiet one progress line instead.

    FFDec decompiles in parallel and reports each script when it finishes, numbered by its
    position in the SWF. The packet handler (script 412 in the current client) starts early
    but finishes last, after several minutes on its own.
    """
    args = [cfg.ffdec, '-config', FFDEC_CONFIG, '-export', 'script,binaryData,font', export, cfg.swf]
    proc = subprocess.Popen(args, env=cfg.env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace')
    log, done, start = [], 0, time.time()
    try:
        for line in proc.stdout:
            log.append(line)
            if not cfg.quiet:
                sys.stdout.write(line)
                continue
            m = PROGRESS_RE.match(line)
            if m:
                done += 1
                total = int(m.group(2))
                note = '  (the last scripts are very large and take several minutes)' if total - done <= 3 and done < total else ''
                sys.stdout.write(('\r  %d/%d scripts, %d:%02d%s' % (done, total, *divmod(int(time.time() - start), 60), note)).ljust(90))
                sys.stdout.flush()
        proc.wait()
    except BaseException:
        # Ctrl+C or an error here would otherwise leave FFDec's Java process running.
        # ffdec-cli.exe starts Java as a child, so stop the whole process tree.
        if os.name == 'nt':
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        raise
    if cfg.quiet:
        print()
    if proc.returncode != 0:
        if cfg.quiet:
            print(''.join(log[-20:]))
        raise SystemExit('FFDec failed (exit code %d). Its output is above.' % proc.returncode)

# Remaining work

Open tasks for this repository. Written so a new session can continue without the earlier conversation.

This is a proof of work, not a product: by default every tool prints what FFDec and the compiler say, unfiltered. Hiding is only ever opt-in, through a flag (`--quiet`, `--no-warnings`).

No open tasks. Confirmed from a fresh clone: `decompile.py setup`, `all --readable`, `build.py` and `build.py --debug` work, `git status --short` stays empty after `all --force`, and the built SWF runs in Flash Player 32 up to the login screen.

## Working notes

- **Build and test:** `python build.py [--debug]` from the repo root. Debug runs: `C:\Projects\study\tfm\flashplayer_32_sa_debug.exe transformice\bin\Transformice-debug.swf`, log in `%APPDATA%\Macromedia\Flash Player\Logs\flashlog.txt` (needs `%USERPROFILE%\mm.cfg`, see [docs/debugging.md](docs/debugging.md)).
- **Full check:** `python decompile.py all --force --readable` in a fresh clone takes about 10 minutes; compare the result with a known-good run.
- **Line endings:** generated `.as` files are CRLF, Python files LF (`.gitattributes`). Some editors insert LF lines into CRLF files; normalize after editing.
- **Compiler output:** `decompiler/project.py` `build()` parses `build.py`'s error lines with `ERROR_RE` for the `fix` stage, so keep them in mxmlc's format.
- **`missing_return` output:** the `fix` stage prints it as `missing_return _o585744546.as(521)` (a location, not a count like the other fixers) and leaves it out when the source already compiles. Cosmetic, left as is.

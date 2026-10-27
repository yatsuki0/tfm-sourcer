# tfm-sourcer: guide for AI agents

Two Python tools. `decompile.py` turns `Transformice.swf` into an editable ActionScript 3 project. `build.py` compiles that project back into a SWF that runs in Flash Player 32. This is a research proof of work: the README is for users, `docs/` explains how and why, and this file covers what you need to change the code safely.

## Rules

- **Never commit game files.** That means no SWF and no decompiled source. `Transformice.swf`, the generated project (`transformice/` by default), `.cache/` and `tfm-sourcer.config.json` are in `.gitignore`; keep it that way. Don't paste decompiled game code into docs or commit messages beyond short illustrative lines.
- **Show tool output as-is by default.** FFDec's and the compiler's output is passed through unfiltered. Anything that hides output must be an opt-in flag, like `--quiet` or `--no-warnings`. Never filter output to make it look cleaner.
- **Python 3.8+, standard library only.** No pip dependencies.
- **Fixers are patterns, never hard-coded names.** Obfuscated names (`_o585744546`) and file names change with every game version. A fixer must match the shape of the bug.
- **The compiler is Flex 4.10, and only Flex 4.10.** Its legacy mxmlc writes ABC 46.16, like the original. The AIR SDK writes ABC 47.16, and Flash Player 32 quits on it. See docs/decompiler.md, "Why Flex 4.10".
- **`build.py` stays standalone.** It must not import `decompiler/`, and it must work with only a project folder and the compiler.
- **Keep the compiler's error format.** `decompiler/project.py` `build()` runs `build.py` and parses its output with `ERROR_RE` (`file.as(line): col: N Error: message`) for the `fix` stage. Don't reformat, wrap or reorder those lines.
- **Line endings:** `.py` and docs are LF, generated `.as` files are CRLF (`.gitattributes`, `export.py`).
- **No `.vscode/` folders,** and no instructions about running a game server in the docs.
- **Commits:** the repository's local Git identity is the owner's (`yatsuki0`); don't change it. No AI attribution lines (`Co-Authored-By`) in commit messages. Don't push, and don't rewrite history, unless the user asks.

## Map

| Path | What it is |
|---|---|
| `decompile.py` | CLI: `setup`, `all`, `export`, `deobfuscate`, `fix`, `readable`, `info`. Common flags: `--swf`, `--project`, `--quiet`, `--no-warnings` |
| `build.py` | CLI: compiles `<project>/src` using `<project>/asconfig.json`. Flags: `--debug`, `--no-warnings`, `--project`, `--output`, `--sdk` |
| `decompiler/config.py` | Loads `tfm-sourcer.config.json` (creating it from the example), resolves paths, holds `quiet` and `no_warnings` |
| `decompiler/export.py` | Stage 1: runs FFDec with raised timeouts, copies scripts and assets into `src/`, normalizes to CRLF, fails on "Not decompiled" stubs, writes `asconfig.json` |
| `decompiler/names.py` | The reversible renaming scheme: `§...§` tokens become `_o<digits>` |
| `decompiler/deobfuscate.py` | Stage 2: applies `names.py` to file contents, file names and `[Embed]` paths |
| `decompiler/fixes.py` | Stage 3: `SOURCE_FIXERS` (text patterns), then `ERROR_FIXERS` (driven by compile errors) in a compile loop |
| `decompiler/readable.py` | Optional stage: inlines constants, unwraps identity functions, folds literal arithmetic, under strict safety rules |
| `decompiler/project.py` | Reads build settings from the SWF (`Target`), writes `asconfig.json`, runs `build.py` and parses its errors |
| `decompiler/swf.py` | Minimal SWF reader: header, tags, SymbolClass, ProductInfo, ABC versions |
| `decompiler/setup_sdk.py` | Downloads and checksum-verifies Flex 4.10 and `playerglobal.swc` 32.0, patches `flex-config.xml` |
| `decompiler/files.py` | File helpers. Writes and renames retry, because the antivirus briefly locks freshly written files |
| `docs/` | `research.md` (findings for the team lead), `decompiler.md` (stages), `decompiler-fixes.md` (one section per fixer), `debugging.md` |

## Common changes

**A new decompiler bug that a text pattern can fix.** Add a function `name(text, ctx) -> (text, count)` to `fixes.py`. Its docstring says what FFDec gets wrong and why the fix is safe. Add it to `SOURCE_FIXERS`, then add a `## name` section to `docs/decompiler-fixes.md`. If it's a new kind of mistake, update the count in `docs/research.md`, finding 4.

**A bug that only shows as a compile error.** Add a function `name(cfg, error)` that edits `error.file` at `error.line`, and register it in `ERROR_FIXERS` under the exact compiler message. The `fix` loop recompiles until the source builds, or stops on errors no fixer knows.

**A bug that compiles but breaks the game.** The client swallows many errors, so it's often invisible. Use a debug build and the debug projector's log (`docs/debugging.md`) to find it, then turn the fix into a source fixer.

**A new CLI option.** Add it to the argparse help, the module docstring's usage lines, and the README's tables.

## Verify

You need `Transformice.swf` in the repository folder and `python decompile.py setup` done. The SWF isn't in the repo; ask the user if it's missing.

- **Build only:** `python build.py`. It should end with `Built ...\Transformice.swf (N bytes)` and show about 25 warnings from the original code.
- **Fix stage on an existing project:** `python decompile.py fix`. Every fixer prints 0, then `Source compiles.`
- **Full pipeline:** `python decompile.py all --force --readable`. It takes about 11 minutes, mostly FFDec, so run it in the background and send its output to a file. It should exit with code 0, print `Source compiles.` and a `Built` line, and leave `git status --short` empty. If the pipeline itself didn't change, copy `transformice/src` before the run and compare it after: the source should be byte-identical. The built SWF's tag contents should be identical too; only the string-pool order varies between folders.
- **In the game:** only the user can check that the built SWF reaches the login screen with texts, flag and banner in Flash Player 32. Ask them.
- **If an export is interrupted,** check that no FFDec `java.exe` is left running. `export.py` stops the process tree on errors and Ctrl+C, but check anyway.

## Environment notes

- Windows. The shell may be Git Bash or PowerShell. Bash heredocs and `python -c` strings can mangle backslashes (`\t`, `\b`), so write scripts to a file, or use an editor tool, for any text with backslashes.
- Machine-specific paths (Flex SDK, FFDec, Java, the Flash Player projector) live only in `tfm-sourcer.config.json` or with the user. Never hard-code them in the code or the docs.

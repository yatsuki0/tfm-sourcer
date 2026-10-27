# tfm-sourcer

Turn `Transformice.swf` into an editable ActionScript 3 project, and build it back into a SWF that runs in Flash Player 32.

There are two tools:

- **`decompile.py`** creates the source. It decompiles the SWF with FFDec, renames the obfuscated identifiers, and repairs the code that FFDec decompiles wrongly. Run it once per game version.
- **`build.py`** compiles that source back into a SWF, with the same compiler the original was built with (Flex 4.10). Run it each time you change the code.

What was found along the way, how it was verified and what's still open: [research summary](docs/research.md).

## Requirements

**Windows only for now.** Everything was built and tested on Windows 11, and the commands in this README are for the Windows command prompt. The code has a few branches for Linux and macOS (for example `mxmlc` instead of `mxmlc.bat`), but they have never been run. The unit tests are the exception: they don't depend on the OS.

| Tool | Version | Needed by | Notes |
|---|---|---|---|
| Python | 3.8+ | both tools | Standard library only, nothing to install with pip |
| Java | 8 | both tools | Runs the compiler and FFDec |
| [Apache Flex SDK](https://archive.apache.org/dist/flex/4.10.0/binaries/) | 4.10.0 | both tools | The compiler. Installed for you by `python decompile.py setup` |
| `playerglobal.swc` | 32.0 | both tools | The Flash Player 32 API the compiler builds against. Installed for you by `setup` |
| [JPEXS FFDec](https://github.com/jindrapetrik/jpexs-decompiler/releases) | 26.4.0 | `decompile.py` | The decompiler. Install it yourself; 26.4.0 is the version tested |
| Flash Player projector | 32 | running the game | The standalone player. The debug version also shows errors, see [debugging](docs/debugging.md) |

## Setup

1. **Create your config.** Both tools read their paths from `tfm-sourcer.config.json` in the repository folder. Copy the example and edit the paths for your machine:
   ```bat
   copy tfm-sourcer.config.example.json tfm-sourcer.config.json
   ```
   ```json
   {
       "swf": "Transformice.swf",
       "project": "transformice",
       "ffdec": "C:/Program Files (x86)/FFDec/ffdec-cli.exe",
       "flex_sdk": "../flex/sdk-4.10.0",
       "java_home": ""
   }
   ```

   | Key | What it is |
   |---|---|
   | `swf` | The game's SWF file to decompile |
   | `project` | The folder where the generated project goes (source, build settings, built SWF). Any name works |
   | `ffdec` | Path to FFDec's command-line program, `ffdec-cli.exe` |
   | `flex_sdk` | The folder where `setup` installs the compiler. It doesn't need to exist yet |
   | `java_home` | Your Java 8 folder. Leave it empty if `java` on your `PATH` is already Java 8 |
   | `playerglobal` | Optional, not in the example: a local `playerglobal.swc` to use instead of downloading Adobe's |

   Relative paths are relative to the repository folder. If you forget this step, the first command you run copies the example for you. The config isn't committed, since its paths are personal.

2. **Install the compiler.** This downloads Flex 4.10 (70 MB) and Adobe's `playerglobal.swc`, checks their checksums, and configures the compiler for Flash Player 32:
   ```bat
   python decompile.py setup
   ```
   It ends with a checklist, so you can see that every part is in place.

## Decompile

Copy the game's `Transformice.swf` into the repository folder (or point `swf` in the config at it). Either form works:

- **The client as downloaded.** It's packed: a small loader with the game cut into pieces inside it. `decompile.py` unpacks it automatically ([how](docs/decompiler.md#packed-swfs)).
- **An already unpacked or dumped game SWF.** It's used as it is.

Then run:

```bat
python decompile.py all --readable --no-warnings
```

This takes about 10 minutes, mostly FFDec. It creates the project in `transformice/` and builds it once at the end, so `transformice\bin\Transformice.swf` is ready to run right away.

What the flags in this example do:

- `--readable` also replaces the obfuscated constants with their real values, which makes the code much easier to read. Leave it out to keep the source as close to the original as possible.
- `--no-warnings` hides the compiler's warnings. The original game code triggers about 25 of them, which would bury the rest of the output. Remove the flag to see them.

To decompile again into a project that already exists, add `--force`. It replaces `transformice/src`, so any changes you made there are lost. Without `--force`, your source is never overwritten.

`all` runs these stages in order. You can also run each one on its own:

| Command | What it does |
|---|---|
| `python decompile.py setup` | Installs and configures the compiler (see [Setup](#setup)) |
| `python decompile.py all` | Runs `export`, `deobfuscate`, `fix`, `readable` (only with `--readable`), then builds |
| `python decompile.py export` | Unpacks the SWF if it's packed, decompiles it with FFDec into `transformice/src`, and writes the build settings to `transformice/asconfig.json` |
| `python decompile.py deobfuscate` | Renames the obfuscated identifiers, which aren't valid ActionScript, to valid names |
| `python decompile.py fix` | Repairs the code FFDec decompiles wrongly, then compiles to check that it builds |
| `python decompile.py readable` | Optional: replaces the obfuscated constants with their values ([details](docs/decompiler.md#optional-readable)) |
| `python decompile.py info [FILE]` | Shows what's inside a SWF: compiler, bytecode version, main class, tags. Reads the configured SWF if you don't give a file |

Options every command accepts:

| Option | What it does |
|---|---|
| `--swf PATH` | Decompile this SWF instead of the one set in the config |
| `--project PATH` | Use this project folder instead of the one set in the config |
| `--no-warnings` | Hide the compiler's warnings |
| `--quiet` | Show a progress line and short summaries instead of FFDec's and the compiler's full output |

By default you see everything FFDec and the compiler print: one line per exported script, and every compiler warning and error.

`--swf` and `--project` let you keep several game versions side by side without editing the config:

```bat
python decompile.py all --swf D:\versions\Transformice_1.857.swf --project D:\tfm-1.857
```

## Build

`decompile.py all` already built the game once. After you change the source, rebuild it in one of two ways. Both compile `transformice/src` into `transformice\bin\Transformice.swf` with the same compiler and the same build settings (`transformice/asconfig.json`), so they produce the same SWF.

### Option 1: `build.py` (command line)

```bat
python build.py --no-warnings
```

The compiler's output is shown as it is. Remove `--no-warnings` to also see its warnings.

| Option | What it does |
|---|---|
| `--debug` | Builds `Transformice-debug.swf` instead, with line numbers in error messages, for the [debug player](docs/debugging.md) |
| `--no-warnings` | Hide the compiler's warnings |
| `--pack` | Also write `transformice\bin\packed\Transformice.swf`: your rebuilt game packed into the original loader, like the downloaded file. Only for a project decompiled from a packed SWF |
| `--project PATH` | Build the project in this folder instead of the one set in the config |
| `--output PATH` | Write the built SWF to this file instead of `transformice\bin\Transformice.swf` |
| `--sdk PATH` | Use the Flex SDK in this folder instead of the one set in the config |

`build.py` only needs the project folder and the compiler: not FFDec, the decompiler, or the original SWF.

### Option 2: VS Code

1. Install the **ActionScript & MXML** extension (BowlerHat).
2. In your VS Code user settings, set `as3mxml.sdk.framework` to the Flex SDK folder (the `flex_sdk` path from your config).
3. Open the `transformice` folder and run **ActionScript: Compile** from the command palette.

The extension reads `transformice/asconfig.json` directly. This way is set up but hasn't been tested yet; `build.py` is the tested one.

### Run the game

Open `transformice\bin\Transformice.swf` with the Flash Player 32 projector. For error messages with file and line numbers, build with `--debug` and run `Transformice-debug.swf` in the debug projector, as described in [debugging](docs/debugging.md).

## Tests

```bat
python -m unittest
```

These are small unit tests that run in under a second. They need nothing but Python: no FFDec, compiler or game SWF. They check the renaming scheme, each decompiler fix, the readable stage, the SWF reader, unpacking and `--pack`, and `build.py`'s compiler arguments, all on small made-up snippets. They don't replace a full run (`python decompile.py all --force`) and checking the game in Flash Player.

## Layout

```
decompile.py                      Transformice.swf -> transformice/src
build.py                          transformice/src -> transformice/bin/Transformice.swf
decompiler/                       the decompile stages, the SWF reader and the compiler setup
docs/                             how it works
tests/                            unit tests (python -m unittest)
tfm-sourcer.config.example.json   template for your tfm-sourcer.config.json

Not committed:
Transformice.swf                  the game's SWF (input)
tfm-sourcer.config.json           your tool paths
transformice/                     the generated project; open this folder in VS Code
  src/                              ActionScript source and embedded assets
  asconfig.json                     build settings, read from the original SWF
  bin/                              built SWFs (bin/packed/ with --pack)
  loader/                           packed SWFs only: the unpacked game, the original loader, the chunk order
.cache/                           FFDec's raw export, downloads and test builds; safe to delete
```

## Documentation

- [Research summary](docs/research.md): key findings, how they were verified, approaches that failed, and open points
- [How the decompiler works](docs/decompiler.md): each stage, the renaming scheme, the optional readable stage, and why Flex 4.10
- [Decompiler fixes](docs/decompiler-fixes.md): every bug FFDec introduces and how it's repaired
- [Debugging](docs/debugging.md): debug builds, logs, and common problems

## Disclaimer

This is a research project, made for study purposes only: to learn how a Flash game can be decompiled and rebuilt. It is not affiliated with, endorsed by or connected to the game's developer.

- The game, its code, art and other assets belong to its developer. This repository contains none of them: no SWF and no decompiled source. The tools work on the game's SWF.
- Don't publish the decompiled source or modified builds, and don't use them against the official servers in ways their terms of service forbid, such as cheating or disrupting other players.
- Check that decompiling the game is allowed where you live and under the game's terms before you use these tools.
- The tools are provided as is, without any warranty.

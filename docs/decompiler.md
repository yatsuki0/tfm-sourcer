# How the decompiler works

`python decompile.py all` runs three stages, plus an [optional fourth](#optional-readable), and then builds the game. Each stage can also run on its own.

```
Transformice.swf ──export──▶ transformice/src/ (obfuscated) ──deobfuscate──▶ transformice/src/ (valid names)
                 ──fix──▶ transformice/src/ (compiles, behaves like the original)
                 ──readable (optional)──▶ transformice/src/ (constants inlined)
                 ──build.py──▶ transformice/bin/Transformice.swf
```

## Packed SWFs

The client as downloaded is **packed**: `Transformice.swf` is a small loader (8 KB of code), and the game is a second SWF cut into 12 pieces, stored as binary-data chunks inside it. At runtime the loader joins the chunks in a fixed, shuffled order and runs the result with `Loader.loadBytes`:

```actionscript
bytes.writeBytes(new ChunkC());     // the loader hides these names behind string
bytes.writeBytes(new ChunkB());     // obfuscation: every string is built from
...                                 // one-character functions over an alphabet
loader.loadBytes(bytes, context);   // context.allowCodeImport = true
```

There is no encryption. A dumped SWF (for example made with a SWF dumper while the game runs) is the joined game SWF itself, saved uncompressed.

[decompiler/unpack.py](../decompiler/unpack.py) recovers the game without reading the loader's code, since that obfuscation may change between versions. The game SWF is compressed (`CWS`), so its body is one zlib stream. Starting from the chunk that begins with `CWS`, only the right next chunk continues the stream without a decompression error. The order is proven at the end: zlib checks the stream's checksum, and the unpacked length must match the SWF header. On the 2026-10-27 client, the order found this way (`3 2 10 12 7 8 1 5 4 9 11 6`) is the same as the one in the loader's decoded code.

The export stage does this automatically. `python decompile.py info` shows whether a SWF is packed. For a packed SWF, the project gets a `loader/` folder:

| File | What it is |
|---|---|
| `loader/game.swf` | The unpacked game. FFDec decompiles this one, and the build settings (60 fps) come from it, not from the loader (36 fps) |
| `loader/loader.swf` | A copy of the original loader |
| `loader/chunks.json` | The chunk ids in the order the loader joins them |

`python build.py --pack` does the reverse. After the normal build, it cuts the new game into as many pieces as there are chunks, puts them into a copy of the original loader in that order, and writes `bin/packed/Transformice.swf`. The loader's code isn't changed or recompiled. Packing the original game back this way reproduces the downloaded `Transformice.swf` byte for byte.

## 1. export

`python decompile.py export [--force]` ([decompiler/export.py](../decompiler/export.py))

Unpacks the game first if the SWF is [packed](#packed-swfs). Then runs FFDec to export the scripts, embedded binary data and fonts into `.cache/export`, then lays them out as a project:

| From | To |
|---|---|
| `.cache/export/scripts/` | `transformice/src/` |
| `.cache/export/binaryData/`, `.cache/export/fonts/` | `transformice/src/_assets/` |

The scripts reference their assets as `[Embed(source="/_assets/<id>_<class>.bin")]`, and FFDec names the exported asset files exactly that way. Line endings are normalized to CRLF, because they vary between FFDec versions.

**Timeouts.** FFDec stops decompiling a method after 60 seconds and writes a stub instead:

```actionscript
throw new flash.errors.IllegalOperationError("Not decompiled due to timeout");
```

The client's packet handler is one method of about 11,600 instructions that needs about 5.5 minutes, so the default settings always lose it, and the rebuilt client can't read anything the server sends. The stage runs FFDec with:

```
decompilationTimeoutSingleMethod=3600, decompilationTimeoutFile=7200, exportTimeout=14400
```

and fails if any `Not decompiled` stub is left.

Last, it writes the [project settings](#the-project-folder).

## 2. deobfuscate

`python decompile.py deobfuscate` ([decompiler/deobfuscate.py](../decompiler/deobfuscate.py), [decompiler/names.py](../decompiler/names.py))

The obfuscator names almost everything with the control characters 0x01–0x08. FFDec shows them as `§\x07\b\b\x04\b\x06\x07\x05\x04\x05§`, which no compiler accepts. Each character becomes one digit, with an `_o` prefix:

| FFDec | Renamed |
|---|---|
| `§\x07\b\b\x04§` | `_o7884` |
| `§\x07\b\b\x04\b\x06\x07\x05\x04\x05_x_TransformiceFLA§` | `_o7884867545_x_TransformiceFLA` |
| file `§%5Cx07%5Cb%5Cb%5Cx04§.as` | file `_o7884.as` |

`\x01`–`\x07` become `1`–`7`, and `\b` (0x08) becomes `8`. Readable parts are kept. The same mapping applies to code, file names and `[Embed]` paths, so classes and assets stay in sync. The stage stops if two different names would map to the same identifier.

The scheme is reversible: to find `_o5857584886827` in FFDec, turn each digit back into its character.

Renaming is safe at runtime: the embedded asset SWFs don't refer to any of these names.

## 3. fix

`python decompile.py fix` ([decompiler/fixes.py](../decompiler/fixes.py))

Repairs code that FFDec decompiles wrongly. Each fixer matches a pattern, not a file or a name, so it keeps working when a new game version changes the obfuscated names. The stage prints how often each fixer applied, then compiles with `build.py`. Known compiler errors are fixed automatically, and anything unknown stops the stage with the file and line. Running it again is safe: a second run finds nothing to change.

See [decompiler-fixes.md](decompiler-fixes.md) for every fixer.

## Optional: readable

`python decompile.py readable`, or `python decompile.py all --readable` ([decompiler/readable.py](../decompiler/readable.py))

Not part of the default run. The obfuscator hides every literal value: it moves them into static fields of "holder" classes, computes numbers with fake arithmetic, and wraps uses in functions that just return their argument. Reading `1` looks like this:

```actionscript
_o631668322._o1641368864887(_o736138528867._o3743336367547)
```

This stage undoes that, repeating three rewrites until nothing changes:

| Rewrite | Before | After |
|---|---|---|
| Inline constants | `_o7685511488._o6224771648617` | `2472` |
| Unwrap identity functions | `_o631668322._o1641368864887(1)` | `1` |
| Fold literal arithmetic | `(6479 + -6474) / (5757 + -5747)` | `0.5` |

In the current client that's about 32,000 constants inlined, 13,600 wrappers removed and 4,600 expressions folded. For example, the packet reader goes from

```actionscript
this._o4325358283283 |= (b & 0x7F) << this._o52872226746 * _o6871263536434._o66282742116;
if((b & 0x80) == 128 && this._o52872226746 < _o8438745214835._o4327711482265)
```

to

```actionscript
this._o4325358283283 |= (b & 0x7F) << this._o52872226746 * 7;
if((b & 0x80) == 128 && this._o52872226746 < 5)
```

Each rewrite only applies where it can't change behaviour:

- Only fields with a literal value that are **never written** anywhere are inlined (389 aren't).
- A wrapper is only removed around a literal of its own type, so no type conversion is lost.
- Arithmetic is only folded when no other operator touches it: `x * 2 + 3` and `"a" + 2 + 3` stay as they are.
- In a class's own static initializers, fields keep their reference, because there they may still be uninitialized.
- Negative values keep their parentheses, so `-f(-5)` can't become `--5`.

The holder fields stay in place, so anything that still refers to them keeps working. The readable build was checked in the debug projector: it compiles, connects and logs no errors. It hasn't been through a full play session yet.

## The project folder

The decompiler reads the build settings from `Transformice.swf` once ([decompiler/project.py](../decompiler/project.py)) and writes them to `transformice/asconfig.json`:

| Setting | Read from | Value for the current game |
|---|---|---|
| Main class | SymbolClass entry 0 | `_o8555124375` |
| Stage size | header | 800×600 |
| Frame rate | header | 60 |
| Background | SetBackgroundColor tag | `#6a7495` |
| SWF version | header | 14 |

From then on, building doesn't need the decompiler or the original SWF. [build.py](../build.py) and the VS Code extension both read `transformice/asconfig.json`, so the two builds always match. `build.py` takes the Flex SDK and Java paths from `tfm-sourcer.config.json`. `build.py` shows the compiler's output as-is, including about 25 warnings that the original code triggers; `--no-warnings` leaves them out.

## Why Flex 4.10

`python decompile.py info` shows that the original was built by **Adobe Flex 4.10**, and that its bytecode is **ABC 46.16**.

Modern Harman AIR SDK compilers write **ABC 47.16**. Flash Player 32 doesn't load that: the player closes as soon as the SWF opens, even for a hello world. Changing the version number in the file doesn't help, because the bytecode itself differs.

Flex 4.10 writes ABC 46.16 like the original. It needs Flash Player 32's `playerglobal.swc`, which `python decompile.py setup` downloads from Adobe and installs into the Flex SDK. If that download ever disappears, set `"playerglobal"` in `tfm-sourcer.config.json` to a local copy: every Harman AIR SDK has one in `frameworks/libs/player/32.0/`.

The rebuilt SWF is zlib-compressed, so it's smaller than the uncompressed original (about 1.8 MB against 2.8 MB).

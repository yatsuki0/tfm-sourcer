# Research summary: recompiling the Transformice client

## Goal

Get the Transformice game client (`Transformice.swf`) into editable ActionScript 3 source, compile it back into a working client, and make the whole process repeatable for new game versions.

## Result

- `python decompile.py all` turns `Transformice.swf` into a compilable project in about 10 minutes, with no manual steps.
- `python build.py` compiles it into a SWF that runs in Flash Player 32, connects to a local server and shows the full login screen (language, flag and event banner), like the original.
- The rebuilt client was played on the local server and worked (before the optional readable stage; the readable build was checked for startup, connection and errors).
- A from-scratch run in an empty folder reproduces the committed source byte for byte.

- The client as downloaded is packed: a small loader with the game cut into chunks. `decompile.py` unpacks it automatically, and `build.py --pack` packs a rebuilt game the same way. Repacking the original game reproduces the downloaded file byte for byte.

Tested on two clients: version 1.856 (a dumped, already unpacked SWF from 2025-02-27) and the packed client downloaded on 2026-10-27. The newer one needed no new fixer.

## Starting point

| Property | Original `Transformice.swf` |
|---|---|
| Size | 2,828,241 bytes, uncompressed |
| Built by | Adobe Flex 4.10, on 2025-02-27 (from its ProductInfo tag) |
| Bytecode | ABC 46.16, one block of 1.87 MB |
| Code | 1,263 scripts (including bundled libraries such as `com.bit101`), most with obfuscated names |
| Assets | 7 embedded binaries (953 KB) and 1 font |
| Server | Several hard-coded IPs and ports |

## Key findings

### 1. The original was built with Flex 4.10, and only that compiler works

The SWF's ProductInfo tag records the compiler: Adobe Flex 4.10. Its bytecode is ABC 46.16.

Current Harman AIR SDK compilers (tested: 51.4.1) write ABC 47.16. Flash Player 32 refuses that format: the player closes immediately, with no error, even for a hello world. Rewriting the version number in the file isn't enough; the bytecode itself differs.

Building with the Apache Flex SDK 4.10.0 and Flash Player 32's `playerglobal.swc` produces ABC 46.16, and the player loads it.

### 2. FFDec silently drops the most important method

FFDec stops decompiling any method after 60 seconds and writes a stub that throws `Not decompiled due to timeout`. The client's packet handler is a single method of 11,653 bytecode instructions that takes about 5.5 minutes to decompile. With default settings it's always lost, and the rebuilt client can't process anything from the server.

Raising FFDec's timeouts recovers it completely: about 3,400 lines of source.

### 3. The obfuscated names follow a simple, reversible scheme

13,752 identifiers are built from the control characters 0x01–0x08, for example `\x07\b\b\x04`. No compiler accepts them. Mapping each character to a digit (`_o7884`) gives valid, unique names, and the mapping can be reversed to find any class in FFDec. None of the embedded asset SWFs refer to these names, so renaming is safe at runtime.

### 4. FFDec makes six kinds of mistakes

| Mistake | Occurrences | Effect |
|---|---|---|
| Constant assigned in a constructor | 8 | Compile error |
| `this.` in a field initializer | 13 | Compile error (Flex 4.10 only) |
| Property access on `null` (obfuscator junk) | 2 | Compile error |
| Raw bytecode left for a closure variable | 1 | Compile error |
| Missing `return` after a `try/catch` | 1 | Compile error (Flex 4.10 only) |
| **Missing `break` in the packet length loop** | 1 | **Compiles, but the game receives nothing** |

The last one is the important one. The socket reader decodes each packet's length 7 bits at a time. Without the `break`, it reads the packet's data as more length bytes, every packet fails with `Error #2030: End of file`, and a `catch` hides the error. The client connects, but the login screen stays empty. It was found by adding a trace to that `catch` in a debug build.

All six are now fixed automatically by pattern, not by file or name, so the fixes should carry over to new game versions. Details: [decompiler-fixes.md](decompiler-fixes.md).

### 5. The client reports its own size to the server

The handshake includes the byte length of the running SWF (`stage.loaderInfo.bytes.length`). The rebuilt client reports the original file's length instead, so it identifies itself like the original. This wasn't the cause of any failure we saw; it's kept for fidelity.

Which length is the original's depends on packing (finding 8). `stage.loaderInfo` belongs to the outermost SWF, so the real client reports the size of the downloaded loader (2,032,821 bytes for the 2026-10-27 client), not of the game inside it. The 2,828,241 used with the dumped 1.856 client was the dump's own size, which the real client probably never sent. The pipeline now uses the size of the SWF it was given, which is the loader for a packed client. This is reasoned from how Flash Player works, not yet checked against the official server.

### 6. The obfuscator hides every constant, and that can be undone safely

Every literal is moved into static fields of "holder" classes, computed with fake arithmetic (`6875 + -4403`), and wrapped in functions that return their argument. Reading `1` takes `_o631668322._o1641368864887(_o736138528867._o3743336367547)`.

An optional stage undoes this: about 32,000 constants inlined, 13,600 wrappers removed and 4,600 expressions folded. It only rewrites where the result is guaranteed to be the same: constants that are never written to, wrappers around a literal of their own type, and arithmetic no other operator touches. Details: [decompiler.md](decompiler.md#optional-readable).

### 7. The stage size in the old project template was wrong

The project template that came with the original export said 800×800. The SWF header says 800×600. The build settings are now read from the SWF itself: main class, stage size, frame rate, background and SWF version.

### 8. The downloaded client is a packed loader

The `Transformice.swf` you download (2,032,821 bytes on 2026-10-27) isn't the game. It's a loader with 8 KB of code and 12 binary chunks of about 170 KB each. The loader joins the chunks in a shuffled order and runs the result, which is the real game SWF: compressed, built the same day, with the same structure as the dumped 1.856 client. There's no encryption. The loader hides its strings, including the order, behind a 64-character alphabet and one-character functions, so a static read of its code shows nothing useful until those are decoded.

The order can be recovered without reading that code at all. The game's body is one zlib stream, and only the right next chunk continues it without an error, so the chunks can be chained one by one; zlib's checksum and the SWF header's length prove the result. Details: [decompiler.md](decompiler.md#packed-swfs).

## Verification

| Check | Result |
|---|---|
| Full run from an empty folder | Reproduces the committed source byte for byte (1,263 files) and `asconfig.json` |
| Rebuilt SWF vs. the committed build | Same tags and assets; bytecode has the same length and identical constant pools (952 ints, 267 doubles, 20,149 strings) |
| Repeat builds in the same folder | Byte-identical |
| Runtime (release projector 32.0.0.101) | Opens, connects to the local server, login screen complete |
| Runtime (debug projector 32.0.0.403) | Connects, no errors logged, for both the plain and the readable source |
| Gameplay | Played on the local server with the plain source, worked; the readable source wasn't played |
| Packed client (2026-10-27) | Unpacked, decompiled, fixed and built with no manual step and no new fixer. The order found from the zlib stream matches the loader's decoded code |
| Repacking | Packing the original game back into the loader reproduces the downloaded file byte for byte |
| Runtime, packed client | Both the rebuilt game (`bin\Transformice.swf`) and the repacked one (`bin\packed\Transformice.swf`) reach the login screen in Flash Player 32 (readable source) |

Two differences are expected and harmless:

- FFDec writes slightly different `.ttf` bytes for the embedded font on every export. The compiled font in the SWF came out identical.
- The Flex compiler orders its string table differently depending on the folder the source is in. Same strings, same code; only the order inside the file changes.

## Approaches that didn't work

| Tried | Why it failed |
|---|---|
| Building with Harman AIR SDK 51.4.1 | ABC 47.16; Flash Player 32 exits immediately |
| Building uncompressed, or from another folder | Not the cause; same result |
| Copying the original's ProductInfo and metadata tags into the build | The player still refused it |
| Patching the ABC version from 47.16 to 46.16 | The player still refused it; the bytecode differs beyond the version |
| Testing in AIR's `adl` runner | Different security sandbox from the browser player; not representative |
| Reporting the original SWF length alone | Kept, but it wasn't the cause of the empty login screen |

## Tools and versions

| Tool | Version used |
|---|---|
| Operating system | Windows 11 (the only one tested) |
| JPEXS FFDec | 26.4.0 |
| Apache Flex SDK | 4.10.0, with Adobe's `playerglobal.swc` 32.0 |
| Java | 1.8.0_202 |
| Python | 3.11.9 (3.8 is the minimum by reading the code, not tested) |
| Flash Player | 32.0.0.101 (release projector), 32.0.0.403 (debug projector) |

## Open points

- **Testing depth.** Startup, connection, login screen and a play session were checked. There's no systematic test of every feature, and bugs like the missing `break` can hide behind swallowed errors. The debug method in [debugging.md](debugging.md) is how to find them.
- **Other game versions.** Only this version was tested. The fixers are written as patterns, but a new version may bring new decompiler mistakes; the `fix` stage then stops and names the file and line.
- **Other packers.** Unpacking handles a loader whose chunks join into a compressed (`CWS`) SWF, which is what the 2026-10-27 client uses. A future client could pack differently; `decompile.py info` shows whether a SWF is recognized as packed.
- **Windows only.** Everything ran on Windows 11. The code has Linux and macOS branches (`mxmlc` instead of `mxmlc.bat`, stopping FFDec), but they have never been run.
- **VS Code compiling** is configured but wasn't tested.
- **FFDec versions.** Only 26.4.0 was tested. Older versions wrote CRLF line endings and fewer junk statements, both of which the pipeline handles.

## Possible next steps

1. **Map the network protocol:** each packet code, its handler and its fields.
2. **Make the server address configurable** instead of the hard-coded `127.0.0.1`.
3. **Give real names** to the main classes (connection, packet handling, rooms, players), now that the code is readable.

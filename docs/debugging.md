# Debugging the rebuilt client

The client catches and hides many errors, so a broken feature often shows nothing at all. The Flash Player **debug** projector can log errors and `trace()` output with file and line numbers.

## Setup

1. Get `flashplayer_32_sa_debug.exe`. Adobe no longer hosts it; check that the file's digital signature says Adobe Inc.
2. Create `C:\Users\<you>\mm.cfg`:
   ```
   ErrorReportingEnable=1
   TraceOutputFileEnable=1
   MaxWarnings=0
   ```

## Run

```bat
python build.py --debug
flashplayer_32_sa_debug.exe transformice\bin\Transformice-debug.swf
```

Then read `%APPDATA%\Macromedia\Flash Player\Logs\flashlog.txt`.

The normal projector writes no log, whatever `mm.cfg` says.

## When nothing is logged

The error is probably caught and swallowed. Add a trace to the `catch` blocks near the feature that misbehaves:

```actionscript
catch(e:Error)
{
   trace(e.getStackTrace());
   ...
}
```

That's how [varint_missing_break](decompiler-fixes.md#varint_missing_break) was found: the trace in the packet reader's `catch` showed `Error #2030: End of file` with the exact line.

Two warnings about `transformice.com/crossdomain.xml` appear in every run, including with the original SWF, and can be ignored.

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| The player closes as soon as the SWF opens | Built with an AIR SDK compiler (ABC 47.16) | Build with Flex 4.10: `python decompile.py setup` |
| `unable to open '{playerglobalHome}/32.0/playerglobal.swc'` | Flex SDK not configured | `python decompile.py setup` |
| `Flex SDK not found` | `flex_sdk` in the config is wrong, or `setup` hasn't run | Fix the path, then `python decompile.py setup` |
| `...asconfig.json not found. Is ... a project folder?` | `build.py` points at a folder without a decompiled project | Check `project` in the config or `--project`, or run `python decompile.py all` |
| `FFDec skipped methods in: ...` | FFDec timed out | Raise the timeouts in [decompiler/export.py](../decompiler/export.py) |
| Login screen without texts, flag or banner | Packet reader broken | Check that `varint_missing_break` applied once in `python decompile.py fix` |
| `Security Sandbox Violation ... server cannot be reached` | No game server is listening on `127.0.0.1` | Not a build problem: the client is fine, it just has nothing to connect to |

# Decompiler fixes

FFDec's output doesn't compile as-is, and one of its mistakes compiles fine but breaks the game. `python decompile.py fix` repairs all known cases. Each fixer is a pattern, not a file or a name, so it should keep working on new game versions. The counts are from client version 1.856.

| Fixer | Count | Without it |
|---|---|---|
| [const_assigned_in_constructor](#const_assigned_in_constructor) | 8 | Compile error |
| [this_in_field_initializer](#this_in_field_initializer) | 13 | Compile error |
| [null_property_access](#null_property_access) | 2 | Compile error |
| [activation_slot](#activation_slot) | 1 | Compile error |
| [missing_return](#missing_return) | 1 | Compile error |
| [varint_missing_break](#varint_missing_break) | 1 | **Compiles, but the login screen stays empty** |
| [original_swf_length](#original_swf_length) | 1 | The handshake reports the rebuilt SWF's size instead of the original's |
| [junk_literal_statements](#junk_literal_statements) | 8 | Nothing; cleanup only |

The other mistake that breaks the game, FFDec skipping the packet handler after its timeout, is prevented during export ([decompiler.md](decompiler.md#1-export)).

## const_assigned_in_constructor

**Error:** `Illegal assignment to a variable specified as constant.`

FFDec moves field initializers into the constructor. A constant then has no initializer, and gets assigned in the constructor, which the compiler rejects.

```actionscript
public const cache:Dictionary;          // before
public var cache:Dictionary;            // after
```

Applies to instance constants declared without an initializer.

## this_in_field_initializer

**Error:** `Access of possibly undefined property x through a reference with static type Class.`

Flex 4.10 reads `this` in a field initializer as the class, not the instance. Without `this.`, the name still refers to the same instance field.

```actionscript
public var size:int = this.defaultSize;   // before
public var size:int = defaultSize;        // after
```

## null_property_access

**Error:** a compile error on `null.x`.

Junk code from the obfuscator, in a branch that never runs:

```actionscript
null.x = 1;                    // before
(null as Object).x = 1;        // after
```

The cast compiles, and it would still throw at runtime exactly like the original bytecode.

## activation_slot

**Error:** `Call to a possibly undefined method _opush.`

When a local variable is captured by a closure, FFDec sometimes can't name it and leaves raw bytecode operations:

```actionscript
_opush(_onewactivation());
var _temp_3:* = new <Item>[a, b];
_opop()._oslot[16] = new <Item>[a, b];
```

The slot is the function's only local of that value's type (`Vector.<Item>`), so the three lines become:

```actionscript
result = new <Item>[a, b];
```

If more than one local could match, the fixer stops and asks for a manual fix.

## missing_return

**Error:** `Function does not return a value.`

A function ends with a `try/catch` where both branches return. Flex 4.10 doesn't see that the end can't be reached. The fixer runs on the compiler's error and adds an unreachable `return` of the right default (`null`, `0`, `false` or `NaN`) before the closing brace.

## varint_missing_break

**Symptom:** it compiles and connects, but the login screen has no texts, language flag or event banner. With a debug build, every packet fails with:

```
Error: Error #2030: End of file was encountered.
    at flash.net::Socket/readBytes()
```

The socket reader decodes each packet's length as a varint, 7 bits per byte, where the high bit means another byte follows. FFDec dropped the `break` after the last length byte, so the loop reads the packet body as more length bytes. The length becomes garbage, reading the body hits the end of the data, and a `catch` hides the error. The game never gets the server's data.

```actionscript
while(socket.bytesAvailable)
{
   b = socket.readByte() & 0xFF;
   length |= (b & 0x7F) << count * 7;
   ++count;
   if((b & 0x80) == 128 && count < 5)
   {
      continue;
   }
   lengthComplete = true;
   break;                    // restored
}
if(!lengthComplete)
{
   return;                   // wait for the rest of the length
}
// read the packet body
```

The decompiled code had an unconditional `return;` after the loop. That's replaced too, so a packet whose body has already arrived is read straight away.

## original_swf_length

The client sends the byte length of its own SWF (`stage.loaderInfo.bytes.length`) in its handshake. A rebuilt SWF has a different length, so the fixer adds a constant with the original file's size and sends that instead:

```actionscript
public static const ORIGINAL_SWF_LENGTH:int = 2828241;
...
this.swfLength = ORIGINAL_SWF_LENGTH;      // was stage.loaderInfo.bytes.length
```

The value is read from `Transformice.swf` on every run.

Leaving the rebuilt size in place didn't cause any failure we could see with the local server. The fixer is kept so the rebuilt client identifies itself exactly like the original, in case a server checks it.

## junk_literal_statements

Newer FFDec versions keep obfuscator leftovers such as a lone `true;` or `false;` statement. They compile and do nothing, so the fixer removes them to keep the source clean. FFDec versions that drop them on their own just give a count of 0.

## When something new comes up

If a new game version brings an error no fixer knows, `python decompile.py fix` stops and prints the file and line. Fix it by hand once, then turn it into a fixer in [decompiler/fixes.py](../decompiler/fixes.py), as a pattern rather than a hard-coded name, so the next run handles it.

Bugs that compile but break the game are harder to find, because the client catches and hides many errors. See [debugging.md](debugging.md).

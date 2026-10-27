"""The fix stage's fixers, on small made-up snippets shaped like FFDec's output."""
import os
import shutil
import tempfile
import unittest

from decompiler import fixes
from decompiler.files import read, write
from decompiler.project import CompileError


class SourceFixersTest(unittest.TestCase):
    def test_const_assigned_in_constructor(self):
        text = '      public const size:int;\n      public static const MAX:int = 5;\n'
        result, count = fixes.const_assigned_in_constructor(text, {})
        self.assertEqual(result, '      public var size:int;\n      public static const MAX:int = 5;\n')
        self.assertEqual(count, 1)

    def test_const_with_initializer_is_kept(self):
        text = '      public const size:int = 3;\n'
        self.assertEqual(fixes.const_assigned_in_constructor(text, {}), (text, 0))

    def test_this_in_field_initializer(self):
        text = '      public var total:int = this.a + this.b;\n         this.c = 1;\n'
        result, count = fixes.this_in_field_initializer(text, {})
        self.assertEqual(result, '      public var total:int = a + b;\n         this.c = 1;\n')
        self.assertEqual(count, 2)

    def test_null_property_access(self):
        result, count = fixes.null_property_access('null.x = 1;\nfoo.null.y;\n"null.z";\n', {})
        self.assertEqual(result, '(null as Object).x = 1;\nfoo.null.y;\n"null.z";\n')
        self.assertEqual(count, 1)

    def test_junk_literal_statements(self):
        text = '         a();\n         true;\n         false;\n         b();\n'
        result, count = fixes.junk_literal_statements(text, {})
        self.assertEqual(result, '         a();\n         b();\n')
        self.assertEqual(count, 2)

    def test_junk_between_blank_lines_leaves_one_blank_line(self):
        text = '      }\n\n      true;\n\n      public function f() : void\n'
        result, count = fixes.junk_literal_statements(text, {})
        self.assertEqual(result, '      }\n\n      public function f() : void\n')
        self.assertEqual(count, 1)

    def test_activation_slot(self):
        text = ('      public function f() : void\n'
                '      {\n'
                '         var list:Vector.<String> = null;\n'
                '         _opush(_onewactivation());\n'
                '         var _temp_1:* = new <String>["a"];\n'
                '         _opop()._oslot[1] = new <String>["a"];\n'
                '      }\n')
        result, count = fixes.activation_slot(text, {})
        self.assertEqual(count, 1)
        self.assertIn('         list = new <String>["a"];\n', result)
        self.assertNotIn('_opush', result)
        self.assertNotIn('_oslot', result)

    def test_activation_slot_with_two_candidates_stops(self):
        text = ('      public function f() : void\n'
                '      {\n'
                '         var a:Vector.<String> = null;\n'
                '         var b:Vector.<String> = null;\n'
                '         _opush(_onewactivation());\n'
                '         var _temp_1:* = new <String>["a"];\n'
                '         _opop()._oslot[1] = new <String>["a"];\n'
                '      }\n')
        with self.assertRaises(SystemExit):
            fixes.activation_slot(text, {})

    def test_varint_missing_break(self):
        text = ('            while(true)\n'
                '            {\n'
                '               b = read();\n'
                '               if((b & 0x80) == 128 && n < 5)\n'
                '               {\n'
                '                  continue;\n'
                '               }\n'
                '               this.reading = false;\n'
                '            }\n'
                '            return;\n')
        result, count = fixes.varint_missing_break(text, {})
        self.assertEqual(count, 1)
        self.assertEqual(result, (
            '            while(true)\n'
            '            {\n'
            '               b = read();\n'
            '               if((b & 0x80) == 128 && n < 5)\n'
            '               {\n'
            '                  continue;\n'
            '               }\n'
            '               this.reading = false;\n'
            '               // The decompiler dropped this break: without it the packet body is read as more length bytes.\n'
            '               break;\n'
            '            }\n'
            '            if(!this.reading)\n'
            '            {\n'
            '               return;\n'
            '            }\n'))

    def test_varint_fix_keeps_crlf(self):
        text = ('if((b & 0x80) == 128 && n < 5)\r\n{\r\ncontinue;\r\n}\r\n'
                'this.reading = false;\r\n}\r\nreturn;')
        result, count = fixes.varint_missing_break(text, {})
        self.assertEqual(count, 1)
        self.assertNotIn('\n', result.replace('\r\n', ''))

    def test_original_swf_length(self):
        text = ('      public var length:int;\n'
                '\n'
                '      public function start() : void\n'
                '      {\n'
                '         this.length = stage.loaderInfo.bytes.length;\n'
                '      }\n')
        result, count = fixes.original_swf_length(text, {'original_size': 12345})
        self.assertEqual(count, 1)
        self.assertIn('      public static const ORIGINAL_SWF_LENGTH:int = 12345;\n', result)
        self.assertIn('         this.length = ORIGINAL_SWF_LENGTH;\n', result)
        self.assertNotIn('loaderInfo', result)

    def test_original_swf_length_absent(self):
        self.assertEqual(fixes.original_swf_length('a();\n', {'original_size': 1}), ('a();\n', 0))

    def test_every_fixer_is_harmless_on_clean_code(self):
        text = ('package\n{\n   public class A\n   {\n      public var x:int = 1;\n\n'
                '      public function f() : int\n      {\n         return this.x;\n      }\n   }\n}\n')
        for fixer in fixes.SOURCE_FIXERS:
            with self.subTest(fixer=fixer.__name__):
                self.assertEqual(fixer(text, {'original_size': 1}), (text, 0))


class ErrorFixersTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)

    def check_missing_return(self, return_type, default):
        path = os.path.join(self.folder, 'A.as')
        write(path, ('      public function f() : %s\r\n'
                     '      {\r\n'
                     '         try\r\n'
                     '         {\r\n'
                     '            return g();\r\n'
                     '         }\r\n'
                     '         catch(e:Error)\r\n'
                     '         {\r\n'
                     '            return h();\r\n'
                     '         }\r\n'
                     '      }\r\n') % return_type)
        fixes.missing_return(None, CompileError(path, 11, 7, 'Function does not return a value.'))
        lines = read(path).split('\r\n')
        self.assertEqual(lines[10], '         return %s;' % default)
        self.assertEqual(lines[11], '      }')

    def test_missing_return_defaults(self):
        for return_type, default in [('int', '0'), ('uint', '0'), ('Number', 'NaN'),
                                     ('Boolean', 'false'), ('String', 'null'), ('Object', 'null')]:
            with self.subTest(return_type=return_type):
                self.check_missing_return(return_type, default)

    def test_registered_under_the_compiler_message(self):
        self.assertIs(fixes.ERROR_FIXERS['Function does not return a value.'], fixes.missing_return)


if __name__ == '__main__':
    unittest.main()

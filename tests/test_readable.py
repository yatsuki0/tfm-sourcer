"""The optional readable stage: inline constants, unwrap identity functions, fold literals."""
import unittest

from decompiler import readable


class LiteralValueTest(unittest.TestCase):
    def test_fake_arithmetic(self):
        self.assertEqual(readable.literal_value('int', '6875 + -4403'), '2472')

    def test_negative_keeps_parentheses(self):
        self.assertEqual(readable.literal_value('int', '-5'), '(-5)')

    def test_int_wraps_like_as3(self):
        self.assertEqual(readable.literal_value('int', '2147483648'), '(-2147483648)')
        self.assertEqual(readable.literal_value('int', '7 / 2'), '3')

    def test_uint_wraps_like_as3(self):
        self.assertEqual(readable.literal_value('uint', '-1'), '4294967295')

    def test_number(self):
        self.assertEqual(readable.literal_value('Number', '1 / 4'), '0.25')

    def test_string(self):
        self.assertEqual(readable.literal_value('String', '"hi"'), '"hi"')

    def test_boolean(self):
        self.assertEqual(readable.literal_value('Boolean', 'true'), 'true')
        self.assertEqual(readable.literal_value('Boolean', 'Boolean("x")'), 'true')
        self.assertEqual(readable.literal_value('Boolean', 'Boolean("")'), 'false')

    def test_not_a_literal(self):
        self.assertIsNone(readable.literal_value('int', 'f()'))
        self.assertIsNone(readable.literal_value('int', '1 / 0'))
        self.assertIsNone(readable.literal_value('String', 'a + "b"'))


class FindConstantsTest(unittest.TestCase):
    def test_written_fields_are_not_constants(self):
        files = {
            'H.as': '      public static var _oA:int = 2 + 3;\n'
                    '      public static var _oB:int = 1;\n',
            'X.as': '         H._oB = 4;\n',
        }
        self.assertEqual(readable.find_constants(files), {'_oA': ('H', '5')})

    def test_name_declared_twice_is_left_alone(self):
        files = {
            'H.as': '      public static var _oA:int = 1;\n',
            'K.as': '      public static var _oA:int = 2;\n',
        }
        self.assertEqual(readable.find_constants(files), {})


class InlineTest(unittest.TestCase):
    constants = {'_oA': ('_oH', '1')}

    def test_qualified_reference(self):
        self.assertEqual(readable.inline('x = _oH._oA;', self.constants, '_oX'), ('x = 1;', 1))

    def test_other_class_with_same_field_name_is_kept(self):
        self.assertEqual(readable.inline('x = _oK._oA;', self.constants, '_oX'), ('x = _oK._oA;', 0))

    def test_bare_reference_in_own_class(self):
        self.assertEqual(readable.inline('         x = _oA;', self.constants, '_oH'), ('         x = 1;', 1))

    def test_own_static_initializer_keeps_reference(self):
        text = '      public static var _oB:int = _oA;'
        self.assertEqual(readable.inline(text, self.constants, '_oH'), (text, 0))

    def test_number_before_dot_gets_parentheses(self):
        self.assertEqual(readable.inline('_oH._oA.toString()', self.constants, '_oX'), ('(1).toString()', 1))


class UnwrapTest(unittest.TestCase):
    wrappers = {('_oW', '_of'): 'int'}

    def test_literal_argument(self):
        self.assertEqual(readable.unwrap('x = _oW._of(5);', self.wrappers), ('x = 5;', 1))

    def test_negative_argument_keeps_parentheses(self):
        self.assertEqual(readable.unwrap('x = -_oW._of(-5);', self.wrappers), ('x = -(-5);', 1))

    def test_non_literal_argument_is_kept(self):
        self.assertEqual(readable.unwrap('x = _oW._of(y);', self.wrappers), ('x = _oW._of(y);', 0))

    def test_finds_identity_wrappers(self):
        files = {'_oW.as': 'public static function _of(param1:int) : int\n{\n   return param1;\n}\n'}
        self.assertEqual(readable.find_identity_wrappers(files), {('_oW', '_of'): 'int'})


class FoldTest(unittest.TestCase):
    def test_simple_arithmetic(self):
        self.assertEqual(readable.fold('x = 2 + 3;'), ('x = 5;', 1))

    def test_parentheses_around_a_number(self):
        self.assertEqual(readable.fold('x = (5);'), ('x = 5;', 1))

    def test_call_parentheses_are_kept(self):
        self.assertEqual(readable.fold('f(5);'), ('f(5);', 0))

    def test_method_on_number_keeps_parentheses(self):
        self.assertEqual(readable.fold('x = (5).toString();'), ('x = (5).toString();', 0))

    def test_division_by_zero_is_kept(self):
        self.assertEqual(readable.fold('x = 1 / 0;'), ('x = 1 / 0;', 0))

    def test_no_partial_fold_next_to_another_operator(self):
        # Folding "1 + 2" in "1 + 2 * 3" would change the result.
        self.assertEqual(readable.fold('x = 1 + 2 * 3;'), ('x = 1 + 2 * 3;', 0))


if __name__ == '__main__':
    unittest.main()

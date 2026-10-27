"""The renaming scheme: FFDec's §...§ tokens -> valid _o<digits> identifiers."""
import unittest

from decompiler.names import Renamer, from_raw

BS = chr(92)


class RenamerTest(unittest.TestCase):
    def test_control_characters_become_digits(self):
        # §\x07\b\b\x04§ as FFDec writes it
        token = BS + 'x07' + BS + 'b' + BS + 'b' + BS + 'x04'
        self.assertEqual(Renamer().name(token), '_o7884')

    def test_plain_parts_are_kept(self):
        token = BS + 'x07' + BS + 'b_x_Main'
        self.assertEqual(Renamer().name(token), '_o78_x_Main')

    def test_url_encoded_backslash_in_file_names(self):
        self.assertEqual(Renamer().name('%5Cx01%5Cx02'), '_o12')

    def test_text_replaces_every_token(self):
        one, two = BS + 'x01', BS + 'x02'
        text = 'var a:§%s§ = new §%s§();' % (one, two)
        self.assertEqual(Renamer().text(text), 'var a:_o1 = new _o2();')

    def test_same_token_gives_same_name(self):
        renamer = Renamer()
        token = BS + 'x03' + BS + 'x05'
        self.assertEqual(renamer.name(token), renamer.name(token))

    def test_collision_is_an_error(self):
        # "\x01" and the plain text "1" would both become _o1.
        renamer = Renamer()
        renamer.name(BS + 'x01')
        with self.assertRaises(ValueError):
            renamer.name('1')

    def test_unexpected_text_is_an_error(self):
        with self.assertRaises(ValueError):
            Renamer().name('a-b')


class FromRawTest(unittest.TestCase):
    def test_raw_control_characters(self):
        self.assertEqual(from_raw('\x08\x05\x05'), '_o855')

    def test_normal_name_is_unchanged(self):
        self.assertEqual(from_raw('Main'), 'Main')


if __name__ == '__main__':
    unittest.main()

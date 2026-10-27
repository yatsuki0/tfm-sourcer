"""build.py's compiler arguments, and how the fix stage reads compiler errors."""
import os
import shutil
import tempfile
import unittest

import build
from decompiler.project import ERROR_RE

ASCONFIG = {
    'mainClass': 'Main',
    'compilerOptions': {
        'source-path': ['src'],
        'output': 'bin/Game.swf',
        'default-background-color': '#6a7495',
        'default-frame-rate': 60,
        'default-size': {'width': 800, 'height': 600},
        'target-player': '32.0',
        'swf-version': 14,
    },
}


class MxmlcArgsTest(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project)
        os.makedirs(os.path.join(self.project, 'src'))
        self.main_file = os.path.join(self.project, 'src', 'Main.as')
        open(self.main_file, 'w').close()

    def test_settings_from_asconfig(self):
        args, output = build.mxmlc_args(self.project, ASCONFIG)
        self.assertEqual(args[0], self.main_file)
        self.assertEqual(output, os.path.join(self.project, 'bin', 'Game.swf'))
        for expected in ('-source-path=' + os.path.join(self.project, 'src'),
                         '-output=' + output,
                         '-default-background-color=0x6a7495',
                         '-default-frame-rate=60',
                         '-default-size=800,600',
                         '-target-player=32.0',
                         '-swf-version=14'):
            self.assertIn(expected, args)

    def test_warnings_shown_by_default(self):
        args, _ = build.mxmlc_args(self.project, ASCONFIG)
        self.assertFalse([a for a in args if a.startswith('-warnings')])

    def test_no_warnings(self):
        args, _ = build.mxmlc_args(self.project, ASCONFIG, warnings=False)
        self.assertIn('-warnings=false', args)

    def test_debug_build(self):
        args, output = build.mxmlc_args(self.project, ASCONFIG, debug=True)
        self.assertTrue(output.endswith('Game-debug.swf'))
        self.assertIn('-debug=true', args)

    def test_output_override(self):
        target = os.path.join(self.project, 'other.swf')
        _, output = build.mxmlc_args(self.project, ASCONFIG, output=target)
        self.assertEqual(output, target)

    def test_missing_main_class(self):
        os.remove(self.main_file)
        with self.assertRaises(SystemExit):
            build.mxmlc_args(self.project, ASCONFIG)


class ErrorLinesTest(unittest.TestCase):
    """decompiler/project.py reads build.py's output with ERROR_RE to drive the fix stage."""

    LOG = ('Loading configuration file C:\\flex\\frameworks\\flex-config.xml\n'
           'C:\\p\\src\\A.as(12): col: 5 Warning: Illogical comparison with null.\n'
           '\n'
           '         if(x == null)\n'
           '            ^\n'
           '\n'
           'C:\\p\\src\\B.as(521): col: 7 Error: Function does not return a value.\n'
           '\n'
           '      }\n'
           '      ^\n')

    def test_finds_errors_only(self):
        matches = list(ERROR_RE.finditer(self.LOG))
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual((m['file'], m['line'], m['col'], m['message']),
                         ('C:\\p\\src\\B.as', '521', '7', 'Function does not return a value.'))


if __name__ == '__main__':
    unittest.main()

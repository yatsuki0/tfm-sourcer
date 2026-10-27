"""Loads tfm-sourcer.config.json. Relative paths are resolved against the folder that holds it.

The config holds machine-specific paths, so it isn't committed. On the first run it's created
from tfm-sourcer.config.example.json.
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT, 'tfm-sourcer.config.json')
EXAMPLE_FILE = os.path.join(ROOT, 'tfm-sourcer.config.example.json')

PATH_KEYS = ('swf', 'project', 'ffdec', 'flex_sdk', 'playerglobal', 'java_home')


class Config:
    def __init__(self, values):
        for key in PATH_KEYS:
            value = values.get(key)
            if value:
                value = os.path.normpath(os.path.join(ROOT, os.path.expandvars(value)))
            setattr(self, key, value)
        self.root = ROOT
        # FFDec's raw export, downloads and throwaway builds; safe to delete.
        self.work = os.path.join(ROOT, '.cache')
        # The project folder (default "transformice") holds the AS3 source, asconfig.json and the build output.
        self.src = os.path.join(self.project, 'src')
        self.assets = os.path.join(self.src, '_assets')
        self.output = os.path.join(self.project, 'bin', os.path.basename(self.swf))
        self.mxmlc = os.path.join(self.flex_sdk, 'bin', 'mxmlc.bat' if os.name == 'nt' else 'mxmlc')
        # Tool output (FFDec, mxmlc) is shown in full unless --quiet asks for a summary.
        self.quiet = False
        self.no_warnings = False

    def require(self, *keys):
        """Stops with a clear message if a configured file doesn't exist."""
        for key in keys:
            path = getattr(self, key)
            if not path or not os.path.exists(path):
                raise SystemExit('"%s" not found: %s\nCheck "%s" in %s.' % (key, path, key, os.path.basename(CONFIG_FILE)))

    def env(self):
        """Environment for running Java tools (FFDec, mxmlc)."""
        env = dict(os.environ)
        if self.java_home:
            env['JAVA_HOME'] = self.java_home
            env['PATH'] = os.path.join(self.java_home, 'bin') + os.pathsep + env.get('PATH', '')
        return env


def load(**overrides):
    """The config file, with any non-empty overrides (e.g. --swf, --project) taking precedence.
    Override paths are taken as given, so relative ones are relative to the current directory."""
    if not os.path.isfile(CONFIG_FILE):
        shutil.copy2(EXAMPLE_FILE, CONFIG_FILE)
        print('Created %s from the example. Check the tool paths in it if a step fails.\n'
              % os.path.basename(CONFIG_FILE))
    with open(CONFIG_FILE, encoding='utf-8') as fh:
        values = json.load(fh)
    values.update({key: os.path.abspath(value) for key, value in overrides.items() if value})
    return Config(values)

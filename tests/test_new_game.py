"""The new-game scaffolder must produce a corpus the validator accepts, and must never overwrite."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / f'scripts/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load('validate')
scaffolder = load('new_game')
SHA = 'b' * 64


class NewGameTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        shutil.copytree(BASE / 'okf', self.root / 'okf')
        shutil.copy(BASE / 'catalog.json', self.root / 'catalog.json')

    def test_scaffolded_game_passes_the_validator(self):
        before = validator.validate(self.root)
        scaffolder.scaffold(self.root, 'zork2', 'Zork II', SHA)
        games, concepts = validator.validate(self.root)
        self.assertEqual((games, concepts), (before[0] + 1, before[1]))
        catalog = json.loads((self.root / 'catalog.json').read_text())
        self.assertEqual(catalog['games']['zork2'], {'title': 'Zork II', 'story_sha256': SHA, 'bundle': 'okf/zork2'})
        self.assertEqual(list(catalog['games']), sorted(catalog['games']))
        self.assertIn('* [Zork II](zork2/index.md)', (self.root / 'okf/index.md').read_text())

    def test_titles_with_yaml_punctuation_still_validate(self):
        scaffolder.scaffold(self.root, 'colon-game', 'Colon: The Game', SHA)
        validator.validate(self.root)

    def test_existing_game_is_never_overwritten(self):
        before = (self.root / 'catalog.json').read_text()
        with self.assertRaises(scaffolder.ScaffoldError):
            scaffolder.scaffold(self.root, 'lost-pig', 'Lost Pig again', SHA)
        self.assertEqual((self.root / 'catalog.json').read_text(), before)

    def test_duplicate_story_hash_is_refused_and_writes_nothing(self):
        existing = json.loads((self.root / 'catalog.json').read_text())['games']['lost-pig']['story_sha256']
        with self.assertRaises(scaffolder.ScaffoldError):
            scaffolder.scaffold(self.root, 'other-game', 'Other', existing)
        self.assertFalse((self.root / 'okf/other-game').exists())

    def test_bad_inputs_are_refused(self):
        for game_id, title, sha in [
            ('Bad_Id', 'T', SHA), ('-lead', 'T', SHA), ('two--hyphens', 'T', SHA), ('../escape', 'T', SHA),
            ('ok-id', '', SHA), ('ok-id', 'T', 'abc'), ('ok-id', 'T', 'B' * 64),
        ]:
            with self.subTest(game_id=game_id, title=title, sha=sha[:3]):
                with self.assertRaises(scaffolder.ScaffoldError):
                    scaffolder.scaffold(self.root, game_id, title, sha)
        self.assertEqual(sorted(p.name for p in (self.root / 'okf').iterdir()), ['index.md', 'lost-pig', 'zork1'])

    def test_main_reports_failure_with_exit_code(self):
        quiet = io.StringIO()
        with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
            self.assertEqual(scaffolder.main(['zork1', '--title', 'Zork I', '--story-sha256', SHA, '--root', str(self.root)]), 1)
            self.assertEqual(scaffolder.main(['zork2', '--title', 'Zork II', '--story-sha256', SHA, '--root', str(self.root)]), 0)


if __name__ == '__main__':
    unittest.main()

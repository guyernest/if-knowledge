"""Boundary checks for contributor-controlled content and catalog paths."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location('corpus_validate', Path(__file__).resolve().parents[1] / 'scripts/validate.py')
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class CorpusValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.catalog = {'version': 1, 'games': {}}
        self.write('okf/index.md', '---\ntype: Index\ntitle: Games\ndescription: All games\n---\n# Games\n')
        self.add_game('sample')

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def add_game(self, game_id):
        self.catalog['games'][game_id] = {'title': game_id, 'story_sha256': 'a' * 64, 'bundle': f'okf/{game_id}'}
        self.save_catalog()
        self.write(f'okf/{game_id}/index.md', f'---\ntype: Index\ntitle: {game_id}\ndescription: Game\ntags: [game-{game_id}]\n---\n# Game\n')

    def save_catalog(self):
        self.write('catalog.json', json.dumps(self.catalog))

    def hint(self, name='sample-opening-hint-1', game='sample', tags=None, body='Try listening.', resource=None):
        tags = tags or f'game-{game}, hint-1'
        resource = resource or f'urn:sha256:{"a" * 64}'
        return self.write(f'okf/{game}/{name}.md', f'---\ntype: Hint\ntitle: A hint\ndescription: Gentle help\ntags: [{tags}]\nstatus: draft\nsources:\n  - title: Tested story\n    resource: {resource}\n---\n{body}\n')

    def test_future_games_and_topics_are_accepted_without_app(self):
        self.hint()
        self.add_game('another-game')
        self.hint(name='another-game-new-topic', game='another-game')
        self.assertEqual(validator.validate(self.root), (2, 2))

    def test_catalog_cannot_escape_corpus(self):
        self.catalog['games']['sample']['bundle'] = '../outside'
        self.save_catalog()
        with self.assertRaisesRegex(validator.ValidationError, 'escapes'):
            validator.validate(self.root)

    def test_symlink_cannot_import_outside_content(self):
        (self.root / 'okf/sample/linked.md').symlink_to(self.root / 'catalog.json')
        with self.assertRaisesRegex(validator.ValidationError, 'symlinks'):
            validator.validate(self.root)

    def test_missing_links_are_rejected(self):
        self.hint(body='[Map](missing.md)')
        with self.assertRaisesRegex(validator.ValidationError, 'missing link'):
            validator.validate(self.root)

    def test_missing_parenthesized_links_are_rejected(self):
        for target in ('maps/unknown(1).png', 'maps/unknown(a(1)).png'):
            with self.subTest(target=target):
                self.hint(body=f'[Map]({target})')
                with self.assertRaisesRegex(validator.ValidationError, 'missing link target'):
                    validator.validate(self.root)

    def test_existing_parenthesized_links_are_accepted(self):
        self.write('okf/sample/maps/opening(1).png', 'fixture image')
        self.write('okf/sample/maps/opening(a(1)).png', 'fixture image')
        for link in ('[Map](maps/opening(1).png)',
                     '[Map](maps/opening(a(1)).png "Map (overview)")',
                     r'![Map](maps/opening\(1\).png)',
                     '[Map](<maps/opening(1).png>)'):
            with self.subTest(link=link):
                self.hint(body=link)
                self.assertEqual(validator.validate(self.root), (1, 1))

    def test_encoded_link_cannot_escape_corpus(self):
        self.hint(body='[Outside](%2e%2e/%2e%2e/catalog.json)')
        with self.assertRaisesRegex(validator.ValidationError, 'escapes'):
            validator.validate(self.root)

    def test_reference_style_missing_links_are_rejected(self):
        self.hint(body='[Map][map]\n\n[map]: missing.md')
        with self.assertRaisesRegex(validator.ValidationError, 'missing link'):
            validator.validate(self.root)

    def test_normalized_duplicate_ids_across_games_are_rejected(self):
        self.hint(name='same-hint')
        self.add_game('another')
        self.hint(name='same_hint', game='another')
        with self.assertRaisesRegex(validator.ValidationError, 'duplicate concept ID'):
            validator.validate(self.root)

    def test_concept_cannot_collide_with_index_id(self):
        self.hint(name='sample-index')
        self.add_game('another')
        with self.assertRaisesRegex(validator.ValidationError, 'duplicate document/index ID'):
            validator.validate(self.root)

    def test_missing_or_multiple_hint_tiers_are_rejected(self):
        for tags in ('game-sample', 'game-sample, hint-1, hint-2', 'game-sample, hint-4'):
            with self.subTest(tags=tags):
                self.hint(tags=tags)
                with self.assertRaisesRegex(validator.ValidationError, 'one valid hint tier'):
                    validator.validate(self.root)

    def test_conflicting_game_tags_are_rejected(self):
        self.hint(tags='game-sample, game-other, hint-1')
        with self.assertRaisesRegex(validator.ValidationError, 'conflicting game tag'):
            validator.validate(self.root)

    def test_app_local_sources_are_rejected(self):
        self.hint(resource='z-mcp/games/LostPig.z8')
        with self.assertRaisesRegex(validator.ValidationError, 'portable URL or URN'):
            validator.validate(self.root)

    def test_story_binaries_and_generated_artifacts_are_rejected(self):
        for name in ('story.z8', 'normalized.json', '.env', 'private.pem'):
            with self.subTest(name=name):
                path = self.write(f'okf/sample/{name}', 'must not publish')
                with self.assertRaisesRegex(validator.ValidationError, 'unexpected bundle file'):
                    validator.validate(self.root)
                path.unlink()


if __name__ == '__main__':
    unittest.main()

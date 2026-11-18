"""The publish client must reproduce the platform's canonical marker bytes and frame its calls correctly."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('okf_publish', BASE / 'scripts/okf_publish.py')
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)
FIXTURE = json.loads((BASE / 'tests/fixtures/repo-publish-marker.json').read_text())


class MarkerTests(unittest.TestCase):
    def test_marker_bytes_match_every_platform_fixture_case(self):
        for case in FIXTURE['cases']:
            with self.subTest(case['name']):
                marker = publisher.canonical_marker(case['input'])
                self.assertEqual(marker.decode('utf-8'), case['canonical'])
                self.assertEqual(len(marker), case['length'])
                self.assertEqual(publisher.sha256_hex(marker), case['sha256'])


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bundle = Path(self.directory.name)

    def write(self, relative, content='x'):
        path = self.bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_only_bundle_markdown_in_byte_order_and_bundle_relative(self):
        self.write('index.md', 'index')
        self.write('docs/B.md')
        self.write('docs/a.md')
        self.write('docs-x/c.md')
        self.write('notes.txt')
        self.write('.hidden/secret.md')
        self.write('docs/.draft.md')
        manifest = publisher.collect_manifest(self.bundle)
        self.assertEqual([f['path'] for f in manifest['files']], ['docs-x/c.md', 'docs/B.md', 'docs/a.md', 'index.md'])
        self.assertEqual(manifest['files'][3], {'path': 'index.md', 'sha256': publisher.sha256_hex(b'index'), 'size': 5})

    def test_empty_bundle_is_refused(self):
        with self.assertRaises(publisher.PublishError):
            publisher.collect_manifest(self.bundle)

    def test_symlink_is_refused(self):
        self.write('real.md')
        (self.bundle / 'link.md').symlink_to(self.bundle / 'real.md')
        with self.assertRaises(publisher.PublishError):
            publisher.collect_manifest(self.bundle)

    def test_real_bundle_builds_a_manifest(self):
        manifest = publisher.collect_manifest(BASE / 'okf')
        paths = [f['path'] for f in manifest['files']]
        self.assertIn('index.md', paths)
        self.assertTrue(all(p.endswith('.md') and not p.startswith('.') for p in paths))


class WireTests(unittest.TestCase):
    def test_event_carries_the_token_only_in_the_authorization_header(self):
        event = publisher.invoke_event('TOKEN', 'get_repo_publish_status', {'instance': 'i'}, 'r1')
        self.assertEqual(event['headers']['authorization'], 'Bearer TOKEN')
        self.assertNotIn('TOKEN', event['body'])
        self.assertEqual(json.loads(event['body'])['params'], {'name': 'get_repo_publish_status', 'arguments': {'instance': 'i'}})

    def response(self, body, encoded=False):
        return {'statusCode': 200, 'headers': {}, 'body': body, 'isBase64Encoded': encoded}

    def rpc_result(self, payload):
        return json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{'type': 'text', 'text': json.dumps(payload)}]}})

    def test_unwrap_plain_sse_and_base64(self):
        body = self.rpc_result({'state': 'committed'})
        self.assertEqual(publisher.unwrap(self.response(body)), {'state': 'committed'})
        self.assertEqual(publisher.unwrap(self.response('data: ' + body + '\n\n')), {'state': 'committed'})
        self.assertEqual(publisher.unwrap(self.response(base64.b64encode(body.encode()).decode(), True)), {'state': 'committed'})

    def test_errors_surface_their_fixed_text(self):
        denied = json.dumps({'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32000, 'message': 'begin_repo_publish: denied (not_bound_publisher)'}})
        with self.assertRaisesRegex(publisher.PublishError, 'not_bound_publisher'):
            publisher.unwrap(self.response(denied))
        tool_error = json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'isError': True, 'content': [{'type': 'text', 'text': 'fixed failure text'}]}})
        with self.assertRaisesRegex(publisher.PublishError, 'fixed failure text'):
            publisher.unwrap(self.response(tool_error))

    def test_summary_prints_the_outcome_without_urls(self):
        lines = publisher.summarize({'state': 'awaiting_approval', 'runId': 'r', 'adminPath': '/instances/x', 'url': 'https://s3/secret'})
        self.assertTrue(any('awaiting_approval' in line for line in lines))
        self.assertFalse(any('secret' in line for line in lines))


if __name__ == '__main__':
    unittest.main()

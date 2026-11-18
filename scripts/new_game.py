#!/usr/bin/env python3
"""Scaffold an empty knowledge bundle for a new game.

Adds the catalog entry, creates okf/<game-id>/index.md and links it from
okf/index.md. It creates no hints: copy the files in templates/ for those.
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
GAME_ID = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
BULLET = re.compile(r'^\* \[(?P<title>[^\]]+)\]\((?P<target>[^)]+)\)\s*$')
NEEDS_QUOTES = re.compile(r'''[:#\[\]{}&*!|>'"%@`,]|^\s|\s$''')


class ScaffoldError(ValueError):
    """The request cannot be scaffolded without guessing or overwriting."""


def yaml_text(value):
    # A JSON string is a valid YAML double-quoted scalar.
    return json.dumps(value) if NEEDS_QUOTES.search(value) else value


def check_inputs(game_id, title, story_sha256):
    if not GAME_ID.match(game_id):
        raise ScaffoldError('game id must be lowercase letters, digits and single hyphens, e.g. "zork2" or "lost-pig"')
    if len(game_id) > 60:
        raise ScaffoldError('game id must be at most 60 characters')
    title = ' '.join(title.split())
    if not title or len(title) > 100:
        raise ScaffoldError('title must be 1-100 characters on one line')
    if not SHA256.match(story_sha256):
        raise ScaffoldError('story SHA-256 must be 64 lowercase hex characters (the hash of the exact story file)')
    return title


def scaffold(root, game_id, title, story_sha256):
    """Create the bundle under `root`; returns the paths written. Writes nothing on error."""
    root = Path(root)
    title = check_inputs(game_id, title, story_sha256)
    catalog_path = root / 'catalog.json'
    collection_path = root / 'okf/index.md'
    bundle = root / 'okf' / game_id
    catalog = json.loads(catalog_path.read_text())
    if game_id in catalog.get('games', {}) or bundle.exists():
        raise ScaffoldError(f'game "{game_id}" already exists; extend its bundle instead of scaffolding it again')
    for existing in catalog['games'].values():
        if existing.get('story_sha256') == story_sha256:
            raise ScaffoldError('another catalog game already records this story SHA-256; check the hash')
    lines = collection_path.read_text().splitlines()
    first = next((i for i, line in enumerate(lines) if BULLET.match(line)), None)
    if first is None:
        raise ScaffoldError('okf/index.md has no bullet list of games to extend')
    last = first
    while last + 1 < len(lines) and BULLET.match(lines[last + 1]):
        last += 1
    bullets = lines[first:last + 1] + [f'* [{title}]({game_id}/index.md)']
    bullets.sort(key=lambda line: BULLET.match(line).group('title').lower())
    lines[first:last + 1] = bullets

    catalog['games'][game_id] = {'title': title, 'story_sha256': story_sha256, 'bundle': f'okf/{game_id}'}
    catalog['games'] = dict(sorted(catalog['games'].items()))

    index = (
        '---\n'
        'type: Index\n'
        f'title: {yaml_text(title + " knowledge")}\n'
        'description: Empty starter bundle awaiting community contributions.\n'
        f'tags: [game-{game_id}, bootstrap]\n'
        '---\n'
        f'# {title} knowledge\n\n'
        'This bundle intentionally has no hints, walkthrough, or map yet. Contributors\n'
        'can add reviewed, independently authored material for the story version in the catalog.\n'
    )
    bundle.mkdir(parents=True)
    (bundle / 'index.md').write_text(index)
    catalog_path.write_text(json.dumps(catalog, indent=2) + '\n')
    collection_path.write_text('\n'.join(lines) + '\n')
    return [catalog_path, collection_path, bundle / 'index.md']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game_id', help='unique id, e.g. zork2 (also the okf/<id> directory)')
    parser.add_argument('--title', required=True, help='display name, e.g. "Zork II"')
    parser.add_argument('--story-sha256', required=True, help='SHA-256 of the exact story file this bundle covers')
    parser.add_argument('--root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        written = scaffold(args.root, args.game_id, args.title, args.story_sha256)
    except (ScaffoldError, OSError, ValueError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    for path in written:
        print(f'wrote {Path(path).relative_to(args.root)}')
    print('Next: copy files from templates/ into okf/%s/ (hints/, places/), link them from an index,' % args.game_id)
    print('then run: python3 scripts/validate.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())

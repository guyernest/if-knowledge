#!/usr/bin/env python3
"""Validate this knowledge corpus without requiring an app or game binaries."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
ASSET_SUFFIXES = {'.md', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.mermaid', '.mmd'}
INLINE_START = re.compile(r'(?<!\\)\]\(\s*')
LINK_END = re.compile(r'\s*(?:"[^"\n]*"|\'[^\'\n]*\'|\([^\n)]*\))?\s*\)')
REFERENCE = re.compile(r'^\s{0,3}\[[^\]]+\]:\s*(?:<([^>]+)>|(\S+))', re.MULTILINE)


class ValidationError(ValueError):
    """A corpus error that should also reject a contributor's pull request."""


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def normalize_id(value):
    # Mirrors okf-ingest's id::normalize_id; paths and stems are selected below.
    return re.sub(r'[^A-Za-z0-9]+', '_', value).upper()


def inside(base, path):
    require(path.resolve().is_relative_to(base.resolve()), f'path escapes {base.name}: {path}')
    return path.resolve()


def read_document(path):
    text = path.read_text(encoding='utf-8')
    match = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)(.*)\Z', text, re.DOTALL)
    require(match is not None, f'{path}: missing YAML frontmatter')
    try:
        metadata = yaml.safe_load(match[1])
    except yaml.YAMLError as error:
        raise ValidationError(f'{path}: invalid YAML: {error}') from error
    require(isinstance(metadata, dict), f'{path}: frontmatter must be a mapping')
    for field in ('type', 'title', 'description'):
        require(isinstance(metadata.get(field), str) and metadata[field].strip(),
                f'{path}: missing or invalid {field}')
    require(bool(match[2].strip()), f'{path}: empty body')
    return metadata, match[2]


def inline_targets(body):
    """Read Markdown destinations, including balanced or escaped parentheses."""
    for match in INLINE_START.finditer(body):
        position, depth, target = match.end(), 0, []
        if position < len(body) and body[position] == '<':
            end = body.find('>', position + 1)
            if end != -1 and LINK_END.match(body, end + 1):
                yield body[position + 1:end]
            continue
        while position < len(body):
            character = body[position]
            if character == '\\' and position + 1 < len(body):
                escaped = body[position + 1]
                if escaped.isascii() and not escaped.isalnum() and not escaped.isspace():
                    target.append(escaped)
                    position += 2
                    continue
            if character == '(':
                depth += 1
            elif character == ')':
                if depth == 0:
                    yield ''.join(target)
                    break
                depth -= 1
            elif character.isspace():
                if depth == 0 and LINK_END.match(body, position):
                    yield ''.join(target)
                break
            target.append(character)
            position += 1


def validate_links(path, body, corpus):
    # Examples in fenced code are not navigation links.
    body = re.sub(r'(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$', '', body)
    targets = list(inline_targets(body)) + [match[1] or match[2] for match in REFERENCE.finditer(body)]
    for target in targets:
        parsed = urlsplit(target)
        if parsed.scheme:
            require(parsed.scheme in {'https', 'http', 'mailto'}, f'{path}: unsupported link {target}')
            continue
        require(not parsed.netloc, f'{path}: use an explicit https link: {target}')
        decoded = unquote(parsed.path)
        if not decoded:
            continue
        require(not decoded.startswith('/') and '\\' not in decoded,
                f'{path}: link must be relative: {target}')
        destination = inside(corpus, path.parent / decoded)
        require(destination.is_file(), f'{path}: missing link target: {target}')


def validate(root=ROOT, ingester=None):
    root = Path(root).resolve()
    corpus = root / 'okf'
    require(corpus.is_dir() and not corpus.is_symlink(), 'okf must be a real directory')
    require(not (root / 'catalog.json').is_symlink(), 'catalog.json must not be a symlink')
    manifest = json.loads((root / 'catalog.json').read_text(encoding='utf-8'))
    require(isinstance(manifest, dict) and manifest.get('version') == 1, 'unsupported catalog version')
    games = manifest.get('games')
    require(isinstance(games, dict) and games, 'catalog must contain games')
    bundles = {}
    for game_id, game in sorted(games.items()):
        require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', game_id), f'invalid game ID: {game_id}')
        require(isinstance(game, dict), f'{game_id}: invalid game entry')
        require(isinstance(game.get('title'), str) and game['title'].strip(), f'{game_id}: missing title')
        require(isinstance(game.get('story_sha256'), str) and
                re.fullmatch(r'[0-9a-f]{64}', game['story_sha256']), f'{game_id}: invalid story SHA-256')
        raw = game.get('bundle')
        require(isinstance(raw, str) and not Path(raw).is_absolute() and '\\' not in raw,
                f'{game_id}: invalid bundle path')
        bundle = inside(corpus, root / raw)
        require(bundle != corpus and bundle.is_dir(), f'{game_id}: missing game bundle')
        for other in bundles.values():
            require(not bundle.is_relative_to(other) and not other.is_relative_to(bundle),
                    f'{game_id}: overlapping game bundles')
            require(bundle.name != other.name, f'{game_id}: duplicate bundle basename')
        bundles[game_id] = bundle
        require((bundle / 'index.md').is_file(), f'{game_id}: missing root index.md')
    require((corpus / 'index.md').is_file(), 'missing aggregate okf/index.md')

    documents, concepts = [], {}
    for path in sorted(corpus.rglob('*')):
        require(not path.is_symlink(), f'symlinks are not allowed: {path}')
        if path.is_dir():
            continue
        require(path.suffix.lower() in ASSET_SUFFIXES and not path.name.startswith('.'),
                f'unexpected bundle file (binaries, secrets and generated output belong elsewhere): {path}')
        if path.suffix != '.md':
            require(path.suffix.lower() != '.md', f'use lowercase .md extension: {path}')
            continue
        owner = next((game_id for game_id, bundle in bundles.items() if path.is_relative_to(bundle)), None)
        require(owner is not None or path == corpus / 'index.md', f'uncataloged document: {path}')
        metadata, body = read_document(path)
        index = path.name == 'index.md'
        require((metadata['type'] == 'Index') == index, f'{path}: Index documents must be named index.md')
        tags = metadata.get('tags', [])
        require(isinstance(tags, list) and all(isinstance(tag, str) and tag for tag in tags),
                f'{path}: tags must be a list of strings')
        require(len(tags) == len(set(tags)), f'{path}: duplicate tags')
        if owner:
            require(f'game-{owner}' in tags, f'{path}: missing matching game tag')
            require(not any(tag.startswith('game-') and tag != f'game-{owner}' for tag in tags),
                    f'{path}: conflicting game tag')
        if not index:
            require(isinstance(metadata.get('status'), str) and metadata['status'].strip(), f'{path}: missing status')
            sources = metadata.get('sources')
            require(isinstance(sources, list) and sources, f'{path}: missing sources')
            for source in sources:
                require(isinstance(source, dict) and isinstance(source.get('title'), str) and source['title'].strip(),
                        f'{path}: source needs a title')
                resource = source.get('resource')
                require(isinstance(resource, str), f'{path}: source needs a resource')
                parsed = urlsplit(resource)
                portable = ((parsed.scheme in {'http', 'https'} and bool(parsed.netloc)) or
                            bool(re.fullmatch(r'urn:[a-zA-Z0-9][a-zA-Z0-9-]{0,31}:[^\s]+', resource)))
                require(portable, f'{path}: source resource must be a portable URL or URN')
            tiers = [tag for tag in tags if tag.startswith('hint-')]
            if metadata['type'] == 'Hint':
                require(len(tiers) == 1 and tiers[0] in {'hint-1', 'hint-2', 'hint-3'}, f'{path}: Hint needs one valid hint tier')
                require(len(body.strip()) < 1100, f'{path}: keep a hint in one small retrieval unit')
            else:
                require(not tiers, f'{path}: hint tier tags belong on Hint documents')
            doc_id = normalize_id(path.stem)
            require(doc_id not in concepts, f'duplicate concept ID {doc_id}: {path}')
            concepts[doc_id] = (path, metadata)
        validate_links(path, body, corpus)
        documents.append((path, index))

    # Index IDs occupy the same namespace as concept IDs in both ingestion modes.
    for aggregate in (False, True):
        ids = set(concepts)
        for path, index in documents:
            if not index or (not aggregate and path == corpus / 'index.md'):
                continue
            if aggregate:
                relative = path.relative_to(corpus)
            else:
                bundle = next(bundle for bundle in bundles.values() if path.is_relative_to(bundle))
                relative = path.relative_to(bundle)
                if len(bundles) > 1:
                    relative = Path(bundle.name) / relative
            doc_id = normalize_id(relative.with_suffix('').as_posix())
            require(doc_id not in ids, f'duplicate document/index ID {doc_id}: {path}')
            ids.add(doc_id)
    if ingester:
        validate_ingestion(Path(ingester).resolve(), corpus, bundles, concepts)
    return len(games), len(concepts)


def validate_ingestion(ingester, corpus, bundles, concepts):
    for roots in (list(bundles.values()), [corpus]):
        with tempfile.TemporaryDirectory(prefix='if-knowledge-ingest-') as temp:
            subprocess.run([str(ingester), *(str(path) for path in roots), temp], check=True)
            data = json.loads((Path(temp) / 'normalized.json').read_text(encoding='utf-8'))
            docs = {doc['id']: doc for doc in data['documents']}
            require(len(docs) == len(data['documents']), 'ingester returned duplicate document IDs')
            for doc_id, (path, metadata) in concepts.items():
                require(doc_id in docs, f'ingester omitted {doc_id}')
                doc = docs[doc_id]
                if roots == [corpus]:
                    expected = path.relative_to(corpus)
                else:
                    bundle = next(bundle for bundle in roots if path.is_relative_to(bundle))
                    expected = path.relative_to(bundle)
                    if len(roots) > 1:
                        expected = Path(bundle.name) / expected
                require(doc['metadata']['okf_path'] == expected.as_posix(), f'ingester changed source path for {doc_id}')
                actual_tags = set(doc['metadata'].get('tags', '').split(','))
                require(set(metadata['tags']) <= actual_tags, f'ingester lost tags for {doc_id}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ingester', type=Path, help='also check both layouts with the real okf-ingest executable')
    args = parser.parse_args()
    try:
        games, concepts = validate(ingester=args.ingester)
    except (ValidationError, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'FAIL: {error}\n')
    print(f'PASS: {games} games, {concepts} concepts; portable catalog, metadata, links and IDs')
    if args.ingester:
        print('PASS: real aggregate and multi-game OKF ingestion preserves IDs, paths and tags')


if __name__ == '__main__':
    main()

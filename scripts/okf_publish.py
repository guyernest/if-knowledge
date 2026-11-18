#!/usr/bin/env python3
"""Publish this repository's okf/ bundle to its bound platform instance, from a GitHub Actions job.

Implements the okf-sync publisher invoke contract (begin, upload, marker, commit, status):
the job assumes the publisher role, then invokes the publisher Lambda with one FRESH GitHub OIDC
token per call. The platform builds the bundle and stops at "awaiting approval"; approving and
publishing stay in the admin and are never done here.

Needs the AWS CLI on PATH and a job with `permissions: id-token: write`. Standard library only.
Never prints a token or a presigned URL.
"""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
TRANSIENT = ('the build could not be started; retry the commit', 'an internal error occurred; retry')
TERMINAL = {'awaiting_approval', 'refused', 'failed', 'approved', 'published'}
SUCCESS = {'awaiting_approval', 'approved', 'published'}


class PublishError(RuntimeError):
    """A publish step failed; the message is safe to print (no token, no presigned URL)."""


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def collect_manifest(bundle):
    """Every .md file under the bundle directory, bundle-relative, sorted by path bytes."""
    bundle = Path(bundle)
    files = []
    for path in bundle.rglob('*.md'):
        relative = path.relative_to(bundle)
        if any(part.startswith('.') for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file():
            raise PublishError(f'{relative.as_posix()} is not a regular file')
        data = path.read_bytes()
        files.append({'path': relative.as_posix(), 'sha256': sha256_hex(data), 'size': len(data)})
    if not files:
        raise PublishError(f'no .md files under {bundle}')
    files.sort(key=lambda entry: entry['path'].encode('utf-8'))
    return {'schema_version': SCHEMA_VERSION, 'files': files}


def canonical_marker(manifest):
    """The commit marker bytes: compact JSON, fixed key order, entries sorted by path bytes, no newline."""
    files = sorted(manifest['files'], key=lambda entry: entry['path'].encode('utf-8'))
    body = {'schema_version': manifest['schema_version'],
            'files': [{'path': f['path'], 'sha256': f['sha256'], 'size': f['size']} for f in files]}
    return json.dumps(body, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def fresh_jwt(audience):
    """One fresh GitHub OIDC token (the runner's request token never goes on a command line)."""
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'] + '&audience=' + urllib.parse.quote(audience, safe='')
    request = urllib.request.Request(url, headers={'Authorization': 'bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response)['value']
    print(f'::add-mask::{token}', flush=True)
    return token


def invoke_event(token, tool, arguments, request_id):
    return {
        'version': '2.0', 'routeKey': 'POST /', 'rawPath': '/', 'rawQueryString': '',
        'headers': {'content-type': 'application/json', 'accept': 'application/json, text/event-stream',
                    'authorization': 'Bearer ' + token},
        'requestContext': {'accountId': 'unknown', 'apiId': 'okf-sync-publisher-route', 'domainName': 'publisher',
                           'domainPrefix': 'api', 'http': {'method': 'POST', 'path': '/', 'protocol': 'HTTP/1.1',
                                                           'sourceIp': '0.0.0.0', 'userAgent': 'github-actions'},
                           'requestId': request_id, 'routeKey': 'POST /', 'stage': '$default',
                           'time': '04/Mar/2020:19:03:58 +0000', 'timeEpoch': 1583348638390},
        'body': json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                            'params': {'name': tool, 'arguments': arguments}}),
        'isBase64Encoded': False,
    }


def unwrap(response):
    """An API Gateway v2 response carrying one JSON-RPC answer (plain JSON or one SSE data frame)."""
    body = response.get('body', '')
    if response.get('isBase64Encoded'):
        body = base64.b64decode(body).decode('utf-8')
    if body.lstrip().startswith('data:'):
        body = next(line[5:].strip() for line in body.splitlines() if line.startswith('data:'))
    answer = json.loads(body)
    if answer.get('error'):
        raise PublishError(str(answer['error'].get('message', 'the publisher returned an error')))
    result = answer.get('result') or {}
    text = (result.get('content') or [{}])[0].get('text', '')
    if result.get('isError'):
        raise PublishError(text or 'the publisher reported a tool failure')
    return json.loads(text)


def call(function, audience, tool, arguments, label):
    """Invoke the publisher once, with a fresh token, the event handed over as a 0600 file."""
    token = fresh_jwt(audience)
    with tempfile.TemporaryDirectory() as directory:
        os.chmod(directory, 0o700)
        event_path = Path(directory) / 'event.json'
        fd = os.open(event_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(invoke_event(token, tool, arguments, label), handle)
        out_path = Path(directory) / 'out.json'
        run = subprocess.run(
            ['aws', 'lambda', 'invoke', '--function-name', function, '--cli-binary-format', 'raw-in-base64-out',
             '--payload', f'fileb://{event_path}', str(out_path)],
            capture_output=True, text=True)
        event_path.unlink()
        if run.returncode != 0:
            first = (run.stderr.strip().splitlines() or ['no error text'])[0]
            raise PublishError(f'{tool}: the invoke failed: {first[:300]}')
        if json.loads(run.stdout).get('FunctionError'):
            raise PublishError(f'{tool}: the publisher function itself failed (FunctionError)')
        return unwrap(json.loads(out_path.read_text()))


def call_retrying(function, audience, tool, arguments, label):
    for attempt in range(3):
        try:
            return call(function, audience, tool, arguments, f'{label}-{attempt}')
        except PublishError as error:
            if attempt < 2 and any(text in str(error) for text in TRANSIENT):
                time.sleep(3)
                continue
            raise


def put(url, headers, data):
    """A presigned PUT with exactly the headers the publisher returned and the file's exact bytes."""
    parts = urllib.parse.urlsplit(url)
    connection = http.client.HTTPSConnection(parts.netloc, timeout=60)
    sent = {name.lower() for name in headers}
    connection.putrequest('PUT', parts.path + ('?' + parts.query if parts.query else ''), skip_accept_encoding=True)
    for name, value in headers.items():
        if name.lower() not in ('host', 'content-length'):
            connection.putheader(name, value)
    connection.putheader('Content-Length', str(len(data)))
    connection.endheaders(data)
    response = connection.getresponse()
    response.read()
    connection.close()
    if response.status // 100 != 2:
        raise PublishError(f'an upload was refused: HTTP {response.status}')
    return sent


def publish(bundle, instance, function, audience):
    manifest = collect_manifest(bundle)
    by_path = {entry['path']: entry for entry in manifest['files']}
    marker_bytes = canonical_marker(manifest)
    print(f'manifest: {len(manifest["files"])} files, {sum(f["size"] for f in manifest["files"])} bytes', flush=True)

    publish_id, cursor, uploaded = None, None, 0
    while True:
        arguments = {'instance': instance, 'manifest': manifest}
        if publish_id:
            arguments['publish_id'] = publish_id
        if cursor:
            arguments['cursor'] = cursor
        page = call_retrying(function, audience, 'begin_repo_publish', arguments, 'begin')
        publish_id = page['publishId']
        for item in page['files']:
            data = (Path(bundle) / item['path']).read_bytes()
            if sha256_hex(data) != by_path[item['path']]['sha256'] or len(data) != by_path[item['path']]['size']:
                raise PublishError(f'{item["path"]} changed while the publish was running')
            put(item['url'], item.get('headers') or {}, data)
            uploaded += 1
        marker = page['marker']
        cursor = page.get('nextCursor')
        if not cursor:
            break
    print(f'uploaded {uploaded} files (publish {publish_id})', flush=True)

    if marker['contentLength'] != len(marker_bytes) or marker['sha256'] != sha256_hex(marker_bytes):
        raise PublishError('the commit marker the server expects differs from the canonical bytes computed here')
    put(marker['url'], marker.get('headers') or {}, marker_bytes)  # the marker goes LAST
    print('marker uploaded', flush=True)

    committed = call_retrying(function, audience, 'commit_repo_publish',
                              {'instance': instance, 'publish_id': publish_id}, 'commit')
    print(f'committed: run {committed.get("runId")}', flush=True)

    deadline, last = time.monotonic() + 540, None
    while True:
        status = call_retrying(function, audience, 'get_repo_publish_status',
                               {'instance': instance, 'publish_id': publish_id}, 'status')
        if status.get('state') != last:
            print(f'state: {status.get("state")}', flush=True)
            last = status.get('state')
        if status.get('state') in TERMINAL:
            return status
        if time.monotonic() > deadline:
            raise PublishError('timed out waiting for the build (the publish is not lost: poll its status later)')
        time.sleep(10)


def summarize(status):
    keys = ('state', 'runId', 'verdict', 'stagedVersion', 'findingCounts', 'findingCodes', 'adminPath', 'adminUrl')
    lines = [f'{key}: {json.dumps(status[key])}' for key in keys if status.get(key) is not None]
    if status.get('refusalText'):
        lines.append('refusalText: ' + status['refusalText'][:1500])
    if status.get('failure'):
        lines.append(f'failure: {status["failure"]}')
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'okf', help='bundle directory (default: okf/)')
    parser.add_argument('--instance', help='the platform instance id the repository is bound to')
    parser.add_argument('--function', default='pmcp-okf-sync-publisher')
    parser.add_argument('--audience', default=os.environ.get('AUD'), help='the OIDC audience (or env AUD)')
    parser.add_argument('--dry-run', action='store_true', help='build and print the manifest only; call nothing')
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            manifest = collect_manifest(args.bundle)
            print(f'{len(manifest["files"])} files; marker {len(canonical_marker(manifest))} bytes')
            for entry in manifest['files']:
                print(f'  {entry["path"]} ({entry["size"]} bytes)')
            return 0
        if not args.instance or not args.audience:
            parser.error('--instance and --audience (or env AUD) are required unless --dry-run')
        status = publish(args.bundle, args.instance, args.function, args.audience)
    except PublishError as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    lines = summarize(status)
    print('\n'.join(lines))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as handle:
            handle.write('### okf publish\n\n' + '\n'.join(f'- {line}' for line in lines) + '\n')
    return 0 if status.get('state') in SUCCESS else 1


if __name__ == '__main__':
    sys.exit(main())

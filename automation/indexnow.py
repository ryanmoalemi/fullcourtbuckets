#!/usr/bin/env python3
"""Tell IndexNow about HTML URLs that changed in this deploy. Never fails the build."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = 'fullcourtbuckets.com'
API = 'https://api.indexnow.org/indexnow'
ROOT = Path(__file__).resolve().parents[1]
KEY_NAME = re.compile(r'[0-9a-f]{32}\Z')


def find_key(root: Path = ROOT) -> str | None:
    for path in sorted(root.glob('*.txt')):
        stem = path.stem
        if KEY_NAME.fullmatch(stem) and path.read_text(encoding='utf-8').strip() == stem:
            return stem
    return None


def public_url(path: str) -> str | None:
    relative = path.replace('\\', '/').lstrip('/')
    if relative.startswith(('automation/', 'data/', '.github/', 'portrait-')):
        return None
    if relative == 'index.html':
        return f'https://{HOST}/'
    if relative.endswith('/index.html'):
        return f'https://{HOST}/' + relative[:-len('index.html')]
    if relative.endswith('.html'):
        return f'https://{HOST}/{relative}'
    return None


def changed_paths(root: Path, before: str) -> list[str]:
    spec = ['HEAD~1', 'HEAD']
    if re.fullmatch(r'[0-9a-fA-F]{40}', before or '') and set(before) != {'0'}:
        probe = subprocess.run(['git', 'cat-file', '-e', before + '^{commit}'], cwd=root, capture_output=True)
        if probe.returncode == 0:
            spec = [before, 'HEAD']
    result = subprocess.run(
        ['git', 'diff', '--name-only', '--diff-filter=ACMR', *spec],
        cwd=root, capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def submit(root: Path = ROOT, before: str = '') -> int:
    key = find_key(root)
    if not key:
        print('IndexNow skipped: no key file.')
        return 0
    urls = []
    seen = set()
    for path in changed_paths(root, before):
        url = public_url(path)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    if not urls:
        print('IndexNow skipped: no changed public URLs.')
        return 0
    payload_base = {
        'host': HOST,
        'key': key,
        'keyLocation': f'https://{HOST}/{key}.txt',
    }
    sent = 0
    for start in range(0, len(urls), 10000):
        body = json.dumps({**payload_base, 'urlList': urls[start:start + 10000]}).encode()
        request = urllib.request.Request(
            API, data=body, method='POST', headers={'Content-Type': 'application/json; charset=utf-8'},
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    print(f'IndexNow accepted {len(urls[start:start + 10000])} URLs (HTTP {response.status}).')
                    sent += len(urls[start:start + 10000])
                    break
            except Exception as exc:
                print(f'IndexNow attempt {attempt + 1} failed: {exc}', file=sys.stderr)
                if attempt < 2:
                    time.sleep(15)
    print(f'IndexNow finished. Submitted {sent} of {len(urls)} URLs.')
    return 0


def main() -> int:
    try:
        return submit(ROOT, os.environ.get('INDEXNOW_BEFORE', ''))
    except Exception as exc:
        print(f'IndexNow skipped: {exc}', file=sys.stderr)
        return 0


if __name__ == '__main__':
    sys.exit(main())

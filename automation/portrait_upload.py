#!/usr/bin/env python3
"""Receive one approved original PNG and store identical bytes.

Sources, exactly one per request:
  - download_url: the existing short-lived OAI/Azure whole-file URL
  - repository_path: portrait-handoff/<player_id>-<slug>-<sha256>.png in the
    same git commit as the request (Google-independent)

Never resizes, recompresses, or invents pixels. Live page verification remains
the publisher's job; this script only lands the original in GitHub.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portrait_folders import record_for

SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
SHA256 = re.compile(r'[a-f0-9]{64}\Z')
HANDOFF_DIR = 'portrait-handoff'
HANDOFF_NAME = re.compile(
    r'(?P<player_id>\d+)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<sha256>[a-f0-9]{64})\.png\Z'
)
OAI_BLOB_HOST = re.compile(r'oaisdmnt[a-z0-9]+\.blob\.core\.windows\.net\Z')
MAX_READ = 12_000_001


class UploadError(SystemExit):
    """Abort the Actions step with a precise message and no file changes."""


def trusted_host(host: str | None) -> bool:
    return bool(host and (host.endswith('.oaiusercontent.com') or OAI_BLOB_HOST.fullmatch(host)))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def git_show(commit: str, relative: str) -> bytes:
    return subprocess.check_output(['git', 'show', f'{commit}:{relative}'])


def request_from_commit(root: Path, commit: str | None) -> tuple[dict, dict]:
    request_path = root / '.github/portrait-upload.json'
    if commit:
        request = json.loads(git_show(commit, '.github/portrait-upload.json'))
    else:
        request = load_json(request_path)
    latest = load_json(request_path)
    return request, latest


def require_player(root: Path, request: dict) -> tuple[str, dict]:
    slug = request.get('slug', '')
    if not SLUG.fullmatch(slug) or request.get('approved') is not True:
        raise UploadError('A safe player slug and explicit owner approval are required.')
    profile = load_json(root / 'data/wnba/players' / f'{slug}.json')
    name = ' '.join(str(profile['player'].get(k) or '').strip() for k in ('first_name', 'last_name')).strip()
    if profile['player']['id'] != request['player_id'] or name != request['player_name'] or profile['slug'] != slug:
        raise UploadError('The approval does not match the player ID, name and slug.')
    digest = request.get('sha256', '')
    if not SHA256.fullmatch(digest):
        raise UploadError('Missing approved original checksum.')
    return slug, profile


def source_kind(request: dict) -> str:
    has_url = bool(request.get('download_url'))
    has_path = bool(request.get('repository_path'))
    if has_url and has_path:
        raise UploadError('Supply exactly one of download_url or repository_path.')
    if has_path:
        return 'repository_file'
    if has_url:
        return 'signed_url'
    raise UploadError('An original-file download_url or repository_path is required.')


def handoff_path_for(request: dict) -> Path:
    relative = request.get('repository_path', '')
    if not isinstance(relative, str) or relative.startswith('/') or '..' in Path(relative).parts:
        raise UploadError('Repository handoff path is unsafe.')
    path = Path(relative)
    if path.as_posix() != relative or path.parent.as_posix() != HANDOFF_DIR:
        raise UploadError('Repository handoff must be a file in portrait-handoff/.')
    match = HANDOFF_NAME.fullmatch(path.name)
    if not match:
        raise UploadError('Handoff filename must be <player_id>-<slug>-<sha256>.png.')
    if (int(match['player_id']) != request['player_id']
            or match['slug'] != request['slug']
            or match['sha256'] != request['sha256']):
        raise UploadError('Handoff filename does not match the approved player ID, slug and checksum.')
    return path


def bytes_from_repository_file(root: Path, request: dict, commit: str | None) -> bytes:
    relative = handoff_path_for(request).as_posix()
    if commit:
        try:
            raw = git_show(commit, relative)
        except subprocess.CalledProcessError as exc:
            raise UploadError('Repository handoff file is missing from the request commit.') from exc
    else:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise UploadError('Repository handoff file is missing.')
        if not path.resolve().is_relative_to((root / HANDOFF_DIR).resolve()):
            raise UploadError('Repository handoff path is unsafe.')
        raw = path.read_bytes()
    return raw


class StorageRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        dest = urlparse(newurl)
        if dest.scheme != 'https' or not trusted_host(dest.hostname):
            raise ValueError('Untrusted storage redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def bytes_from_signed_url(url: str, opener=None) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not trusted_host(parsed.hostname) or parsed.username or parsed.password or parsed.port:
        raise UploadError('Only the approved temporary whole-file handoff is accepted.')
    try:
        opener = opener or urllib.request.build_opener(StorageRedirect())
        with opener.open(url, timeout=60) as response:
            raw = response.read(MAX_READ)
    except urllib.error.HTTPError as exc:
        raise UploadError('Approved-file download returned HTTP ' + str(exc.code)) from exc
    except urllib.error.URLError as exc:
        raise UploadError('Approved-file connection failed: ' + str(exc.reason)) from exc
    except UploadError:
        raise
    except Exception:
        raise UploadError('Approved-file download failed: ' + type(sys.exc_info()[1]).__name__)
    return raw


def fetch_original_bytes(root: Path, request: dict, commit: str | None, opener=None) -> tuple[str, bytes]:
    kind = source_kind(request)
    if kind == 'repository_file':
        return kind, bytes_from_repository_file(root, request, commit)
    return kind, bytes_from_signed_url(request['download_url'], opener=opener)


def validate_original(raw: bytes, request: dict) -> Image.Image:
    digest = request['sha256']
    if len(raw) > 12_000_000 or len(raw) != request['bytes'] or hashlib.sha256(raw).hexdigest() != digest:
        raise UploadError('Approved original byte count/checksum did not match; nothing published.')
    image = Image.open(io.BytesIO(raw))
    image.load()
    if image.format != 'PNG' or list(image.size) != request['dimensions']:
        raise UploadError('Original image dimensions/format do not match approval.')
    if min(image.size) < 1024 or image.width * image.height > 25_000_000 or image.convert('RGBA').getchannel('A').getextrema() != (0, 255):
        raise UploadError('Use a full-resolution original with visible artwork and transparency.')
    return image


def write_originals(root: Path, request: dict, raw: bytes) -> tuple[Path, Path]:
    slug = request['slug']
    folder = root / 'images/players' / slug
    if folder.is_symlink():
        raise UploadError('Unsafe image folder.')
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'portrait.png'
    if target.is_symlink():
        raise UploadError('Unsafe target file.')
    if any((folder / ('portrait' + ext)).exists() for ext in ['.webp', '.avif']):
        raise UploadError('Another portrait format exists; do not create ambiguous image choices.')
    temporary = folder / 'portrait.png.tmp'
    temporary.write_bytes(raw)
    temporary.replace(target)
    master_dir = root / 'portrait-masters'
    master_dir.mkdir(parents=True, exist_ok=True)
    master_path = master_dir / f"{request['player_id']}-{slug}-{request['sha256']}.png"
    if master_path.exists():
        existing = master_path.read_bytes()
        if hashlib.sha256(existing).hexdigest() != request['sha256'] or existing != raw:
            raise UploadError('Existing GitHub master does not match approved original; nothing published.')
    else:
        master_path.write_bytes(raw)
    return target, master_path


def remove_handoff(root: Path, request: dict) -> Path | None:
    if source_kind(request) != 'repository_file':
        return None
    path = root / handoff_path_for(request)
    if path.is_file() and not path.is_symlink():
        path.unlink()
        return path
    return None


def write_receipt(root: Path, request: dict, target: Path, master_path: Path, raw: bytes, source: str) -> Path:
    receipt = {k: v for k, v in request.items() if k != 'download_url'}
    receipt.update(
        status='uploaded_pending_live_verification',
        path=str(target.relative_to(root)),
        original_bytes_preserved=True,
        source=source,
        github_master_path=str(master_path.relative_to(root)),
        github_blob_sha=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
    )
    receipt_path = root / 'content/portrait-upload-receipts' / f"{request['slug']}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt_path


def scrub_request(root: Path, request: dict) -> Path:
    request_path = root / '.github/portrait-upload.json'
    request_path.write_text(json.dumps({
        'request_id': request['request_id'],
        'slug': request['slug'],
        'status': 'uploaded_pending_live_verification',
        'sha256': request['sha256'],
    }, indent=2) + '\n')
    return request_path


def git_publish(root: Path, slug: str, paths: list[Path]) -> None:
    subprocess.run(['git', 'config', 'user.name', 'Full Court Buckets updater'], check=True, cwd=root)
    subprocess.run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'], check=True, cwd=root)
    rels = [str(path.relative_to(root)) for path in paths]
    subprocess.run(['git', 'add', '--', *rels], check=True, cwd=root)
    if subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=root).returncode:
        subprocess.run(['git', 'commit', '-m', 'Upload approved full-resolution portrait: ' + slug], check=True, cwd=root)
        subprocess.run(['git', 'pull', '--rebase', 'origin', 'main'], check=True, cwd=root)
        subprocess.run(['git', 'push', 'origin', 'HEAD:main'], check=True, cwd=root)


def process(root: Path, request: dict, commit: str | None = None, opener=None, publish_git: bool = False) -> dict:
    slug, _profile = require_player(root, request)
    source, raw = fetch_original_bytes(root, request, commit, opener=opener)
    validate_original(raw, request)
    target, master_path = write_originals(root, request, raw)
    record = record_for(root, target)
    receipt_path = write_receipt(root, request, target, master_path, raw, source)
    removed = remove_handoff(root, request)
    request_path = scrub_request(root, request)
    if publish_git:
        tracked = [target, master_path, receipt_path, request_path]
        if removed is not None:
            tracked.append(removed)
        git_publish(root, slug, tracked)
    return {
        'slug': slug,
        'source': source,
        'width': record['width'],
        'height': record['height'],
        'sha256': request['sha256'],
        'path': str(target.relative_to(root)),
        'github_master_path': str(master_path.relative_to(root)),
    }


def main() -> None:
    root = Path.cwd()
    commit = os.environ.get('REQUEST_COMMIT')
    request, latest = request_from_commit(root, commit)
    if latest.get('request_id') != request.get('request_id'):
        raise UploadError('Upload superseded by a newer request; no files changed.')
    if request.get('status') == 'uploaded_pending_live_verification':
        print('Original already uploaded. No duplicate upload.')
        return
    result = process(root, request, commit=commit, publish_git=os.environ.get('PORTRAIT_UPLOAD_DRY_RUN') != '1')
    print('Uploaded exact approved original:', result['slug'], result['width'], result['height'], result['sha256'])
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a') as handle:
            handle.write('uploaded=true\n')


if __name__ == '__main__':
    main()

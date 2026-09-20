"""Whole-file portrait upload: signed URL and Google-independent repo handoff."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import portrait_upload as upload


class FakeResponse:
    def __init__(self, data):
        self.data = data
    def read(self, n=-1):
        return self.data if n < 0 else self.data[:n]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, data):
        self.data = data
        self.requested = None
    def open(self, url, timeout=60):
        self.requested = url
        return FakeResponse(self.data)


class PortraitUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data/wnba/players').mkdir(parents=True)
        (self.root / 'content/portrait-upload-receipts').mkdir(parents=True)
        (self.root / '.github').mkdir(parents=True)
        (self.root / 'portrait-handoff').mkdir(parents=True)
        (self.root / '.github/portrait-upload.json').write_text('{}\n')
        self.slug = 'example-player'
        self.player_id = 42
        (self.root / f'data/wnba/players/{self.slug}.json').write_text(json.dumps({
            'slug': self.slug,
            'player': {'id': self.player_id, 'first_name': 'Example', 'last_name': 'Player'},
        }))

    def png_bytes(self, size=(1024, 1024)):
        image = Image.new('RGBA', size, (120, 70, 50, 255))
        image.putpixel((0, 0), (0, 0, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()

    def request_for(self, raw, **extra):
        request = {
            'request_id': '42-test-upload',
            'player_id': self.player_id,
            'player_name': 'Example Player',
            'slug': self.slug,
            'approved': True,
            'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw),
            'dimensions': [1024, 1024],
        }
        request.update(extra)
        return request

    def test_repository_file_preserves_exact_bytes_and_scrubs_url_less_request(self):
        raw = self.png_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        relative = f'portrait-handoff/{self.player_id}-{self.slug}-{digest}.png'
        (self.root / relative).write_bytes(raw)
        request = self.request_for(raw, repository_path=relative)
        result = upload.process(self.root, request)
        published = (self.root / f'images/players/{self.slug}/portrait.png').read_bytes()
        master = (self.root / f'portrait-masters/{self.player_id}-{self.slug}-{digest}.png').read_bytes()
        self.assertEqual(published, raw)
        self.assertEqual(master, raw)
        self.assertEqual(result['source'], 'repository_file')
        self.assertFalse((self.root / relative).exists())
        stub = json.loads((self.root / '.github/portrait-upload.json').read_text())
        self.assertEqual(stub['status'], 'uploaded_pending_live_verification')
        self.assertNotIn('download_url', stub)
        receipt = json.loads((self.root / f'content/portrait-upload-receipts/{self.slug}.json').read_text())
        self.assertTrue(receipt['original_bytes_preserved'])
        self.assertEqual(receipt['source'], 'repository_file')
        self.assertNotIn('download_url', receipt)
        self.assertEqual(receipt['github_blob_sha'], hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest())

    def test_signed_url_from_approved_host_preserves_bytes(self):
        raw = self.png_bytes()
        url = 'https://files.oaiusercontent.com/private/original.png?sv=2026&sig=secret'
        result = upload.process(self.root, self.request_for(raw, download_url=url), opener=FakeOpener(raw))
        self.assertEqual(result['source'], 'signed_url')
        self.assertEqual((self.root / f'images/players/{self.slug}/portrait.png').read_bytes(), raw)

    def test_azure_blob_host_is_still_trusted(self):
        self.assertTrue(upload.trusted_host('oaisdmntabc123.blob.core.windows.net'))
        self.assertTrue(upload.trusted_host('files.oaiusercontent.com'))
        self.assertFalse(upload.trusted_host('github.com'))
        self.assertFalse(upload.trusted_host('objects.githubusercontent.com'))
        self.assertFalse(upload.trusted_host('drive.google.com'))

    def test_rejects_untrusted_download_host(self):
        raw = self.png_bytes()
        with self.assertRaises(upload.UploadError) as caught:
            upload.process(self.root, self.request_for(raw, download_url='https://example.com/portrait.png'))
        self.assertIn('approved temporary whole-file handoff', str(caught.exception))
        self.assertFalse((self.root / f'images/players/{self.slug}/portrait.png').exists())

    def test_rejects_both_sources(self):
        raw = self.png_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        relative = f'portrait-handoff/{self.player_id}-{self.slug}-{digest}.png'
        (self.root / relative).write_bytes(raw)
        with self.assertRaises(upload.UploadError):
            upload.process(self.root, self.request_for(
                raw, download_url='https://files.oaiusercontent.com/x.png', repository_path=relative))

    def test_rejects_path_traversal_handoff(self):
        raw = self.png_bytes()
        with self.assertRaises(upload.UploadError):
            upload.process(self.root, self.request_for(raw, repository_path='portrait-handoff/../secret.png'))

    def test_rejects_handoff_filename_that_does_not_bind_player_and_hash(self):
        raw = self.png_bytes()
        relative = f'portrait-handoff/1-{self.slug}-{hashlib.sha256(raw).hexdigest()}.png'
        (self.root / relative).write_bytes(raw)
        with self.assertRaises(upload.UploadError):
            upload.process(self.root, self.request_for(raw, repository_path=relative))

    def test_checksum_mismatch_does_not_publish(self):
        raw = self.png_bytes()
        other = self.png_bytes(size=(1025, 1024))
        digest = hashlib.sha256(raw).hexdigest()
        relative = f'portrait-handoff/{self.player_id}-{self.slug}-{digest}.png'
        (self.root / relative).write_bytes(other)
        with self.assertRaises(upload.UploadError) as caught:
            upload.process(self.root, self.request_for(raw, repository_path=relative))
        self.assertIn('byte count/checksum', str(caught.exception))
        self.assertFalse((self.root / f'images/players/{self.slug}/portrait.png').exists())
        self.assertTrue((self.root / relative).exists())

    def test_existing_master_mismatch_is_refused(self):
        raw = self.png_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        master = self.root / f'portrait-masters/{self.player_id}-{self.slug}-{digest}.png'
        master.parent.mkdir(parents=True)
        master.write_bytes(b'not-the-original')
        relative = f'portrait-handoff/{self.player_id}-{self.slug}-{digest}.png'
        (self.root / relative).write_bytes(raw)
        with self.assertRaises(upload.UploadError):
            upload.process(self.root, self.request_for(raw, repository_path=relative))
        self.assertEqual(master.read_bytes(), b'not-the-original')

    def test_existing_verified_github_masters_are_untouched_by_this_change(self):
        root = Path(__file__).resolve().parents[1]
        ashlon = root / 'portrait-masters/67147-ashlon-jackson-23db58ae84a633670083527a4061ade363932f6dca5d1adc4e5dc3417fd4473d.png'
        antonia = root / 'portrait-masters/67043-antonia-delaere-93afdad4f6cf041c82afdb8000708d748236b69694946b24bae53f3df0bf0858.png'
        self.assertEqual(hashlib.sha256(ashlon.read_bytes()).hexdigest(),
                         '23db58ae84a633670083527a4061ade363932f6dca5d1adc4e5dc3417fd4473d')
        self.assertEqual(hashlib.sha256(antonia.read_bytes()).hexdigest(),
                         '93afdad4f6cf041c82afdb8000708d748236b69694946b24bae53f3df0bf0858')

    def test_live_request_stub_is_already_uploaded(self):
        repo = Path(__file__).resolve().parents[1]
        stub = json.loads((repo / '.github/portrait-upload.json').read_text())
        self.assertEqual(stub['status'], 'uploaded_pending_live_verification')
        self.assertRegex(stub.get('slug', ''), r'^[a-z0-9]+(?:-[a-z0-9]+)*\Z')
        self.assertRegex(stub.get('sha256', ''), r'^[a-f0-9]{64}\Z')
        self.assertTrue(stub.get('request_id'))
        self.assertNotIn('download_url', stub)
        self.assertNotIn('repository_path', stub)

    def test_main_noops_when_request_already_uploaded(self):
        raw = self.png_bytes()
        request = self.request_for(raw, status='uploaded_pending_live_verification')
        (self.root / '.github/portrait-upload.json').write_text(json.dumps(request) + '\n')
        cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        os.environ.pop('REQUEST_COMMIT', None)
        upload.main()
        self.assertFalse((self.root / f'images/players/{self.slug}/portrait.png').exists())


if __name__ == '__main__':
    unittest.main()

"""IndexNow stays optional. These tests do not call the network."""
import tempfile
import unittest
from pathlib import Path

import indexnow


class IndexNowTests(unittest.TestCase):
    def test_public_urls_skip_private_files(self):
        self.assertEqual(indexnow.public_url('index.html'), 'https://fullcourtbuckets.com/')
        self.assertEqual(indexnow.public_url('wnba/aja-wilson/index.html'), 'https://fullcourtbuckets.com/wnba/aja-wilson/')
        self.assertEqual(indexnow.public_url('standings/index.html'), 'https://fullcourtbuckets.com/standings/')
        self.assertIsNone(indexnow.public_url('data/wnba/status.json'))
        self.assertIsNone(indexnow.public_url('automation/build_players.py'))
        self.assertIsNone(indexnow.public_url('9e8571afa2db2872fe525e2d2be7cfaf.txt'))

    def test_missing_key_does_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(indexnow.find_key(Path(tmp)))
            self.assertEqual(indexnow.submit(Path(tmp), ''), 0)

    def test_key_file_matches_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'abcdef0123456789abcdef0123456789.txt').write_text('not-the-key\n', encoding='utf-8')
            self.assertIsNone(indexnow.find_key(root))
            (root / 'abcdef0123456789abcdef0123456789.txt').write_text('abcdef0123456789abcdef0123456789\n', encoding='utf-8')
            self.assertEqual(indexnow.find_key(root), 'abcdef0123456789abcdef0123456789')


if __name__ == '__main__':
    unittest.main()

"""Every page has a unique, in-range <title> and meta description."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
import seo_meta  # noqa: E402


class SeoMeta(unittest.TestCase):
    def test_every_page_has_unique_in_range_title_and_description(self):
        problems = seo_meta.audit(ROOT)
        self.assertEqual(problems, [], '\n'.join(problems[:40]))

    def test_overrides_are_in_range(self):
        for path, o in seo_meta.load_overrides(ROOT).items():
            if 'title' in o:
                self.assertTrue(seo_meta.title_ok(o['title']), f'{path}: {o["title"]}')
            if 'description' in o:
                self.assertTrue(seo_meta.desc_ok(o['description']), f'{path}: {len(o["description"])}')
            self.assertTrue((ROOT / path.strip('/') / 'index.html').is_file() or path == '/', path)

    def test_family_rules_stay_in_range(self):
        for name in ('Awa Fam', 'Darianna Littlepage-Buggs', "A'ja Wilson", 'DeMya Chakheia Walker'):
            self.assertTrue(seo_meta.title_ok(seo_meta.player_title(name)), name)
            self.assertNotIn('Stats & Profile', seo_meta.player_title(name))
        for team in ('Chicago Sky', 'Golden State Valkyries'):
            self.assertTrue(seo_meta.title_ok(seo_meta.team_title(team)), team)
        self.assertTrue(seo_meta.title_ok(seo_meta.owner_title('Lisa Bhathal Merage', 'Portland Fire')))
        for n in range(1, 8):
            self.assertTrue(seo_meta.title_ok(seo_meta.pbp_title(n)))
        self.assertTrue(seo_meta.desc_ok(seo_meta.player_description('Awa Fam is a center.')))
        self.assertTrue(seo_meta.desc_ok(seo_meta.fit_description('x ' * 120)))

    def test_no_espn_credit_and_streaming_next_to_tv(self):
        for page in ROOT.rglob('*.html'):
            if '.git' in page.parts or 'node_modules' in page.parts:
                continue
            text = page.read_text(encoding='utf-8', errors='ignore')
            self.assertNotIn('Stream: ESPN App', text, page)
            self.assertNotIn('ESPN noted', text, page)
            for line in __import__('re').findall(r'class="broadcast-line"[^>]*>([^<]*)<', text):
                if 'TV:' in line:
                    self.assertIn('Stream:', line, page)

    def test_audit_catches_problems(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for slug, title in (('a', 'Short'), ('b', 'A long enough descriptive page title for testing'),
                                ('c', 'A long enough descriptive page title for testing')):
                (root / slug).mkdir()
                (root / slug / 'index.html').write_text(f'<html><head><title>{title}</title></head></html>')
            out = '\n'.join(seo_meta.audit(root))
            self.assertIn('/a/: title is 5 characters', out)
            self.assertIn('missing meta description', out)
            self.assertIn('/c/: title duplicates /b/', out)


if __name__ == '__main__':
    unittest.main()

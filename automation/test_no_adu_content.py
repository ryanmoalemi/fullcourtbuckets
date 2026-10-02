"""Former ADU pages are deleted. The builder must not recreate them."""
import unittest
from pathlib import Path
import build_players as builder
from link_graph import iter_html

ROOT = Path(__file__).resolve().parents[1]
SCAN = (
    'sitemap.xml',
    'pages-sitemap.xml',
    'player-sitemap.xml',
    'robots.txt',
    'index.html',
    'articles.json',
)
PUBLISHED_SUFFIXES = {'.html', '.xml', '.js', '.json', '.txt'}


class NoAduContent(unittest.TestCase):
    def test_removed_paths_are_gone(self):
        self.assertGreaterEqual(len(builder.REMOVED_ADU_PATHS), 16)
        for relative in sorted(builder.REMOVED_ADU_PATHS):
            self.assertFalse((ROOT / relative).exists(), relative)
            with self.assertRaises(builder.BuildError):
                builder.reject_removed_adu(relative, '<p>accessory dwelling</p>')

    def test_sitemaps_and_homepage_do_not_list_adu_urls(self):
        for name in SCAN:
            text = (ROOT / name).read_text().casefold()
            self.assertNotIn('sandiegoadubuilder', text, name)
            self.assertNotIn('accessory dwelling', text, name)
            for relative in builder.REMOVED_ADU_PATHS:
                self.assertNotIn(relative.casefold(), text, name)

    def test_published_files_do_not_mention_adu(self):
        removed = set(builder.REMOVED_ADU_PATHS)
        offenders = []
        for path in ROOT.rglob('*'):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(ROOT).as_posix()
            if relative in removed or relative.startswith(('automation/', '.git/', 'content/', 'data/')):
                continue
            if path.suffix.lower() not in PUBLISHED_SUFFIXES:
                continue
            text = path.read_text(encoding='utf-8', errors='replace').casefold()
            if 'sandiegoadubuilder' in text or 'accessory dwelling' in text:
                offenders.append(relative)
                continue
            for adu in builder.REMOVED_ADU_PATHS:
                if adu.casefold() in text:
                    offenders.append(f'{relative} mentions {adu}')
        self.assertEqual(offenders, [])

    def test_builder_refuses_adu_output(self):
        for relative in builder.REMOVED_ADU_PATHS:
            with self.assertRaises(builder.BuildError):
                builder.reject_removed_adu(relative, '<p>WNBA</p>')
        with self.assertRaises(builder.BuildError):
            builder.reject_removed_adu('wnba/index.html', 'https://sandiegoadubuilder.com/adu-cost.html')
        builder.reject_removed_adu('wnba/caitlin-clark/index.html', '<p>WNBA stats</p>')
        for path in iter_html(ROOT):
            relative = path.relative_to(ROOT).as_posix()
            if relative in builder.REMOVED_ADU_PATHS:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'sandiegoadubuilder.com' in text:
                self.fail(relative)

"""Former ADU URLs are tiny noindex redirects. Full ADU pages stay blocked."""
import tempfile
import unittest
from pathlib import Path
import build_players as builder
import site_nav
from link_graph import iter_html

ROOT = Path(__file__).resolve().parents[1]
SCAN = (
    'sitemap.xml',
    'pages-sitemap.xml',
    'player-sitemap.xml',
    'sitemap/index.html',
    'robots.txt',
    'index.html',
    'articles.json',
)
PUBLISHED_SUFFIXES = {'.html', '.xml', '.js', '.json', '.txt'}
HOME_ONLY = {
    'projects/craftsman-backyard-cottage.html',
    'projects/rice-street-east-block.html',
    'projects/rice-street-west-block.html',
}


class NoAduContent(unittest.TestCase):
    def test_removed_paths_are_redirect_stubs(self):
        self.assertGreaterEqual(len(builder.REMOVED_ADU_PATHS), 16)
        self.assertEqual(set(builder.ADU_REDIRECT_TARGETS), set(builder.REMOVED_ADU_PATHS))
        for relative in sorted(builder.REMOVED_ADU_PATHS):
            target = builder.ADU_REDIRECT_TARGETS[relative]
            self.assertTrue(target.startswith('https://sandiegoadubuilder.com'), relative)
            if relative in HOME_ONLY:
                self.assertEqual(target, 'https://sandiegoadubuilder.com/')
            else:
                self.assertEqual(target, 'https://sandiegoadubuilder.com/' + relative)
            stub = builder.adu_redirect_html(relative)
            text = (ROOT / relative).read_text(encoding='utf-8')
            self.assertEqual(text, stub, relative)
            self.assertIn(f'<link rel="canonical" href="{target}">', text)
            self.assertIn(f'<meta http-equiv="refresh" content="0; url={target}">', text)
            self.assertIn(f'location.replace("{target}")', text)
            self.assertIn('<meta name="robots" content="noindex">', text)
            self.assertNotIn('googletagmanager', text)
            self.assertNotIn('gtag(', text)
            self.assertNotIn('G-ZJK92LK3XT', text)
            self.assertNotIn('adsbygoogle', text)
            self.assertNotIn('site-nav', text)
            self.assertNotIn('accessory dwelling', text.casefold())
            with self.assertRaises(builder.BuildError):
                builder.reject_removed_adu(relative, '<p>accessory dwelling</p>')
            builder.reject_removed_adu(relative, stub)

    def test_publish_replaces_a_full_page_and_writes_every_stub(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            full = root / 'jadus.html'
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(
                '<html><head>'
                '<link rel="canonical" href="https://sandiegoadubuilder.com/jadus.html">'
                '<script src="https://www.googletagmanager.com/gtag/js?id=G-ZJK92LK3XT"></script>'
                '</head><body><h1>Junior accessory dwelling units</h1>'
                + ('<p>Full article copy.</p>' * 40)
                + '</body></html>',
                encoding='utf-8',
            )
            with self.assertRaises(builder.BuildError):
                builder.reject_removed_adu('jadus.html', full.read_text(encoding='utf-8'))
            builder.publish_adu_redirects(root)
            for relative in builder.REMOVED_ADU_PATHS:
                written = (root / relative).read_text(encoding='utf-8')
                self.assertEqual(written, builder.adu_redirect_html(relative))
                self.assertNotIn('googletagmanager', written)
            builder.publish_adu_redirects(root)

    def test_sitemaps_homepage_and_menu_do_not_list_adu_urls(self):
        menu = site_nav.render(site_nav.build_menu(ROOT), '/')
        self.assertNotIn('sandiegoadubuilder', menu.casefold())
        self.assertNotIn('accessory dwelling', menu.casefold())
        for relative in builder.REMOVED_ADU_PATHS:
            self.assertNotIn(relative.casefold(), menu.casefold())
        for name in SCAN:
            text = (ROOT / name).read_text(encoding='utf-8').casefold()
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

    def test_builder_refuses_full_adu_pages(self):
        for relative in builder.REMOVED_ADU_PATHS:
            with self.assertRaises(builder.BuildError):
                builder.reject_removed_adu(relative, '<p>WNBA</p>')
            with self.assertRaises(builder.BuildError):
                builder.reject_removed_adu(relative, builder.adu_redirect_html(relative) + '<p>More</p>')
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

    def test_pages_workflow_keeps_the_stubs(self):
        workflow = (ROOT / '.github' / 'workflows' / 'fcb-wnba.yml').read_text(encoding='utf-8')
        self.assertIn('REMOVED_ADU_PATHS', workflow)
        self.assertIn('git add --', workflow)
        self.assertIn('git archive HEAD', workflow)
        self.assertIn('adu_redirect_html', workflow)
        self.assertIn('actions/deploy-pages@v4', workflow)
        self.assertIn('actions/upload-pages-artifact@v3', workflow)
        add_at = workflow.index("print('\\n'.join(sorted(b.REMOVED_ADU_PATHS)))")
        archive_at = workflow.index('git archive HEAD')
        self.assertLess(add_at, archive_at)
        self.assertIn('Pages artifact keeps', workflow)

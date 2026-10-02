"""SEO starter-guide rules: duplicates, orphans, titles, sitemaps, and static pages."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import build_players as builder
import internal_links as links
from test_build_players import P, setup

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://fullcourtbuckets.com'


def _profile(player_id, slug, first, last, stats=True):
    profile = copy.deepcopy(P)
    profile['slug'] = slug
    profile['player']['id'] = player_id
    profile['player']['first_name'] = first
    profile['player']['last_name'] = last
    profile['active_in_provider_feed'] = False
    profile['current_team'] = None
    if stats:
        profile['season_stats'][0]['player_id'] = player_id
    else:
        profile['season_stats'] = []
    return profile


def _write_player(root, profile, name):
    slug = profile['slug']
    (root / 'data/wnba/players' / f'{slug}.json').write_text(json.dumps(profile), encoding='utf-8')
    return {
        'id': profile['player']['id'],
        'slug': slug,
        'name': name,
        'active_in_provider_feed': False,
    }


class GeneratorRuleTests(unittest.TestCase):
    def test_titles_descriptions_and_thin_profiles(self):
        self.assertEqual(
            builder.player_title("A'ja Wilson"),
            "A'ja Wilson WNBA Stats & Profile | Full Court Buckets",
        )
        long_name = 'Darianna Littlepage-Buggs'
        titled = builder.player_title(long_name)
        self.assertIn('WNBA Stats & Profile', titled)
        self.assertLessEqual(len(titled), 70)
        huge = builder.player_title('X' * 40)
        self.assertLessEqual(len(huge), 70)
        self.assertNotIn('WNBA Stats & Profile', huge)
        clipped = builder.cap_description('alpha ' * 40)
        self.assertLessEqual(len(clipped), 155)
        self.assertFalse(clipped.endswith(' '))
        thin = _profile(9, 'thin-player', 'Thin', 'Player', stats=False)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertFalse(builder.player_indexable(thin, root))
            page = builder.profile_page(thin, root, menu=[])
            self.assertIn('content="noindex"', page)
            self.assertNotIn('Available coverage from 2008 onward.', page)
            self.assertIn('No season records are listed on this page yet.', page)
            faq = root / 'data/wnba/faq'
            faq.mkdir(parents=True)
            (faq / 'thin-player.json').write_text(json.dumps({
                'slug': 'thin-player',
                'items': [{'question': 'Who is this?', 'answer': 'A player with a curated note.'}],
            }), encoding='utf-8')
            self.assertTrue(builder.player_indexable(thin, root))
        slot = {
            'full_name': 'Minnesota Lynx',
            'conference': 'Western Conference',
            'players': [{'name': 'Example', 'slug': 'example'}] * 12,
        }
        standing = {'wins': 33, 'losses': 11, 'conferenceRank': 1, 'playoffSeed': 1}
        description = builder.team_description(slot, standing)
        self.assertGreaterEqual(len(description), 110)
        self.assertLessEqual(len(description), 155)
        self.assertNotIn('\u2014', description)

    def test_orphan_stub_recovers_the_id_slug_without_a_title(self):
        target = builder.orphan_player_target(
            'matilde-villa',
            '<title>Redirect</title><link rel="canonical" href="https://fullcourtbuckets.com/wnba/">',
            {},
            {'matilde-villa-270867'},
        )
        self.assertEqual(target, 'https://fullcourtbuckets.com/wnba/matilde-villa-270867/')
        hub = builder.orphan_player_target(
            'nadia-fingall',
            '<title>Redirect</title><link rel="canonical" href="https://fullcourtbuckets.com/wnba/">',
            {},
            {'matilde-villa-270867'},
        )
        self.assertEqual(hub, 'https://fullcourtbuckets.com/wnba/')

    def test_box_score_link_for_a_future_recap(self):
        html_text = '<article><p>Recap.</p><p class="brand-sign">Full Court Buckets</p></article>'
        updated = links.ensure_box_score(html_text, {'espnGameId': '401918017'})
        self.assertIn('https://www.espn.com/wnba/game/_/gameId/401918017', updated)
        self.assertIn('target="_blank" rel="noopener"', updated)
        self.assertLess(updated.index('Box score'), updated.index('brand-sign'))
        self.assertEqual(links.ensure_box_score(updated, {'espnGameId': '401918017'}), updated)

    def test_duplicate_orphan_and_sitemap_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup(root)
            data = root / 'data/wnba'
            index = json.loads((data / 'players-index.json').read_text(encoding='utf-8'))
            archive = _profile(99338, 'alicia-florez', 'Alicia', 'Florez')
            current = _profile(245094, 'alicia-florez-245094', 'Alicia', 'Florez')
            villa = _profile(270867, 'matilde-villa-270867', 'Matilde', 'Villa')
            thin = _profile(50, 'thin-player', 'Thin', 'Player', stats=False)
            index['players'] = [
                index['players'][0],
                _write_player(root, archive, 'Alicia Florez'),
                _write_player(root, current, 'Alicia Florez'),
                _write_player(root, villa, 'Matilde Villa'),
                _write_player(root, thin, 'Thin Player'),
            ]
            (data / 'players-index.json').write_text(json.dumps(index), encoding='utf-8')
            orphan = root / 'wnba' / 'matilde-villa'
            orphan.mkdir(parents=True)
            (orphan / 'index.html').write_text(
                '<title>Matilde Villa WNBA Stats &amp; Profile | Full Court Buckets</title>',
                encoding='utf-8',
            )
            unknown = root / 'wnba' / 'nadia-fingall'
            unknown.mkdir(parents=True)
            (unknown / 'index.html').write_text(
                '<title>Nadia Fingall WNBA Stats | Full Court Buckets</title>',
                encoding='utf-8',
            )
            builder.build(root)
            builder.build(root)
            stub = (root / 'wnba/alicia-florez/index.html').read_text(encoding='utf-8')
            self.assertIn('noindex', stub)
            self.assertIn('http-equiv="refresh"', stub)
            self.assertIn(f'{BASE}/wnba/alicia-florez-245094/', stub)
            self.assertIn('location.replace', stub)
            villa_stub = (root / 'wnba/matilde-villa/index.html').read_text(encoding='utf-8')
            self.assertIn(f'{BASE}/wnba/matilde-villa-270867/', villa_stub)
            self.assertIn('noindex', villa_stub)
            nadia = (root / 'wnba/nadia-fingall/index.html').read_text(encoding='utf-8')
            self.assertIn(f'{BASE}/wnba/', nadia)
            self.assertNotIn('matilde-villa-270867', nadia)
            directory = (root / 'wnba/index.html').read_text(encoding='utf-8')
            self.assertNotIn('href="/wnba/alicia-florez/"', directory)
            self.assertIn('href="/wnba/alicia-florez-245094/"', directory)
            thin_page = (root / 'wnba/thin-player/index.html').read_text(encoding='utf-8')
            self.assertIn('noindex', thin_page)
            titles = []
            for path in (root / 'wnba').iterdir():
                if not path.is_dir() or path.name in builder.SKIP_PLAYER_DIRS:
                    continue
                text = (path / 'index.html').read_text(encoding='utf-8')
                if not builder.page_indexable(text):
                    continue
                title = re.search(r'<title>(.*?)</title>', text).group(1)
                titles.append(title)
            self.assertEqual(len(titles), len(set(titles)))
            player_locs = set(re.findall(r'<loc>\s*([^<]+?)\s*</loc>', (root / 'player-sitemap.xml').read_text(encoding='utf-8')))
            page_locs = set(re.findall(r'<loc>\s*([^<]+?)\s*</loc>', (root / 'pages-sitemap.xml').read_text(encoding='utf-8')))
            site_locs = set(re.findall(r'<loc>\s*([^<]+?)\s*</loc>', (root / 'sitemap.xml').read_text(encoding='utf-8')))
            self.assertIn(f'{BASE}/wnba/alicia-florez-245094/', player_locs)
            self.assertIn(f'{BASE}/wnba/example-player/', player_locs)
            self.assertNotIn(f'{BASE}/wnba/alicia-florez/', site_locs)
            self.assertNotIn(f'{BASE}/wnba/matilde-villa/', site_locs)
            self.assertNotIn(f'{BASE}/wnba/nadia-fingall/', site_locs)
            self.assertNotIn(f'{BASE}/wnba/thin-player/', site_locs)
            self.assertNotIn(f'{BASE}/wnba/', player_locs)
            self.assertIn(f'{BASE}/', page_locs)
            self.assertIn(f'{BASE}/wnba/', page_locs)
            self.assertEqual(site_locs, player_locs | page_locs)
            for loc in site_locs:
                self.assertIn('<lastmod>', (root / 'sitemap.xml').read_text(encoding='utf-8'))
                self.assertTrue(loc.startswith(BASE))


class PublishedPageTests(unittest.TestCase):
    def test_static_pages_and_removed_scratch_files(self):
        self.assertFalse((ROOT / 'live-article-current.html').exists())
        self.assertFalse((ROOT / 'live-article-final-check.html').exists())
        home = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/"', home)
        self.assertIn('href="/favicon.svg"', home)
        self.assertNotIn('href="favicon.svg"', home)
        self.assertIn('"@type":"WebSite"', home)
        self.assertIn('"@type":"Organization"', home)
        self.assertIn('"sameAs":["https://www.tiktok.com/@fullcourtbuckets"]', home)
        self.assertIn('https://fullcourtbuckets.com/logo.png', home)
        self.assertIn('hello@fullcourtbuckets.com', home)
        self.assertIn('WebPage', home)
        self.assertIn('BreadcrumbList', home)
        description = re.search(r'name="description" content="([^"]*)"', home).group(1)
        self.assertGreaterEqual(len(description), 120)
        self.assertLessEqual(len(description), 155)
        about = (ROOT / 'about/index.html').read_text(encoding='utf-8')
        self.assertIn('AboutPage', about)
        self.assertIn('TODO: owner, add the editor', about)
        self.assertIn('Follow Full Court Buckets on TikTok at ', about)
        self.assertIn('href="https://www.tiktok.com/@fullcourtbuckets" target="_blank" rel="noopener me">@fullcourtbuckets</a>', about)
        self.assertIn('Wikimedia Commons', about)
        self.assertIn('AI-generated editorial illustration', about)
        self.assertNotIn('\u2014', about)
        contact = (ROOT / 'contact/index.html').read_text(encoding='utf-8')
        self.assertIn('ContactPage', contact)
        contact_desc = re.search(r'name="description" content="([^"]*)"', contact).group(1)
        self.assertGreaterEqual(len(contact_desc), 110)
        self.assertLessEqual(len(contact_desc), 155)
        terms = (ROOT / 'terms/index.html').read_text(encoding='utf-8')
        terms_desc = re.search(r'name="description" content="([^"]*)"', terms).group(1)
        self.assertGreaterEqual(len(terms_desc), 110)
        self.assertLessEqual(len(terms_desc), 155)
        for relative in ('privacy/index.html', 'terms/index.html', 'standings/index.html'):
            text = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn('WebPage', text, relative)
            self.assertIn('BreadcrumbList', text, relative)
        news = (ROOT / 'news/index.html').read_text(encoding='utf-8')
        news_desc = re.search(r'name="description" content="([^"]*)"', news).group(1)
        self.assertGreaterEqual(len(news_desc), 110)
        self.assertLessEqual(len(news_desc), 155)

    def test_published_players_teams_and_sitemaps(self):
        florez = (ROOT / 'wnba/alicia-florez/index.html').read_text(encoding='utf-8')
        self.assertIn('noindex', florez)
        self.assertIn('http-equiv="refresh"', florez)
        self.assertIn(f'{BASE}/wnba/alicia-florez-245094/', florez)
        villa = (ROOT / 'wnba/matilde-villa/index.html').read_text(encoding='utf-8')
        self.assertIn('noindex', villa)
        self.assertIn(f'{BASE}/wnba/matilde-villa-270867/', villa)
        standings = (ROOT / 'standings/index.html').read_text(encoding='utf-8')
        self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/standings/"', standings)
        self.assertIn('href="https://www.espn.com/wnba/standings" target="_blank" rel="noopener"', standings)
        body = standings.split('id="standingsBody"', 1)[1].split('</tbody>', 1)[0]
        names = re.findall(r'class="team-name"[^>]*>([^<]+)', body)
        self.assertEqual(len(names), 15)
        self.assertEqual(len(set(names)), 15)
        self.assertEqual(names[:8], [
            'Minnesota Lynx', 'Golden State Valkyries', 'Las Vegas Aces', 'Atlanta Dream',
            'Washington Mystics', 'Indiana Fever', 'Dallas Wings', 'New York Liberty',
        ])
        index = json.loads((ROOT / 'data/wnba/players-index.json').read_text(encoding='utf-8'))
        titles = {}
        for entry in index['players']:
            text = (ROOT / 'wnba' / entry['slug'] / 'index.html').read_text(encoding='utf-8')
            if not builder.page_indexable(text):
                continue
            title = re.search(r'<title>(.*?)</title>', text).group(1)
            self.assertNotIn(title, titles.values())
            titles[entry['slug']] = title
            description = re.search(r'name="description" content="([^"]*)"', text).group(1)
            self.assertLessEqual(len(description), 155, entry['slug'])
            self.assertLessEqual(len(title), 81, entry['slug'])
        darianna = (ROOT / 'wnba/darianna-littlepage-buggs/index.html').read_text(encoding='utf-8')
        self.assertNotIn('Available coverage from 2008 onward.', darianna)
        self.assertIn('index,follow', darianna)
        expansion = (ROOT / 'news/wnba-expansion-teams/index.html').read_text(encoding='utf-8')
        self.assertNotIn('site.api.espn.com', expansion)
        self.assertIn('https://www.espn.com/wnba/standings', expansion)
        self.assertIn('https://www.espn.com/wnba/game/_/gameId/401856891', expansion)
        recap = (ROOT / 'news/liberty-lynx-game-2-recap/index.html').read_text(encoding='utf-8')
        self.assertIn('https://www.espn.com/wnba/game/_/gameId/401918017', recap)
        self.assertIn('target="_blank" rel="noopener"', recap)
        meta = re.search(r'name="description" content="([^"]*)"', recap).group(1)
        self.assertLessEqual(len(meta), 155)
        player_locs = set(re.findall(r'<loc>\s*([^<]+?)\s*</loc>', (ROOT / 'player-sitemap.xml').read_text(encoding='utf-8')))
        page_locs = set(re.findall(r'<loc>\s*([^<]+?)\s*</loc>', (ROOT / 'pages-sitemap.xml').read_text(encoding='utf-8')))
        site_locs = set(re.findall(r'<loc>\s*([^<]+?)\s*</loc>', (ROOT / 'sitemap.xml').read_text(encoding='utf-8')))
        self.assertEqual(site_locs, player_locs | page_locs)
        self.assertNotIn(f'{BASE}/wnba/alicia-florez/', site_locs)
        self.assertNotIn(f'{BASE}/wnba/matilde-villa/', site_locs)
        self.assertIn(f'{BASE}/wnba/alicia-florez-245094/', player_locs)
        self.assertIn(f'{BASE}/', page_locs)
        self.assertIn(f'{BASE}/standings/', page_locs)
        self.assertNotIn(f'{BASE}/wnba/', player_locs)
        blob = (ROOT / 'sitemap.xml').read_text(encoding='utf-8')
        for loc in site_locs:
            self.assertIn(f'<loc>{loc}</loc>', blob)
            block = blob.split(f'<loc>{loc}</loc>', 1)[1].split('</url>', 1)[0]
            self.assertIn('<lastmod>', block, loc)
            path = loc.removeprefix(BASE)
            page = ROOT / 'index.html' if path in ('', '/') else ROOT / path.strip('/') / 'index.html'
            self.assertTrue(builder.page_indexable(page.read_text(encoding='utf-8')), loc)
        for entry in index['players']:
            loc = f'{BASE}/wnba/{entry["slug"]}/'
            text = (ROOT / 'wnba' / entry['slug'] / 'index.html').read_text(encoding='utf-8')
            self.assertEqual(builder.page_indexable(text), loc in player_locs, entry['slug'])
        fever = (ROOT / 'wnba/teams/indiana-fever/index.html').read_text(encoding='utf-8')
        fever_desc = re.search(r'name="description" content="([^"]*)"', fever).group(1)
        self.assertGreaterEqual(len(fever_desc), 110)
        self.assertLessEqual(len(fever_desc), 155)
        self.assertIn('Latest stories', fever)
        self.assertIn('href="/news/fever-aces-game-2-recap/"', fever)
        self.assertIn('<th scope="col">PPG</th>', fever)


if __name__ == '__main__':
    unittest.main()

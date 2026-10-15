"""Team pages list FCB stories that name the club or a current player."""
import json
from pathlib import Path
import tempfile
import unittest

import build_players as builder
import internal_links as links
import team_coverage
import team_season

ROOT = Path(__file__).resolve().parents[1]


def _article(slug, title, date, body, teams=None, description='', head=''):
    listed = ''
    return {
        'slug': slug,
        'url': f'/news/{slug}/',
        'title': title,
        'description': description,
        'date': date,
        'teams': teams or [],
        '_body': body,
        '_head': head,
    }


def _write_site(root: Path, articles: list, slots: list) -> None:
    players = []
    for slot in slots:
        for player in slot['players']:
            players.append({
                'id': player['id'],
                'slug': player['slug'],
                'name': player['name'],
                'active_in_provider_feed': True,
                'current_team': {
                    'id': slot['id'],
                    'full_name': slot['full_name'],
                    'name': slot['name'],
                },
            })
    data = root / 'data' / 'wnba'
    data.mkdir(parents=True)
    (data / 'players-index.json').write_text(json.dumps({'players': players}), encoding='utf-8')
    stored = []
    for article in articles:
        stored.append({key: value for key, value in article.items() if not key.startswith('_')})
        folder = root / 'news' / article['slug']
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'index.html').write_text(
            '<!doctype html><html><head><meta charset="utf-8">'
            + article.get('_head', '')
            + '</head><body><header><nav>'
            '<a href="/wnba/teams/atlanta-dream/">Atlanta Dream</a>'
            '<a href="/wnba/angel-reese/">Angel Reese</a>'
            '<a href="/wnba/allisha-gray/">Allisha Gray</a>'
            '</nav></header><article class="article"><h1>'
            + article['title']
            + '</h1>'
            + article.get('_body', '')
            + '</article><footer><p>Footer</p></footer></body></html>',
            encoding='utf-8',
        )
    (root / 'articles.json').write_text(json.dumps(stored), encoding='utf-8')
    for slot in slots:
        folder = root / 'wnba' / 'teams' / slot['slug']
        folder.mkdir(parents=True)
        (folder / 'index.html').write_text(
            '<main><section class="directory-header"><h1>' + slot['full_name'] + '</h1></section>'
            '<p><a class="inline-link" href="/wnba/teams/">All teams</a></p>'
            '<p><a class="inline-link" href="/wnba/">All players</a></p></main>',
            encoding='utf-8',
        )


DREAM = {
    'id': 1,
    'full_name': 'Atlanta Dream',
    'name': 'Dream',
    'slug': 'atlanta-dream',
    'conference': 'Eastern Conference',
    'players': [
        {'id': 10, 'slug': 'allisha-gray', 'name': 'Allisha Gray'},
        {'id': 11, 'slug': 'angel-reese', 'name': 'Angel Reese'},
        {'id': 12, 'slug': 'aja-wilson', 'name': "A'ja Wilson"},
    ],
}
ACES = {
    'id': 2,
    'full_name': 'Las Vegas Aces',
    'name': 'Aces',
    'slug': 'las-vegas-aces',
    'conference': 'Western Conference',
    'players': [
        {'id': 20, 'slug': 'chelsea-gray', 'name': 'Chelsea Gray'},
        {'id': 21, 'slug': 'jackie-young', 'name': 'Jackie Young'},
    ],
}
FIRE = {
    'id': 3,
    'full_name': 'Portland Fire',
    'name': 'Fire',
    'slug': 'portland-fire',
    'conference': 'Western Conference',
    'players': [{'id': 30, 'slug': 'serah-williams', 'name': 'Serah Williams'}],
}
SKY = {
    'id': 4,
    'full_name': 'Chicago Sky',
    'name': 'Sky',
    'slug': 'chicago-sky',
    'conference': 'Eastern Conference',
    'players': [{'id': 40, 'slug': 'elizabeth-williams', 'name': 'Elizabeth Williams'}],
}


def _slugs(root, slot):
    return [article['slug'] for article in team_coverage.matching_articles(root, slot)]


class MatchTests(unittest.TestCase):
    def test_full_name_alias_player_and_link_match_but_surnames_do_not(self):
        articles = [
            _article('full-name', 'Notes', '2026-10-01', '<p>The Atlanta Dream won.</p>'),
            _article('the-nick', 'Notes', '2026-10-02', '<p>The Dream won the night.</p>'),
            _article('bare-nick', 'Dream sweep the Liberty', '2026-10-03', '<p>A recap.</p>'),
            _article('dream-team', 'Tryouts', '2026-10-04', '<p>the Dream Team meets Tuesday.</p>'),
            _article('city-only', 'Concert', '2026-10-05', '<p>Atlanta hosted a concert.</p>'),
            _article('surname', 'Box', '2026-10-06', '<p>Gray scored 20 and Young added 10.</p>'),
            _article('full-player', 'Box', '2026-10-07', '<p>Allisha Gray scored 20.</p>'),
            _article('possessive', 'Box', '2026-10-08', "<p>Allisha Gray's free throws closed it.</p>"),
            _article('link-only', 'Box', '2026-10-09', '<p><a href="/wnba/allisha-gray/">Gray</a> scored 20.</p>'),
            _article('young-word', 'Kids', '2026-10-10', '<p>The young players caught fire under the sun.</p>'),
            _article('jackie', 'Box', '2026-10-11', '<p>Jackie Young scored 18 for the Aces.</p>'),
            _article('nav-only', 'Sunday notes', '2026-10-12', '<p>Nothing about a club.</p>'),
            _article('aside-only', 'Aside', '2026-10-13', '<p>No names.</p><aside class="article-end"><a href="/wnba/angel-reese/">Angel Reese</a><a href="/news/other/">Dream win again</a></aside>'),
            _article('head-only', 'Weather', '2026-10-14', '<p>Clear skies.</p>', head='<script type="application/ld+json">{"headline":"Atlanta Dream"}</script>'),
            _article('slug-only', 'Schedule', '2026-10-15', '<p>Four games are set.</p>', teams=['atlanta-dream']),
            _article('city-anchor', 'Sweep', '2026-10-16', '<p>They swept <a href="/wnba/teams/las-vegas-aces/">Las Vegas</a>.</p>'),
            _article('caught-fire', 'Run', '2026-10-17', '<p>Then the Valkyries caught fire.</p>'),
            _article('the-fire', 'Home', '2026-10-18', '<p>The Fire won at home.</p>'),
            _article('apostrophe', 'Night', '2026-10-19', '<p>A’ja Wilson scored 30.</p>'),
            _article('stripped', 'Night', '2026-10-20', '<p>Aja Wilson scored 30.</p>'),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_site(root, articles, [DREAM, ACES, FIRE])
            dream = _slugs(root, DREAM)
            aces = _slugs(root, ACES)
            fire = _slugs(root, FIRE)
        self.assertIn('full-name', dream)
        self.assertIn('the-nick', dream)
        self.assertNotIn('bare-nick', dream)
        self.assertNotIn('dream-team', dream)
        self.assertNotIn('city-only', dream)
        self.assertNotIn('surname', dream)
        self.assertNotIn('surname', aces)
        self.assertIn('full-player', dream)
        self.assertIn('possessive', dream)
        self.assertIn('link-only', dream)
        self.assertNotIn('young-word', aces)
        self.assertNotIn('young-word', fire)
        self.assertIn('jackie', aces)
        self.assertNotIn('nav-only', dream)
        self.assertNotIn('aside-only', dream)
        self.assertNotIn('head-only', dream)
        self.assertIn('slug-only', dream)
        self.assertIn('city-anchor', aces)
        self.assertNotIn('city-anchor', dream)
        self.assertNotIn('caught-fire', fire)
        self.assertIn('the-fire', fire)
        self.assertIn('apostrophe', dream)
        self.assertIn('stripped', dream)

    def test_newest_first_deduped_dated_in_pacific_time(self):
        articles = [
            _article('older', 'Older title', '2026-10-01', '<p>The Atlanta Dream won.</p>'),
            _article('newer', 'Newer title', '2026-10-14', '<p>The Atlanta Dream won again.</p>'),
            _article('same', 'First listing', '2026-10-14', '<p>The Atlanta Dream won again.</p>'),
            _article('same', 'Second listing', '2026-10-01', '<p>The Atlanta Dream won.</p>'),
            _article('utc-evening', 'Late UTC is still the 13th', '2026-10-14T06:30:00Z', '<p>The Atlanta Dream won.</p>'),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_site(root, articles, [DREAM])
            found = team_coverage.matching_articles(root, DREAM)
            html = team_coverage.section_html(root, DREAM)
        self.assertEqual([article['slug'] for article in found], ['newer', 'same', 'utc-evening', 'older'])
        self.assertEqual([article['title'] for article in found if article['slug'] == 'same'], ['First listing'])
        self.assertNotIn('Second listing', html)
        self.assertIn('>Newer title</a><time datetime="2026-10-14">October 14, 2026 PT</time>', html)
        self.assertIn('datetime="2026-10-13">October 13, 2026 PT</time>', html)
        self.assertLess(html.find('Newer title'), html.find('Late UTC'))
        self.assertLess(html.find('Late UTC'), html.find('Older title'))
        self.assertNotIn('target="_blank"', html)
        self.assertNotIn('\u2014', html)
        self.assertIn('>Full Court Buckets coverage of the Atlanta Dream</h2>', html)
        self.assertNotIn('Coverage Of', html)

    def test_long_list_hides_the_tail_behind_more_and_empty_stays_hidden(self):
        articles = [
            _article(f'game-{number}', f'Game {number}', f'2026-01-{number:02d}', '<p>The Aces won.</p>')
            for number in range(1, 22)
        ]
        articles.append(_article('unrelated', 'Weather', '2026-02-01', '<p>Clear skies.</p>'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_site(root, articles, [ACES, SKY])
            html = team_coverage.section_html(root, ACES)
            hidden = team_coverage.section_html(root, SKY)
        self.assertEqual(hidden, '')
        visible, extra = html.split('<details class="team-coverage-more">', 1)
        self.assertEqual(visible.count('<li>'), team_coverage.VISIBLE_LIMIT)
        self.assertIn('<summary>More</summary>', extra)
        self.assertEqual(extra.count('<li>'), 1)
        self.assertIn('>Game 21</a>', visible)
        self.assertNotIn('>Game 1</a>', visible)
        self.assertIn('>Game 1</a>', extra)
        self.assertNotIn('id="team-coverage"', hidden)

    def test_a_trade_moves_the_story_with_the_player(self):
        articles = [_article('reese-night', 'Twenty points', '2026-10-08', '<p>Angel Reese had 20.</p>')]
        moved = dict(SKY)
        moved['players'] = list(SKY['players']) + [{'id': 11, 'slug': 'angel-reese', 'name': 'Angel Reese'}]
        dream_without = dict(DREAM)
        dream_without['players'] = [player for player in DREAM['players'] if player['slug'] != 'angel-reese']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_site(root, articles, [dream_without, moved])
            self.assertEqual(_slugs(root, dream_without), [])
            self.assertEqual(_slugs(root, moved), ['reese-night'])

    def test_section_sits_at_the_bottom_and_refresh_is_idempotent(self):
        articles = [_article('dream-win', 'Dream take it', '2026-10-02', '<p>The Atlanta Dream won.</p>')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_site(root, articles, [DREAM])
            page = builder.team_page(DREAM, include_standings=False, menu=[], root=root)
            main = page.split('<main', 1)[1].split('</main>', 1)[0]
            self.assertLess(main.find('>All players</a>'), main.find('id="team-coverage"'))
            self.assertLess(main.find('id="team-news"'), main.find('id="team-coverage"'))
            self.assertEqual(team_coverage.refresh(root), 1)
            written = (root / 'wnba' / 'teams' / 'atlanta-dream' / 'index.html').read_text(encoding='utf-8')
            self.assertIn('id="team-coverage"', written)
            self.assertEqual(team_coverage.refresh(root), 0)
            again = team_coverage.apply_html(written, root, DREAM)
            self.assertEqual(again, written)
            stub = root / 'wnba' / 'teams' / 'fire' / 'index.html'
            stub.parent.mkdir(parents=True)
            stub.write_text('<meta http-equiv="refresh" content="0;url=/wnba/teams/portland-fire/">', encoding='utf-8')
            self.assertEqual(team_coverage.refresh(root), 0)
            self.assertNotIn('team-coverage', stub.read_text(encoding='utf-8'))


class PublishedPageTests(unittest.TestCase):
    def test_every_current_team_page_matches_the_generator(self):
        index = json.loads((ROOT / 'data/wnba/players-index.json').read_text(encoding='utf-8'))
        linking = links.catalog_from_index(index)
        corpus = team_coverage.load_corpus(ROOT)
        counts = {}
        for slot in sorted(linking['by_id'].values(), key=lambda item: item['slug']):
            expected = team_coverage.section_html(ROOT, slot, linking, corpus)
            page = (ROOT / 'wnba' / 'teams' / slot['slug'] / 'index.html').read_text(encoding='utf-8')
            rows = team_coverage.matching_articles(ROOT, slot, linking, corpus)
            counts[slot['slug']] = len(rows)
            main = page.split('<main', 1)[1].split('</main>', 1)[0]
            if not expected:
                self.assertNotIn('id="team-coverage"', page, slot['slug'])
                continue
            self.assertIn(expected, page, slot['slug'])
            self.assertLess(main.find('>All players</a>'), main.find('id="team-coverage"'), slot['slug'])
            self.assertLess(main.find('id="roster"'), main.find('id="team-coverage"'), slot['slug'])
            self.assertNotIn('target="_blank"', expected, slot['slug'])
            self.assertNotIn('\u2014', expected, slot['slug'])
            dates = [part.split('"', 1)[0] for part in expected.split('datetime="')[1:]]
            self.assertEqual(dates, sorted(dates, reverse=True), slot['slug'])
            self.assertLessEqual(expected.split('<details', 1)[0].count('<li>'), team_coverage.VISIBLE_LIMIT)
            if len(rows) > team_coverage.VISIBLE_LIMIT:
                self.assertIn('<summary>More</summary>', expected, slot['slug'])
            else:
                self.assertNotIn('<summary>More</summary>', expected, slot['slug'])
        for slug in ('fire', 'tempo'):
            stub = (ROOT / 'wnba' / 'teams' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertNotIn('id="team-coverage"', stub)
        self.assertGreater(counts['atlanta-dream'], 0)
        self.assertEqual(len(counts), len(linking['by_id']))

    def test_patch_and_article_builds_keep_the_section(self):
        players = (ROOT / 'automation' / 'build_players.py').read_text(encoding='utf-8')
        tracker = (ROOT / 'automation' / 'build_finals_ratings_tracker.py').read_text(encoding='utf-8')
        season = (ROOT / 'automation' / 'team_season.py').read_text(encoding='utf-8')
        css = (ROOT / 'automation' / 'players.css').read_text(encoding='utf-8')
        published = (ROOT / 'wnba' / 'assets' / 'players.css').read_text(encoding='utf-8')
        self.assertIn('team_coverage.section_html', players)
        self.assertIn('team_coverage.refresh', players)
        self.assertIn('team_coverage.refresh', tracker)
        self.assertIn('team_coverage.apply_html', season)
        self.assertIn('#team-coverage', css)
        self.assertIn('@media(max-width:480px){#team-coverage', css)
        self.assertEqual(css, published)
        index = json.loads((ROOT / 'data/wnba/players-index.json').read_text(encoding='utf-8'))
        linking = links.catalog_from_index(index)
        slot = next(item for item in linking['by_id'].values() if item['slug'] == 'atlanta-dream')
        standing = builder.load_standings_by_name(ROOT).get(slot['full_name'])
        page = (ROOT / 'wnba' / 'teams' / 'atlanta-dream' / 'index.html').read_text(encoding='utf-8')
        updated = team_season.patch_team_html(page, ROOT, slot, standing)
        self.assertIn('id="team-coverage"', updated)
        self.assertIn('Full Court Buckets coverage of the Atlanta Dream', updated)
        self.assertLess(updated.find('>All players</a>'), updated.find('id="team-coverage"'))


if __name__ == '__main__':
    unittest.main()

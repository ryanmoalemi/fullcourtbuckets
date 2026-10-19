"""Homepage rail is generated from scoreboard data, not slogan copy."""
import datetime as dt
import json
import re
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import offline_tests
import homepage_rail as rail
import internal_links as links

offline_tests.install()

ROOT = Path(__file__).resolve().parents[1]
PT = ZoneInfo('America/Los_Angeles')
NOW = dt.datetime(2026, 10, 2, 12, 0, tzinfo=PT)


def _newest_game_recaps(articles, limit):
    """One href per ESPN game: the newest article wins, equal dates keep the first."""
    best = {}
    for article in articles or []:
        if not isinstance(article, dict):
            continue
        game_id = str(article.get('espnGameId') or '').strip()
        slug = str(article.get('slug') or '').strip()
        if not game_id or not slug:
            continue
        href = str(article.get('url') or f'/news/{slug}/')
        if not href.startswith('/'):
            href = f'/news/{slug}/'
        date = str(article.get('date') or '')
        current = best.get(game_id)
        if current is None or date > current[0]:
            best[game_id] = (date, href, slug)
    ranked = sorted(best.values(), key=lambda row: row[0], reverse=True)
    return [(href, slug) for _date, href, slug in ranked[:limit]]


def _team(team_id, nick, abbr, score, home):
    return {
        'id': str(team_id),
        'homeAway': 'home' if home else 'away',
        'score': str(score),
        'team': {'id': str(team_id), 'abbreviation': abbr, 'shortDisplayName': nick, 'displayName': nick},
    }


def _event(game_id, when, state, teams, summary='', completed=False, wins=None, series_type='playoff', detail='', short=''):
    competitors = []
    for team in teams:
        competitors.append({'id': team['team']['id'], 'wins': (wins or {}).get(team['team']['id'], 0)})
    return {
        'id': str(game_id),
        'date': when,
        'season': {'type': 3, 'slug': 'post-season'},
        'competitions': [{
            'status': {'type': {
                'state': state,
                'name': 'STATUS_FINAL' if state == 'post' else 'STATUS_SCHEDULED',
                'detail': detail,
                'shortDetail': short or detail,
                'description': 'Final' if state == 'post' else 'Scheduled',
            }},
            'competitors': teams,
            'series': {
                'type': series_type,
                'summary': summary,
                'completed': completed,
                'competitors': competitors,
            },
        }],
    }


def _standings():
    rows = []
    west = [('Minnesota Lynx', 33, 11), ('Golden State Valkyries', 32, 12), ('Las Vegas Aces', 31, 13), ('Dallas Wings', 18, 26), ('Seattle Storm', 16, 28)]
    east = [('Atlanta Dream', 30, 14), ('Washington Mystics', 28, 16), ('New York Liberty', 27, 17), ('Indiana Fever', 24, 20), ('Chicago Sky', 10, 34)]
    rank = 1
    for conference, teams in (('Western', west), ('Eastern', east)):
        for index, (name, wins, losses) in enumerate(teams, start=1):
            rows.append({
                'rank': rank,
                'name': name,
                'conference': conference,
                'conferenceRank': index,
                'wins': wins,
                'losses': losses,
            })
            rank += 1
    return {'teams': rows}


class HomepageRailTests(unittest.TestCase):
    def test_series_status_next_game_and_recap_link(self):
        events = [
            rail.parse_event(_event(
                '401918022', '2026-10-02T01:00:00Z', 'post',
                [_team(17, 'Aces', 'LV', 94, True), _team(5, 'Fever', 'IND', 83, False)],
                summary='LV leads series 2-1', completed=False,
                wins={'17': 2, '5': 1},
                detail='Final', short='Final',
            )),
            rail.parse_event(_event(
                '401918099', '2026-10-03T02:00:00Z', 'pre',
                [_team(17, 'Aces', 'LV', 0, True), _team(5, 'Fever', 'IND', 0, False)],
                summary='LV leads series 2-1', completed=False,
                wins={'17': 2, '5': 1},
                detail='Fri, October 2nd at 7:00 PM EDT', short='10/2 - 7:00 PM EDT',
            )),
            rail.parse_event(_event(
                '401918016', '2026-09-28T01:00:00Z', 'post',
                [_team(129689, 'Valkyries', 'GS', 104, True), _team(3, 'Wings', 'DAL', 80, False)],
                summary='GS leads series 1-0', completed=False,
                wins={'129689': 1, '3': 0},
                detail='Final', short='Final',
            )),
            rail.parse_event(_event(
                '9', '2026-10-04T04:00:00Z', 'pre',
                [_team(-1, 'TBD', 'TBD', 0, True), _team(-2, 'TBD', 'TBD', 0, False)],
                summary='Series starts 10/4', completed=False,
                wins={'-1': 0, '-2': 0},
                detail='10/4 - TBD', short='TBD',
            )),
        ]
        articles = [{
            'slug': 'fever-aces-game-3-recap',
            'url': '/news/fever-aces-game-3-recap/',
            'date': '2026-10-01',
            'espnGameId': '401918022',
        }, {
            'slug': 'older-same-game',
            'url': '/news/older-same-game/',
            'date': '2026-09-01',
            'espnGameId': '401918022',
        }]
        html_text = rail.render_rail(events, articles, _standings(), now=NOW)
        self.assertIn('>Playoff series<', html_text)
        self.assertIn('Aces lead Fever 2-1', html_text)
        self.assertIn('Next: Fri, Oct 2, 7:00 p.m. PT', html_text)
        self.assertNotIn('espn.com', html_text)  # score/next links stay on FCB (Oct 19, 2026)
        self.assertIn('>Latest scores<', html_text)
        self.assertIn('href="/news/fever-aces-game-3-recap/">Aces 94, Fever 83</a>', html_text)
        self.assertNotIn('href="/news/fever-aces-game-3-recap/" target="_blank"', html_text)
        self.assertIn('<li>Valkyries 104, Wings 80<p', html_text)  # no FCB page: unlinked
        self.assertNotIn('>TBD<', html_text)
        self.assertNotIn('Final standings', html_text)
        self.assertNotIn('\u2014', html_text)
        for slogan in rail.SLOGANS:
            self.assertNotIn(slogan, html_text)

    def test_completed_series_has_no_next_game(self):
        events = [rail.parse_event(_event(
            '401918022', '2026-10-02T01:00:00Z', 'post',
            [_team(17, 'Aces', 'LV', 94, True), _team(5, 'Fever', 'IND', 83, False)],
            summary='LV wins series 2-1', completed=True,
            wins={'17': 2, '5': 1},
            detail='Final', short='Final',
        ))]
        html_text = rail.render_rail(events, [], _standings(), now=NOW)
        self.assertIn('Aces beat Fever 2-1', html_text)
        self.assertNotIn('Next:', html_text)
        self.assertNotIn('lead Fever', html_text)

    def test_tbd_tip_does_not_invent_a_clock_time(self):
        events = [rail.parse_event(_event(
            '401918295', '2026-10-04T04:00:00Z', 'pre',
            [_team(20, 'Dream', 'ATL', 0, True), _team(9, 'Liberty', 'NY', 0, False)],
            summary='Series starts 10/4', completed=False,
            wins={'20': 0, '9': 0},
            detail='10/4 - TBD', short='TBD',
        ))]
        html_text = rail.render_rail(events, [], _standings(), now=NOW)
        self.assertIn('Liberty at Dream', html_text)
        self.assertIn('Next: Oct 4, time TBD', html_text)
        self.assertNotIn('p.m.', html_text)
        self.assertNotIn('a.m.', html_text)

    def test_overtime_final_is_labeled(self):
        event = _event(
            '401918020', '2026-10-01T01:00:00Z', 'post',
            [_team(3, 'Wings', 'DAL', 90, True), _team(129689, 'Valkyries', 'GS', 88, False)],
            completed=False, wins={'3': 1, '129689': 1},
            detail='Final/OT', short='Final/OT',
        )
        event['competitions'][0]['status']['type']['description'] = 'Final/OT'
        parsed = rail.parse_event(event)
        self.assertTrue(parsed['ot'])
        html_text = rail.render_rail([parsed], [], _standings(), now=NOW)
        self.assertIn('Wings 90, Valkyries 88 OT', html_text)

    def test_offseason_shows_top_four_per_conference(self):
        old = rail.parse_event(_event(
            '1', '2026-08-01T01:00:00Z', 'post',
            [_team(17, 'Aces', 'LV', 80, True), _team(5, 'Fever', 'IND', 70, False)],
            series_type='', completed=True, wins={'17': 1, '5': 0},
            detail='Final', short='Final',
        ))
        html_text = rail.render_rail([old], [], _standings(), now=NOW)
        self.assertIn('>Final standings<', html_text)
        self.assertIn('href="/standings/">1. Dream 30-14</a>', html_text)
        self.assertIn('href="/standings/">4. Fever 24-20</a>', html_text)
        self.assertIn('href="/standings/">1. Lynx 33-11</a>', html_text)
        self.assertIn('href="/standings/">4. Wings 18-26</a>', html_text)
        self.assertNotIn('Sky', html_text)
        self.assertNotIn('Storm', html_text)
        self.assertNotIn('>Playoff series<', html_text)
        self.assertNotIn('>Latest scores<', html_text)
        self.assertNotIn('target="_blank"', html_text)
        self.assertIn('<h3 class="rail-conf">Eastern</h3>', html_text)
        eastern = html_text.split('Eastern', 1)[1].split('Western', 1)[0]
        self.assertLess(eastern.find('Dream'), eastern.find('Fever'))

    def test_apply_homepage_replaces_slogans_and_keeps_the_photo(self):
        page = (
            '<section class="feature-grid" id="latest">'
            '<a class="feature feature-link" id="featured-story" href="/news/old/">'
            '<img class="feature-photo" id="featured-image" src="/images/articles/keep.jpg" alt="Keep"'
            '<div class="feature-content"><h1 id="featured-title">Old</h1>'
            '<p id="featured-dek">Old dek</p><div class="meta" id="featured-meta">Old</div></div></a>'
            '<aside class="rail"><div class="rail-card"><h2>WNBA News. Given to You Straight.</h2></div></aside>'
            '</section><div class="story-list" id="older-stories"></div>'
        )
        articles = [{
            'slug': 'keep',
            'url': '/news/keep/',
            'title': 'Kept',
            'description': 'Dek',
            'category': 'WNBA',
            'date': '2026-10-01',
            'image': '/images/articles/keep.jpg',
            'imageAlt': 'Keep',
        }]
        fresh = rail.render_rail([], [], _standings(), now=NOW)
        updated = links.apply_homepage(page, articles, fresh)
        self.assertIn('class="article-card" id="featured-story"', updated)
        self.assertIn('class="article-visual"', updated)
        self.assertIn('src="/images/articles/keep.jpg"', updated)
        self.assertIn('object-position:center 20%', updated)
        self.assertIn('>Kept</h3>', updated)
        self.assertNotIn('feature-credit', updated)
        self.assertNotIn('id="featured-image"', updated)
        self.assertIn('src="/images/articles/keep.jpg"', updated)
        self.assertIn('>Final standings<', updated)
        self.assertNotIn('Given to You Straight', updated)
        kept = links.apply_homepage(page, articles, None)
        self.assertIn('Given to You Straight', kept)

    def test_ticker_uses_the_finals_schedule_when_no_result_is_newer(self):
        now = dt.datetime(2026, 10, 15, 12, 0, tzinfo=PT)
        articles = [
            {'slug': '2026-wnba-finals-ratings-tracker', 'title': 'Four games are set', 'date': '2026-10-14'},
            {
                'slug': 'aces-valkyries-semis-game-2-recap',
                'title': 'Burton from 28. Valkyries 83, Aces 81.',
                'date': '2026-10-07',
                'espnGameId': '401918298',
            },
        ]
        item = links.choose_ticker(articles, now)
        self.assertEqual(
            item['text'],
            'WNBA Finals Game 1: Dream at Valkyries, Sat Oct 17, 12:30 PM PT, NBC/Peacock',
        )
        self.assertGreaterEqual(item['date'], articles[0]['date'])

    def test_ticker_uses_a_newer_game_result(self):
        now = dt.datetime(2026, 10, 18, 18, 0, tzinfo=PT)
        articles = [{
            'slug': 'finals-game-1-recap',
            'title': 'Dream beat Valkyries 90-80',
            'date': '2026-10-18',
            'espnGameId': '401918305',
        }]
        item = links.choose_ticker(articles, now)
        self.assertEqual(item['text'], 'Dream beat Valkyries 90-80')
        self.assertEqual(item['date'], '2026-10-18')

    def test_ticker_hides_when_the_newest_item_is_older_than_48_hours(self):
        now = dt.datetime(2026, 10, 28, 15, 0, tzinfo=PT)
        articles = [{
            'slug': 'old-recap',
            'title': 'Burton from 28. Valkyries 83, Aces 81.',
            'date': '2026-10-07',
            'espnGameId': '401918298',
        }]
        self.assertIsNone(links.choose_ticker(articles, now))

    def test_published_ticker_is_not_older_than_the_newest_article(self):
        home = (ROOT / 'index.html').read_text(encoding='utf-8')
        articles = json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
        newest = max(article['date'] for article in articles)
        match = re.search(r'<div class="ticker[^"]*"[^>]*data-item-date="(\d{4}-\d{2}-\d{2})"', home)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(match.group(1), newest)
        self.assertNotIn('Burton from 28', home)
        self.assertIn('WNBA Finals Game 2: Dream at Valkyries, Mon Oct 19, 2026, 5 p.m. PT, Chase Center. Valkyries lead 1-0.', home)
        self.assertNotIn('tonight', home.split('class="ticker', 1)[1].split('</div></div></div>', 1)[0].lower())
        featured = home.split('id="latest"', 1)[1].split('id="home-rail"', 1)[0]
        self.assertIn('class="article-card" id="featured-story"', featured)
        self.assertIn('class="article-visual"', featured)
        self.assertIn('class="article-copy"', featured)
        self.assertNotIn('feature-credit', featured)
        self.assertNotIn('feature-photo', featured)
        self.assertNotIn('is-card', featured)
        style = home.split('</style>', 1)[0]
        self.assertIn('.article-card{display:grid;grid-template-columns:46% 54%;min-height:290px;', style)
        self.assertIn('.article-visual img{width:100%;height:100%;object-fit:cover;', style)
        self.assertIn('.article-card{grid-template-columns:1fr}.article-visual{min-height:210px}', style)
        self.assertNotIn('.feature-photo.is-card', style)

    def test_published_homepage_has_no_slogan_column(self):
        home = (ROOT / 'index.html').read_text(encoding='utf-8')
        rail_html = home.split('id="home-rail"', 1)[1].split('</aside>', 1)[0]
        for slogan in rail.SLOGANS:
            self.assertNotIn(slogan, home)
        self.assertNotIn('rail-card', home)
        self.assertNotIn('\u2014', rail_html)
        self.assertIn('>Playoff series<', rail_html)
        self.assertIn('>Latest scores<', rail_html)
        # Completed series roll off the 14-day scoreboard window, so check the form
        # of the finished-series lines instead of one fixed first-round result.
        self.assertRegex(rail_html, r'<li><p class="rail-status">[A-Z][A-Za-z ]+ beat [A-Z][A-Za-z ]+ \d-\d</p>')
        scores = rail_html.split('id="latest-scores"', 1)[1].split('</section>', 1)[0]
        score_rows = scores.count('<li>')
        self.assertGreater(score_rows, 0)
        self.assertLessEqual(score_rows, rail.LATEST_LIMIT)
        articles = json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
        self.assertTrue(articles)
        # Newest game recap per ESPN id, same tie-break as homepage_rail._recaps.
        # A fixed older story falls off the rail once newer finals take the slots.
        newest = _newest_game_recaps(articles, rail.LATEST_LIMIT)
        self.assertGreaterEqual(len(newest), 1)
        self.assertLessEqual(len(newest), rail.LATEST_LIMIT)
        for href, slug in newest:
            self.assertIn(f'href="{href}"', scores, slug)
            self.assertNotIn(f'href="{href}" target="_blank"', rail_html, slug)
        self.assertIn('target="_blank" rel="noopener"', rail_html)
        self.assertIn('https://www.espn.com/wnba/game/_/gameId/', rail_html)
        newest_recap = max(
            (article for article in articles if article.get('espnGameId')),
            key=lambda article: article['date'],
        )
        recap_day = dt.date.fromisoformat(newest_recap['date'])
        self.assertIn(f'{recap_day.strftime("%b")} {recap_day.day}', scores)
        import citation
        scheduled = next(
            row for row in citation.FINALS_TRACKER_ROWS
            if row[-1] == 'Scheduled' and row[1] != 'Not listed'
        )
        matchup = scheduled[2].split(',', 1)[0]
        away, home_club = matchup.split(' at ', 1)
        series = rail_html.split('id="playoff-series"', 1)[1].split('</section>', 1)[0]
        self.assertIn(f'{away.split()[-1]} at {home_club.split()[-1]}', series)
        day_match = re.search(r'([A-Z][a-z]{2})\.?\s+(\d{1,2})', scheduled[1])
        self.assertIn(f'{day_match.group(1)} {int(day_match.group(2))}', series)

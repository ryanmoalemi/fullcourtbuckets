"""Homepage rail is generated from scoreboard data, not slogan copy."""
import datetime as dt
import json
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import homepage_rail as rail
import internal_links as links

ROOT = Path(__file__).resolve().parents[1]
PT = ZoneInfo('America/Los_Angeles')
NOW = dt.datetime(2026, 10, 2, 12, 0, tzinfo=PT)


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
        self.assertIn('href="https://www.espn.com/wnba/game/_/gameId/401918099" target="_blank" rel="noopener"', html_text)
        self.assertIn('>Latest scores<', html_text)
        self.assertIn('href="/news/fever-aces-game-3-recap/">Aces 94, Fever 83</a>', html_text)
        self.assertNotIn('href="/news/fever-aces-game-3-recap/" target="_blank"', html_text)
        self.assertIn('href="https://www.espn.com/wnba/game/_/gameId/401918016" target="_blank" rel="noopener"', html_text)
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
            '<img class="feature-photo" id="featured-image" src="/images/articles/keep.jpg" alt="Keep">'
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
        self.assertIn('id="featured-image"', updated)
        self.assertIn('src="/images/articles/keep.jpg"', updated)
        self.assertIn('>Final standings<', updated)
        self.assertNotIn('Given to You Straight', updated)
        kept = links.apply_homepage(page, articles, None)
        self.assertIn('Given to You Straight', kept)

    def test_published_homepage_has_no_slogan_column(self):
        home = (ROOT / 'index.html').read_text(encoding='utf-8')
        rail_html = home.split('id="home-rail"', 1)[1].split('</aside>', 1)[0]
        for slogan in rail.SLOGANS:
            self.assertNotIn(slogan, home)
        self.assertNotIn('rail-card', home)
        self.assertNotIn('\u2014', rail_html)
        self.assertIn('>Playoff series<', rail_html)
        self.assertIn('>Latest scores<', rail_html)
        self.assertIn('Aces beat Fever 2-1', rail_html)
        self.assertIn('Dream lead Liberty 2-0', rail_html)
        self.assertIn('href="/news/liberty-dream-semis-game-2-recap/"', rail_html)
        self.assertNotIn('href="/news/liberty-dream-semis-game-2-recap/" target="_blank"', rail_html)
        self.assertIn('target="_blank" rel="noopener"', rail_html)
        self.assertIn('https://www.espn.com/wnba/game/_/gameId/', rail_html)
        articles = json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
        self.assertTrue(articles)

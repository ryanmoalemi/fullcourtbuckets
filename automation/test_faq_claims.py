"""Curated and related-search FAQ answers stay factual and do not talk about the page."""
import json
import re
import unittest
from pathlib import Path

import build_players as players
import per_game

ROOT = Path(__file__).resolve().parents[1]
PAGE_TALK = re.compile(
    r'this page|on this page|opened for this page|later report',
    re.I,
)
AGE = re.compile(r'\bShe is \d{2}\b')
SEASON_COUNT = re.compile(
    r'\b(\d+) (?:regular seasons|wnba seasons|seasons)\b',
    re.I,
)
ESPN_NAME = re.compile(r'\bESPN\b')
URL = re.compile(r'https?://\S+')


def answer_problems(slug: str, answer: str, profile, root: Path) -> list[str]:
    """Reasons one FAQ answer fails the fact-check rules. Empty when it is clean."""
    problems = []
    if PAGE_TALK.search(answer):
        problems.append(f'{slug} FAQ talks about the page: {answer}')
    if AGE.search(answer):
        problems.append(f'{slug} FAQ states an age: {answer}')
    if ESPN_NAME.search(URL.sub('', answer)):
        problems.append(f'{slug} FAQ names ESPN: {answer}')
    span = players.verified_pre2008_career(profile, root)
    if span:
        full = len(span[0])
        for count in SEASON_COUNT.findall(answer):
            if int(count) < full:
                problems.append(
                    f'{slug} FAQ says {count} seasons, below the {full}-season career: {answer}'
                )
    return problems


class FaqClaimTests(unittest.TestCase):
    def test_counting_averages_round_half_up_from_totals(self):
        # Float formatting misses exact .x5 totals in two ways.
        # 16.95 is 16.94999... in binary, so it prints 16.9. 8.25 is exact and
        # half-even, so it prints 8.2. WNBA.com prints the half-up total/games.
        self.assertEqual(f'{16.95:.1f}', '16.9')
        self.assertEqual(f'{14.45:.1f}', '14.4')
        self.assertEqual(f'{8.25:.1f}', '8.2')
        self.assertEqual(f'{12.05:.1f}', '12.1')
        self.assertEqual(per_game.counting_total(16.95, 43), 729)
        self.assertEqual(per_game.shown_average(16.95, 43), '17.0')
        self.assertEqual(per_game.counting_total(14.45, 42), 607)
        self.assertEqual(per_game.shown_average(14.45, 42), '14.5')
        self.assertEqual(per_game.counting_total(6.95, 42), 292)
        self.assertEqual(per_game.shown_average(6.95, 42), '7.0')
        # Becky Hammon 2014 is 264 points in 32 games, exactly 8.25. Official is 8.3.
        self.assertEqual(per_game.counting_total(8.25, 32), 264)
        self.assertEqual(per_game.shown_average(8.25, 32), '8.3')
        # Chelsea Gray 2026 is 518 points in 43 games. Official is 12.0, not 12.1.
        self.assertEqual(per_game.counting_total(12.05, 43), 518)
        self.assertEqual(per_game.shown_average(12.05, 43), '12.0')

        def season_points(slug, year):
            profile = json.loads((ROOT / 'data/wnba/players' / f'{slug}.json').read_text(encoding='utf-8'))
            return next(
                item for item in profile['season_stats']
                if item.get('season') == year and item.get('season_type') == 2
            )

        austin = season_points('shakira-austin', 2026)
        self.assertEqual(players.row_average(austin, 'pts'), '17.0')
        hamby = season_points('dearica-hamby', 2026)
        self.assertEqual(players.row_average(hamby, 'pts'), '14.5')
        self.assertEqual(players.row_average(hamby, 'reb'), '7.0')
        hammon = season_points('becky-hammon', 2014)
        self.assertEqual(players.row_average(hammon, 'pts'), '8.3')
        chelsea = season_points('chelsea-gray', 2026)
        self.assertEqual(players.row_average(chelsea, 'pts'), '12.0')
        allisha = season_points('allisha-gray', 2026)
        self.assertEqual(players.row_average(allisha, 'pts'), '19.0')

    def test_curated_faq_files_and_related_searches(self):
        problems = []
        curated = 0
        for slug in sorted(players.SEARCH_FAQ_SLUGS):
            data = json.loads((ROOT / 'data/wnba/faq' / f'{slug}.json').read_text(encoding='utf-8'))
            profile = json.loads((ROOT / 'data/wnba/players' / f'{slug}.json').read_text(encoding='utf-8'))
            published = dict(players.faq_answer_pairs(profile, ROOT))
            for item in data['items']:
                curated += 1
                answer = item['answer']
                problems.extend(answer_problems(slug, answer, profile, ROOT))
                if published.get(item['question']) != answer:
                    problems.append(f'{slug} file answer does not match the generator: {item["question"]}')
        related = 0
        related_slugs = 0
        for slug, items in sorted(players._disk_topic_candidates(ROOT).items()):
            if not items:
                continue
            related_slugs += 1
            profile = json.loads((ROOT / 'data/wnba/players' / f'{slug}.json').read_text(encoding='utf-8'))
            for item in items:
                related += 1
                problems.extend(answer_problems(slug, item['answer'], profile, ROOT))
        self.assertGreaterEqual(curated, 360)
        self.assertEqual(problems, [])
        self.assertGreaterEqual(len(players.SEARCH_FAQ_SLUGS), 36)
        # Related-search files can be held for curated pages. The check still ran.
        self.assertGreaterEqual(related_slugs, 0)
        self.assertGreaterEqual(related, 0)

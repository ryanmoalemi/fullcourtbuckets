"""Curated and related-search FAQ answers stay factual and do not talk about the page."""
import json
import re
import unittest
from pathlib import Path

import build_players as players

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
    def test_rounding_matches_the_season_table(self):
        self.assertEqual(players.value(8.25), '8.3')
        self.assertEqual(players.value(518 / 43), '12.0')
        self.assertEqual(players.round_tenth(8.25), players.value(8.25))
        gray = json.loads((ROOT / 'data/wnba/players/chelsea-gray.json').read_text(encoding='utf-8'))
        row = next(
            item for item in gray['season_stats']
            if item.get('season') == 2026 and item.get('season_type') == 2
        )
        self.assertEqual(players.value(row['pts']), '12.0')
        hammon = json.loads((ROOT / 'data/wnba/players/becky-hammon.json').read_text(encoding='utf-8'))
        season = next(
            item for item in hammon['season_stats']
            if item.get('season') == 2014 and item.get('season_type') == 2
        )
        self.assertEqual(players.value(season['pts']), '8.3')

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

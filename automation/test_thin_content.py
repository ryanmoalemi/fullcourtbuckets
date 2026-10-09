"""Thin-content rules for team summaries and inactive player bios.

Player pages may not share a sentence of 12 or more words, aside from the
fixed labels listed below. Bios may not use unverified-claim markers.
"""
from __future__ import annotations

import html
import json
import re
import unittest
from collections import defaultdict
from pathlib import Path

import career_summary
import team_season
import internal_links
import build_players as builder

ROOT = Path(__file__).resolve().parents[1]
WORD_RE = re.compile(r"[A-Za-z0-9']+")
SENTENCE_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
# Sentences that are labels, not biography. Anything else of 12+ words must be unique.
# The season-table controls repeat when two players have the same years on file.
FIXED_LABELS = frozenset()


def _fixed(sentence: str) -> bool:
    if sentence in FIXED_LABELS:
        return True
    return (
        'Season by season stats' in sentence
        and 'per game averages except games played' in sentence
    )
MARKERS = career_summary.MARKERS


def _plain(fragment: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', fragment or '')
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def _sentences(fragment: str) -> list[str]:
    plain = _plain(fragment)
    found = []
    seen = set()
    for part in SENTENCE_RE.split(plain):
        words = WORD_RE.findall(part)
        if len(words) < 12:
            continue
        sentence = ' '.join(words)
        if _fixed(sentence) or sentence in seen:
            continue
        seen.add(sentence)
        found.append(sentence)
    return found


def _main(page: str) -> str:
    if '<main' not in page:
        return ''
    return page.split('<main', 1)[1].split('</main>', 1)[0]


def _section(page: str, section_id: str) -> str:
    match = re.search(rf'<section\b[^>]*\bid="{section_id}"[^>]*>.*?</section>', page, re.S)
    return match.group(0) if match else ''


class CareerRuleTests(unittest.TestCase):
    def test_marker_list_catches_unverified_claims(self):
        self.assertIn('reportedly', career_summary.marker_hits('She reportedly scored 40.'))
        self.assertIn('widely regarded', career_summary.marker_hits('She is widely regarded as a star.'))
        self.assertEqual(career_summary.marker_hits('She scored 20 points in 2014.'), [])

    def test_published_player_bios_do_not_share_long_sentences_or_markers(self):
        shared = defaultdict(list)
        marker_hits = []
        pages = 0
        for path in sorted((ROOT / 'wnba').glob('*/index.html')):
            if path.parent.name in {'teams', 'assets', 'couples'}:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'Inactive player' not in text or 'http-equiv="refresh"' in text.lower():
                continue
            pages += 1
            main = _main(text)
            for sentence in _sentences(main):
                shared[sentence].append(path.parent.name)
            bio = _section(text, 'career') + _section(text, 'answer-summary')
            # answer-summary is a paragraph, not a section. Include it from main via the class.
            summary = re.search(r'<p class="answer-summary">.*?</p>', main, re.S)
            blob = _plain((bio or '') + (summary.group(0) if summary else ''))
            for marker in MARKERS:
                if marker in blob.casefold():
                    marker_hits.append(f'{path.parent.name}: {marker}')
        self.assertGreaterEqual(pages, 300)
        duplicates = {sentence: slugs for sentence, slugs in shared.items() if len(slugs) > 1}
        self.assertEqual(duplicates, {})
        self.assertEqual(marker_hits, [])

    def test_published_career_copy_matches_the_stored_rows(self):
        rollout = json.loads((ROOT / 'data/wnba/career-rollout.json').read_text(encoding='utf-8'))
        for slug in rollout['slugs']:
            profile = json.loads((ROOT / 'data/wnba/players' / f'{slug}.json').read_text(encoding='utf-8'))
            page = (ROOT / 'wnba' / slug / 'index.html').read_text(encoding='utf-8')
            main = _plain(_main(page))
            for sentence in career_summary.sentences_for(profile, ROOT):
                plain = _plain(sentence)
                self.assertIn(plain, main, slug)

    def test_inactive_pages_stay_indexable_and_in_the_sitemap(self):
        sitemap = (ROOT / 'player-sitemap.xml').read_text(encoding='utf-8')
        missing = []
        noindex = []
        for path in sorted((ROOT / 'wnba').glob('*/index.html')):
            if path.parent.name in {'teams', 'assets', 'couples'}:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'Inactive player' not in text or 'http-equiv="refresh"' in text.lower():
                continue
            if 'content="noindex"' in text or 'noindex' in text.split('</head>', 1)[0]:
                noindex.append(path.parent.name)
            url = f'https://fullcourtbuckets.com/wnba/{path.parent.name}/'
            if url not in sitemap:
                missing.append(path.parent.name)
            self.assertNotIn('balldontlie', text.casefold(), path.parent.name)
        self.assertEqual(noindex, [])
        self.assertEqual(missing, [])


class TeamSummaryTests(unittest.TestCase):
    def test_every_team_summary_is_100_to_200_words_and_cites_its_article(self):
        index = json.loads((ROOT / 'data/wnba/players-index.json').read_text(encoding='utf-8'))
        linking = internal_links.catalog_from_index(index)
        table = builder.load_standings_by_name(ROOT)
        for slot in linking['by_id'].values():
            standing = table.get(slot['full_name']) or table.get(slot.get('name') or '')
            summary = team_season.summary_paragraphs(ROOT, slot, standing)
            count = team_season.word_count(summary)
            self.assertGreaterEqual(count, 100, slot['slug'])
            self.assertLessEqual(count, 200, slot['slug'])
            self.assertNotIn('\u2014', summary, slot['slug'])
            self.assertNotIn('balldontlie', summary.casefold(), slot['slug'])
            page = (ROOT / 'wnba' / 'teams' / slot['slug'] / 'index.html').read_text(encoding='utf-8')
            block = _section(page, 'season-2026')
            self.assertIn('Season summary', block, slot['slug'])
            self.assertIn('Wikimedia Commons', block, slot['slug'])
            self.assertIn('target="_blank" rel="noopener"', block, slot['slug'])
            news = _section(page, 'team-news')
            self.assertIn('Latest stories', news, slot['slug'])
            self.assertNotIn('target="_blank"', news, slot['slug'])
        for slug in ('chicago-sky', 'connecticut-sun', 'phoenix-mercury', 'seattle-storm', 'los-angeles-sparks'):
            page = (ROOT / 'wnba' / 'teams' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertIn('latest league stories', _section(page, 'team-news'), slug)
        for slug, rows in team_season.COVERAGE.items():
            for href, _label, claim in rows:
                article_slug = href.strip('/').split('/')[-1]
                article = (ROOT / 'news' / article_slug / 'index.html').read_text(encoding='utf-8')
                self.assertIn(claim, article, f'{slug} {article_slug} {claim}')


if __name__ == '__main__':
    unittest.main()

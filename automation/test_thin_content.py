"""Thin-content rules for team summaries and inactive player bios.

Player pages may not share a sentence of 12 or more words, aside from the
fixed labels listed below. Bios may not use unverified-claim markers.

A second check strips names, numbers, teams, colleges, and years. If one
sentence skeleton then shows up on more than 5% of the rewritten bios, the
test fails. The same rule applies to team season summaries.
"""
from __future__ import annotations

import html
import json
import re
import unittest
from collections import defaultdict
from pathlib import Path

import career_prose
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
YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')
ORDINAL_RE = re.compile(r'\b\d+(?:st|nd|rd|th)\b', re.I)
ORDINAL_WORDS = (
    'first', 'second', 'third', 'fourth', 'fifth',
    'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
)
NUMBER_RE = re.compile(r'\b\d+(?:\.\d+)?\b')
TABLE_ROW_RE = re.compile(
    r'<th scope="row">(\d{4})</th><td class="team-cell">([^<]+)</td>'
)
META_PAGE_RE = re.compile(
    r'\b(?:rows?|stored|this page|on this page|database|standings file|standings line)\b',
    re.I,
)


def _career_copy(page: str) -> str:
    match = re.search(r'<div class="career-copy">(.*?)</div>', page, re.S)
    if not match:
        return ''
    copy = re.sub(r'<p class="career-sources">.*?</p>', ' ', match.group(1), flags=re.S)
    return copy


def _paragraphs(fragment: str) -> list[str]:
    plain_parts = []
    for piece in re.findall(r'<p\b[^>]*>(.*?)</p>', fragment or '', re.S):
        if 'career-sources' in piece:
            continue
        text = _plain(piece)
        if text:
            plain_parts.append(text)
    return plain_parts


def _known_teams() -> list[str]:
    found = set()
    extras_path = ROOT / 'data' / 'wnba' / 'career-extras.json'
    if extras_path.is_file():
        extras = json.loads(extras_path.read_text(encoding='utf-8'))
        for extra in extras.values():
            draft = extra.get('draft') if isinstance(extra, dict) else None
            if isinstance(draft, dict) and draft.get('team'):
                found.add(str(draft['team']).strip())
    for path in (ROOT / 'data' / 'wnba' / 'players').glob('*.json'):
        try:
            profile = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        for row in profile.get('season_stats') or []:
            team = career_summary._team(row) if isinstance(row, dict) else ''
            if team and 'not named' not in team:
                found.add(team)
    return sorted(found, key=len, reverse=True)


def _known_colleges() -> list[str]:
    found = set()
    extras_path = ROOT / 'data' / 'wnba' / 'career-extras.json'
    extras = json.loads(extras_path.read_text(encoding='utf-8')) if extras_path.is_file() else {}
    for path in (ROOT / 'data' / 'wnba' / 'players').glob('*.json'):
        try:
            profile = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        slug = path.stem
        college = career_prose._college(profile, extras.get(slug) or {})
        if college:
            found.add(college)
    return sorted(found, key=len, reverse=True)


def _known_places() -> list[str]:
    found = {'the United States', 'United States'}
    for _label, (year, city) in career_summary.OLYMPICS.items():
        found.add(city)
        found.add(str(year))
    extras_path = ROOT / 'data' / 'wnba' / 'career-extras.json'
    if extras_path.is_file():
        extras = json.loads(extras_path.read_text(encoding='utf-8'))
        for extra in extras.values():
            if not isinstance(extra, dict):
                continue
            for event in career_prose._olympics(extra):
                found.add(event['nation'])
                found.add(career_prose._nation(event['nation']))
                found.add(event['city'])
    found.discard('')
    return sorted(found, key=len, reverse=True)


def _template(sentence: str, name: str, teams: list[str], colleges: list[str], places: list[str]) -> str:
    text = sentence
    for team in teams:
        text = re.sub(rf'\b{re.escape(team)}\b', '{TEAM}', text)
    for college in colleges:
        text = text.replace(college, '{COLLEGE}')
    for place in places:
        text = re.sub(rf'\b{re.escape(place)}\b', '{PLACE}', text)
    if name:
        text = text.replace(name, '{NAME}')
        last = name.split()[-1]
        if len(last) >= 4:
            text = re.sub(rf'\b{re.escape(last)}\b', '{NAME}', text)
    text = YEAR_RE.sub('{YEAR}', text)
    text = ORDINAL_RE.sub('{NUM}', text)
    for word in ORDINAL_WORDS:
        text = re.sub(rf'\b{word}\b', '{NUM}', text, flags=re.I)
    text = NUMBER_RE.sub('{NUM}', text)
    return re.sub(r'\s+', ' ', text).strip()


def _table_pairs(page: str) -> set[tuple[str, int]]:
    pairs = set()
    for year, team in TABLE_ROW_RE.findall(page):
        pairs.add((html.unescape(team).strip(), int(year)))
    return pairs


def _season_claims(text: str, teams: list[str]) -> set[tuple[str, int]]:
    """Team-years stated with a season phrase.

    Draft wording alone is not a season. A sentence counts only when it uses
    "the Team in YEAR" or "the Team from YEAR through YEAR", including when
    that phrase sits in the draft sentence because she played there.
    """
    claims = set()
    for sentence in SENTENCE_RE.split(text):
        work = sentence
        for team in teams:
            span = re.compile(
                rf'\bthe {re.escape(team)} from (\d{{4}}) through (\d{{4}})'
            )
            for start, end in span.findall(work):
                start_year, end_year = int(start), int(end)
                if start_year <= end_year:
                    for year in range(start_year, end_year + 1):
                        claims.add((team, year))
            work = span.sub(' ', work)
            single = re.compile(rf'\bthe {re.escape(team)} in (\d{{4}})')
            for year in single.findall(work):
                claims.add((team, int(year)))
            work = single.sub(' ', work)
    return claims


def _through_ends(text: str, teams: list[str]) -> dict[str, int]:
    """Shorthand "the Team through YEAR" covers logged seasons up to that year.

    A continuous "from YEAR through YEAR" is not this shorthand.
    """
    work = text
    for team in teams:
        work = re.sub(rf'\bthe {re.escape(team)} from \d{{4}} through \d{{4}}', ' ', work)
    ends = {}
    for team in teams:
        for year in re.findall(rf'\bthe {re.escape(team)},? through (\d{{4}})', work):
            ends[team] = max(ends.get(team, 0), int(year))
    return ends


def _span_covered(phrase: str, copy: str, ends: dict[str, int]) -> bool:
    if phrase in copy:
        return True
    match = re.match(r'the (.+) from (\d{4}) through (\d{4})$', phrase)
    if match:
        team, _start, end = match.group(1), int(match.group(2)), int(match.group(3))
        return ends.get(team, 0) >= end
    match = re.match(r'the (.+) in (\d{4})$', phrase)
    if match:
        team, year = match.group(1), int(match.group(2))
        return ends.get(team, 0) >= year
    return False


def _team_mentions(sentence: str, teams: list[str]) -> dict[str, int]:
    work = sentence
    counts = {}
    for team in teams:
        found = re.findall(rf'\b{re.escape(team)}\b', work)
        if found:
            counts[team] = len(found)
            work = re.sub(rf'\b{re.escape(team)}\b', ' ', work)
    return counts


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
        checked = 0
        for slug in rollout['slugs']:
            page = (ROOT / 'wnba' / slug / 'index.html').read_text(encoding='utf-8')
            if 'career-sources' not in page:
                continue
            checked += 1
            profile = json.loads((ROOT / 'data/wnba/players' / f'{slug}.json').read_text(encoding='utf-8'))
            main = _plain(_main(page))
            for sentence in career_summary.sentences_for(profile, ROOT):
                plain = _plain(sentence)
                self.assertIn(plain, main, slug)
            sources = _plain(re.search(r'<p class="career-sources">.*?</p>', page, re.S).group(0))
            self.assertLess(len(WORD_RE.findall(sources)), 12, slug)
            self.assertNotIn('balldontlie', sources.casefold(), slug)
            self.assertIn('Full Court Buckets season logs', sources)
            extra = career_summary.load_extras(ROOT).get(slug) or {}
            bbref = str(extra.get('bbref') or '').strip() if isinstance(extra, dict) else ''
            international = extra.get('international') if isinstance(extra, dict) and isinstance(extra.get('international'), dict) else {}
            if bbref or str(international.get('source') or '').strip():
                self.assertIn('Basketball-Reference', sources, slug)
                self.assertIn('basketball-reference.com', page, slug)
        self.assertGreaterEqual(checked, 90)

    def test_rewritten_bios_do_not_reuse_a_sentence_template(self):
        teams = _known_teams()
        colleges = _known_colleges()
        places = _known_places()
        shared = defaultdict(set)
        pages = []
        for path in sorted((ROOT / 'wnba').glob('*/index.html')):
            if path.parent.name in {'teams', 'assets', 'couples'}:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'Inactive player' not in text or 'career-sources' not in text:
                continue
            pages.append(path.parent.name)
            profile = json.loads((ROOT / 'data/wnba/players' / f'{path.parent.name}.json').read_text(encoding='utf-8'))
            name = career_summary.player_name(profile)
            copy = _career_copy(text)
            self.assertEqual(META_PAGE_RE.findall(_plain(copy)), [], path.parent.name)
            for paragraph in _paragraphs(copy):
                for part in SENTENCE_RE.split(paragraph):
                    words = WORD_RE.findall(part)
                    if len(words) < 6:
                        continue
                    key = _template(part, name, teams, colleges, places)
                    shared[key].add(path.parent.name)
        self.assertGreaterEqual(len(pages), 90)
        limit = 0.05 * len(pages)
        over = {
            template: sorted(slugs)
            for template, slugs in shared.items()
            if len(slugs) / len(pages) > 0.05
        }
        self.assertEqual(over, {})
        self.assertGreater(limit, 0)

    def test_sportswriter_bios_use_she_and_skip_filler_verbs(self):
        voice_path = ROOT / 'data' / 'wnba' / 'career-voice.json'
        if not voice_path.is_file():
            self.skipTest('sportswriter voice has not been published')
        slugs = json.loads(voice_path.read_text(encoding='utf-8')).get('slugs') or []
        self.assertGreaterEqual(len(slugs), 40)
        banned = ('competed for', 'suited up', 'recorded', 'during the regular season', 'subsequently')
        for slug in slugs:
            page = (ROOT / 'wnba' / slug / 'index.html').read_text(encoding='utf-8')
            copy = _paragraphs(_career_copy(page))
            self.assertGreaterEqual(len(copy), 1, slug)
            profile = json.loads((ROOT / 'data/wnba/players' / f'{slug}.json').read_text(encoding='utf-8'))
            name = career_summary.player_name(profile)
            self.assertIn(name, copy[0], slug)
            for sentence in copy[1:]:
                self.assertNotIn(name, sentence, slug)
                body = sentence
                if body.startswith('She '):
                    body = body[3:]
                elif body.startswith('Her '):
                    body = body[4:]
                self.assertNotRegex(body, r'\b(?:She|Her)\b', slug)
            blob = ' '.join(copy).casefold()
            for phrase in banned:
                self.assertNotIn(phrase, blob, slug)

    def test_career_summary_matches_the_season_table(self):
        teams = _known_teams()
        checked = 0
        for path in sorted((ROOT / 'wnba').glob('*/index.html')):
            slug = path.parent.name
            if slug in {'teams', 'assets', 'couples'}:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'Inactive player' not in text or 'career-sources' not in text:
                continue
            checked += 1
            profile = json.loads((ROOT / 'data/wnba/players' / f'{slug}.json').read_text(encoding='utf-8'))
            copy = _plain(_career_copy(text))
            table = _table_pairs(text)
            self.assertTrue(table, slug)
            ends = _through_ends(copy, teams)
            for phrase in career_prose.span_phrases(profile):
                self.assertTrue(_span_covered(phrase, copy, ends), f'{slug}: {phrase}')
            claims = _season_claims(copy, teams)
            extra = sorted(claims - table)
            self.assertEqual(extra, [], slug)
            uncovered = sorted(
                pair for pair in table
                if pair not in claims and ends.get(pair[0], 0) < pair[1]
            )
            self.assertEqual(uncovered, [], slug)
        self.assertGreaterEqual(checked, 90)

    def test_closing_sentence_names_each_team_once(self):
        teams = _known_teams()
        extras = json.loads((ROOT / 'data/wnba/career-extras.json').read_text(encoding='utf-8'))
        repeated = {}
        false_debut = {}
        invented = []
        checked = 0
        for path in sorted((ROOT / 'wnba').glob('*/index.html')):
            slug = path.parent.name
            if slug in {'teams', 'assets', 'couples'}:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'Inactive player' not in text or 'career-sources' not in text:
                continue
            checked += 1
            paragraphs = _paragraphs(_career_copy(text))
            self.assertTrue(paragraphs, slug)
            counts = _team_mentions(paragraphs[-1], teams)
            dupes = {team: count for team, count in counts.items() if count > 1}
            if dupes:
                repeated[slug] = dupes
            profile = json.loads((ROOT / 'data/wnba/players' / f'{slug}.json').read_text(encoding='utf-8'))
            copy = _plain(_career_copy(text))
            folded = copy.casefold()
            if 'overseas' in folded or 'injur' in folded:
                invented.append(slug)
            extra = extras.get(slug) if isinstance(extras.get(slug), dict) else {}
            draft = career_prose._draft(extra or {})
            years = []
            for phrase in career_prose.span_phrases(profile):
                for year in re.findall(r'\d{4}', phrase):
                    years.append(int(year))
            if draft and years and int(draft['year']) < min(years):
                debut = f"from {min(years)} through"
                if debut in copy:
                    false_debut[slug] = debut
        self.assertGreaterEqual(checked, 90)
        self.assertEqual(repeated, {})
        self.assertEqual(false_debut, {})
        self.assertEqual(invented, [])

    def test_crystal_bradford_team_years_match_her_table(self):
        page = (ROOT / 'wnba' / 'crystal-bradford' / 'index.html').read_text(encoding='utf-8')
        if 'career-sources' not in page:
            self.skipTest('Crystal Bradford has not been rewritten yet')
        copy = _plain(_career_copy(page))
        table = _table_pairs(page)
        for phrase in (
            'the Los Angeles Sparks in 2015',
            'the Atlanta Dream in 2021',
            'the Las Vegas Aces in 2025',
        ):
            self.assertIn(phrase, copy)
        self.assertIn(('Las Vegas Aces', 2025), table)
        self.assertIn(('Atlanta Dream', 2021), table)
        self.assertIn(('Los Angeles Sparks', 2015), table)

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
            self.assertIn(summary, page, slot['slug'])
            self.assertEqual(META_PAGE_RE.findall(_plain(summary)), [], slot['slug'])
            self.assertIn('Season summary', block, slot['slug'])
            self.assertIn('Wikimedia Commons', block, slot['slug'])
            self.assertIn('target="_blank" rel="noopener"', block, slot['slug'])
            news = _section(page, 'team-news')
            self.assertIn('Latest stories', news, slot['slug'])
            self.assertNotIn('target="_blank"', news, slot['slug'])
        for slug in ('chicago-sky', 'connecticut-sun', 'phoenix-mercury', 'seattle-storm', 'los-angeles-sparks'):
            page = (ROOT / 'wnba' / 'teams' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertIn('latest league stories', _section(page, 'team-news'), slug)
        sky = (ROOT / 'wnba' / 'teams' / 'chicago-sky' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('image/webp', _section(sky, 'season-2026'))
        for slug, rows in team_season.COVERAGE.items():
            for href, _label, claim in rows:
                article_slug = href.strip('/').split('/')[-1]
                article = (ROOT / 'news' / article_slug / 'index.html').read_text(encoding='utf-8')
                self.assertIn(claim, article, f'{slug} {article_slug} {claim}')

    def test_team_summaries_do_not_share_a_sentence_template(self):
        index = json.loads((ROOT / 'data/wnba/players-index.json').read_text(encoding='utf-8'))
        linking = internal_links.catalog_from_index(index)
        names = set()
        teams = set()
        pages = {}
        for slot in linking['by_id'].values():
            teams.add(slot['full_name'])
            page = (ROOT / 'wnba' / 'teams' / slot['slug'] / 'index.html').read_text(encoding='utf-8')
            block = _section(page, 'season-2026')
            summary = re.search(r'<p class="season-summary">(.*?)</p>', block, re.S)
            self.assertIsNotNone(summary, slot['slug'])
            pages[slot['slug']] = _plain(summary.group(1))
            for label in re.findall(r'>([^<]+)</a>', summary.group(1)):
                names.add(html.unescape(label))
        team_names = sorted(teams, key=len, reverse=True)
        player_names = sorted(names, key=len, reverse=True)
        shared = defaultdict(set)
        for slug, plain in pages.items():
            for part in SENTENCE_RE.split(plain):
                words = WORD_RE.findall(part)
                if len(words) < 6:
                    continue
                text = part
                for team in team_names:
                    text = re.sub(rf'\b{re.escape(team)}\b', '{TEAM}', text)
                for player in player_names:
                    text = re.sub(rf'\b{re.escape(player)}\b', '{NAME}', text)
                    last = player.split()[-1]
                    if len(last) >= 4:
                        text = re.sub(rf'\b{re.escape(last)}\b', '{NAME}', text)
                text = text.replace('Eastern Conference', '{CONF}').replace('Western Conference', '{CONF}')
                text = YEAR_RE.sub('{YEAR}', text)
                text = ORDINAL_RE.sub('{NUM}', text)
                text = NUMBER_RE.sub('{NUM}', text)
                shared[re.sub(r'\s+', ' ', text).strip()].add(slug)
        over = {
            template: sorted(slugs)
            for template, slugs in shared.items()
            if len(slugs) > 1 and len(slugs) / len(pages) > 0.05
        }
        self.assertEqual(over, {})

    def test_team_summary_patch_keeps_an_existing_photo(self):
        index = json.loads((ROOT / 'data/wnba/players-index.json').read_text(encoding='utf-8'))
        linking = internal_links.catalog_from_index(index)
        slot = next(item for item in linking['by_id'].values() if item['slug'] == 'chicago-sky')
        standing = builder.load_standings_by_name(ROOT).get(slot['full_name'])
        page = (ROOT / 'wnba' / 'teams' / 'chicago-sky' / 'index.html').read_text(encoding='utf-8')
        updated = team_season.patch_team_html(page, ROOT, slot, standing)
        before = _section(page, 'season-2026')
        after = _section(updated, 'season-2026')
        self.assertEqual(before.count('<picture>'), after.count('<picture>'))
        self.assertIn('image/webp', after)
        self.assertIn('class="season-summary"', after)


if __name__ == '__main__':
    unittest.main()

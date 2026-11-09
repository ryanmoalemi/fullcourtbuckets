#!/usr/bin/env python3
"""2027 WNBA Draft Lottery hub: exact pick probabilities, simulator, team needs.

Odds are the Oct. 28, 2026 league release (1,000 assigned four-ball combinations).
Picks 1 and 2 are drawn. Picks 3-7 follow the pre-lottery order among the slots
that were not drawn. The math enumerates all 42 ordered pairs. No Monte Carlo.

    python automation/build_draft_lottery_2027.py
"""
from __future__ import annotations

import csv
import html
import json
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path

import analytics
import internal_links
import site_nav
import team_hub

ROOT = Path(__file__).resolve().parents[1]
ROUTE = '/wnba/draft-lottery-2027/'
BASE = 'https://fullcourtbuckets.com'
TITLE = '2027 WNBA Draft Lottery Odds, Simulator and Live Results (Nov 15)'
DESCRIPTION = (
    'Official 2027 WNBA Draft Lottery odds, full pick probabilities for picks 1-7, '
    'team needs, live results, and a free CSV. Drawing: Nov. 15, 2026.'
)
PUBLISHED = '2026-11-09'
CSV_PATH = ROOT / 'data' / 'wnba-draft-lottery-2027-odds.csv'
RESULTS_PATH = ROOT / 'data' / 'wnba-draft-lottery-2027-results.json'
PAGE_PATH = ROOT / 'wnba' / 'draft-lottery-2027' / 'index.html'
SEED = 20261115
TOTAL = 1000

# Pre-lottery order is worst record first. Houston won the head-to-head tiebreak
# over Toronto, so Houston is first and cannot land past pick 3.
SLOTS = [
    {
        'id': 'HOU', 'circle': 'HOU', 'team': 'Houston Comets', 'short': 'Houston',
        'label': 'Houston', 'href': '/wnba/teams/connecticut-sun/',
        'chances': 329, 'record': '22-66', 'record_scope': '2025 and 2026',
        'original': 'Houston', 'facts': 'Connecticut Sun',
    },
    {
        'id': 'TOR', 'circle': 'TOR', 'team': 'Toronto Tempo', 'short': 'Toronto',
        'label': 'Toronto', 'href': '/wnba/teams/toronto-tempo/',
        'chances': 329, 'record': '11-33', 'record_scope': '2026 only',
        'original': 'Toronto', 'facts': 'Toronto Tempo',
    },
    {
        'id': 'WAS', 'circle': 'WAS', 'team': 'Washington Mystics', 'short': 'Washington',
        'label': 'Washington (from Chicago)', 'href': '/wnba/teams/washington-mystics/',
        'chances': 161, 'record': '26-62', 'record_scope': 'Chicago, 2025 and 2026',
        'original': 'Chicago', 'facts': 'Washington Mystics',
    },
    {
        'id': 'SEA', 'circle': 'SEA', 'team': 'Seattle Storm', 'short': 'Seattle',
        'label': 'Seattle', 'href': '/wnba/teams/seattle-storm/',
        'chances': 93, 'record': '31-57', 'record_scope': '2025 and 2026',
        'original': 'Seattle', 'facts': 'Seattle Storm',
    },
    {
        'id': 'POR', 'circle': 'POR', 'team': 'Portland Fire', 'short': 'Portland',
        'label': 'Portland', 'href': '/wnba/teams/portland-fire/',
        'chances': 52, 'record': '17-27', 'record_scope': '2026 only',
        'original': 'Portland', 'facts': 'Portland Fire',
    },
    {
        'id': 'LAL', 'circle': 'LAL', 'team': 'Los Angeles Sparks', 'short': 'Los Angeles',
        'label': 'Los Angeles (own pick)', 'href': '/wnba/teams/los-angeles-sparks/',
        'chances': 24, 'record': '37-51', 'record_scope': '2025 and 2026',
        'original': 'Los Angeles', 'facts': 'Los Angeles Sparks',
    },
    {
        'id': 'LAL-PHX', 'circle': 'PHX', 'team': 'Los Angeles Sparks', 'short': 'Los Angeles',
        'label': 'Los Angeles (from Phoenix)', 'href': '/wnba/teams/los-angeles-sparks/',
        'chances': 12, 'record': '43-45', 'record_scope': 'Phoenix, 2025 and 2026',
        'original': 'Phoenix', 'facts': 'Los Angeles Sparks',
    },
]
ORDER = [slot['id'] for slot in SLOTS]
CHANCES = {slot['id']: slot['chances'] for slot in SLOTS}
BY_ID = {slot['id']: slot for slot in SLOTS}

# College lines fetched from Sports-Reference on Nov. 9, 2026.
# Board order is Ultimate Big Board's Oct. 29, 2026 snapshot (8 mocks).
# No. 10 on that board (Taliah Scott) named no school and appeared in 1 of 8 mocks,
# so the tenth card is Clara Strack, the next player in all 8 mocks (board rank 11).
PROSPECTS = [
    {
        'board': 1, 'mocks': '8 of 8', 'name': 'JuJu Watkins', 'initials': 'JW',
        'school': 'USC', 'pos': 'G', 'height': '6-2',
        'sr': 'https://www.sports-reference.com/cbb/players/juju-watkins-1.html',
        'full': {'season': '2024-25', 'school': 'USC', 'g': 33, 'pts': '23.9', 'reb': '6.8', 'ast': '3.4', 'stl': '2.2', 'blk': '1.8', 'fg': '.426'},
        'early': {'g': 1, 'pts': '21.0', 'reb': '5.0', 'ast': '2.0', 'school': 'USC'},
        'note': 'Sports-Reference has no 2025-26 season for her.',
    },
    {
        'board': 2, 'mocks': '8 of 8', 'name': 'Madison Booker', 'initials': 'MB',
        'school': 'Texas', 'pos': 'F', 'height': '6-1',
        'sr': 'https://www.sports-reference.com/cbb/players/madison-booker-1.html',
        'full': {'season': '2025-26', 'school': 'Texas', 'g': 39, 'pts': '18.9', 'reb': '6.7', 'ast': '3.7', 'stl': '2.2', 'blk': '0.7', 'fg': '.508'},
        'early': {'g': 2, 'pts': '27.0', 'reb': '5.0', 'ast': '5.5', 'school': 'Texas'},
        'note': '',
    },
    {
        'board': 3, 'mocks': '8 of 8', 'name': 'Hannah Hidalgo', 'initials': 'HH',
        'school': 'Notre Dame', 'pos': 'G', 'height': '5-7',
        'sr': 'https://www.sports-reference.com/cbb/players/hannah-hidalgo-1.html',
        'full': {'season': '2025-26', 'school': 'Notre Dame', 'g': 36, 'pts': '25.3', 'reb': '6.9', 'ast': '5.2', 'stl': '5.6', 'blk': '0.3', 'fg': '.475'},
        'early': {'g': 2, 'pts': '29.5', 'reb': '6.5', 'ast': '5.0', 'school': 'Notre Dame'},
        'note': '',
    },
    {
        'board': 4, 'mocks': '8 of 8', 'name': "S'Mya Nichols", 'initials': 'SN',
        'school': 'Kansas', 'pos': 'G', 'height': '6-0',
        'sr': 'https://www.sports-reference.com/cbb/players/smya-nichols-1.html',
        'full': {'season': '2025-26', 'school': 'Kansas', 'g': 36, 'pts': '17.4', 'reb': '3.1', 'ast': '4.6', 'stl': '1.1', 'blk': '0.2', 'fg': '.482'},
        'early': {'g': 2, 'pts': '13.5', 'reb': '3.0', 'ast': '3.5', 'school': 'Kansas'},
        'note': '',
    },
    {
        'board': 5, 'mocks': '8 of 8', 'name': 'Mikaylah Williams', 'initials': 'MW',
        'school': 'LSU', 'pos': 'G', 'height': '6-0',
        'sr': 'https://www.sports-reference.com/cbb/players/mikaylah-williams-1.html',
        'full': {'season': '2025-26', 'school': 'LSU', 'g': 35, 'pts': '14.2', 'reb': '5.3', 'ast': '3.6', 'stl': '1.4', 'blk': '0.2', 'fg': '.507'},
        'early': {'g': 2, 'pts': '19.5', 'reb': '5.5', 'ast': '5.5', 'school': 'LSU'},
        'note': '',
    },
    {
        'board': 6, 'mocks': '8 of 8', 'name': 'MiLaysia Fulwiley', 'initials': 'MF',
        'school': 'LSU', 'pos': 'G', 'height': '5-9',
        'sr': 'https://www.sports-reference.com/cbb/players/milaysia-fulwiley-1.html',
        'full': {'season': '2025-26', 'school': 'LSU', 'g': 35, 'pts': '14.6', 'reb': '3.6', 'ast': '3.5', 'stl': '2.8', 'blk': '1.4', 'fg': '.474'},
        'early': {'g': 2, 'pts': '17.5', 'reb': '2.5', 'ast': '5.0', 'school': 'LSU'},
        'note': 'Her 2023-24 and 2024-25 seasons on that page are at South Carolina.',
    },
    {
        'board': 7, 'mocks': '3 of 8', 'name': 'Audi Crooks', 'initials': 'AC',
        'school': 'Oklahoma State', 'pos': 'C', 'height': '6-3',
        'sr': 'https://www.sports-reference.com/cbb/players/audi-crooks-1.html',
        'full': {'season': '2025-26', 'school': 'Iowa State', 'g': 31, 'pts': '25.8', 'reb': '7.7', 'ast': '1.7', 'stl': '0.3', 'blk': '0.8', 'fg': '.649'},
        'early': {'g': 2, 'pts': '18.0', 'reb': '9.0', 'ast': '0.0', 'school': 'Oklahoma State'},
        'note': 'Only 3 of 8 mocks on that board include her, so this rank is softer than the names above.',
    },
    {
        'board': 8, 'mocks': '7 of 8', 'name': 'Oluchi Okananwa', 'initials': 'OO',
        'school': 'Maryland', 'pos': 'G', 'height': '5-10',
        'sr': 'https://www.sports-reference.com/cbb/players/oluchi-okananwa-1.html',
        'full': {'season': '2025-26', 'school': 'Maryland', 'g': 33, 'pts': '17.8', 'reb': '5.4', 'ast': '2.0', 'stl': '2.2', 'blk': '0.2', 'fg': '.518'},
        'early': {'g': 1, 'pts': '11.0', 'reb': '9.0', 'ast': '4.0', 'school': 'Maryland'},
        'note': 'Her 2023-24 and 2024-25 seasons on that page are at Duke.',
    },
    {
        'board': 9, 'mocks': '5 of 8', 'name': 'Ashlyn Watkins', 'initials': 'AW',
        'school': 'South Carolina', 'pos': 'F', 'height': '6-3',
        'sr': 'https://www.sports-reference.com/cbb/players/ashlyn-watkins-1.html',
        'full': {'season': '2024-25', 'school': 'South Carolina', 'g': 14, 'pts': '7.2', 'reb': '6.1', 'ast': '1.1', 'stl': '1.3', 'blk': '1.9', 'fg': '.512'},
        'early': {'g': 1, 'pts': '7.0', 'reb': '10.0', 'ast': '2.0', 'school': 'South Carolina'},
        'note': 'The 2024-25 line is 14 games. Her 2023-24 line on that page is 38 games, 9.2 points and 7.4 rebounds.',
    },
    {
        'board': 11, 'mocks': '8 of 8', 'name': 'Clara Strack', 'initials': 'CS',
        'school': 'Kentucky', 'pos': 'C', 'height': '6-5',
        'sr': 'https://www.sports-reference.com/cbb/players/clara-strack-1.html',
        'full': {'season': '2025-26', 'school': 'Kentucky', 'g': 36, 'pts': '16.9', 'reb': '10.1', 'ast': '1.9', 'stl': '1.2', 'blk': '2.5', 'fg': '.482'},
        'early': {'g': 2, 'pts': '14.0', 'reb': '9.5', 'ast': '2.5', 'school': 'Kentucky'},
        'note': 'Listed 11th on that board, in all 8 mocks. The board\'s 10th name, Taliah Scott, was in 1 of 8 mocks and had no school, so she is not carded here.',
    },
]

# Wikimedia Commons files, CC BY or CC BY-SA. S'Mya Nichols has no such file.
PROSPECT_PHOTOS = {
    'JuJu Watkins': {
        'src': '/images/articles/wnba-draft-lottery-2027/juju-watkins.webp',
        'alt': 'JuJu Watkins smiling, seated in a gray T-shirt',
        'author': 'All-Pro Reels',
        'page': 'https://commons.wikimedia.org/wiki/File:JuJu_Watkins_2025.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
    'Madison Booker': {
        'src': '/images/articles/wnba-draft-lottery-2027/madison-booker.webp',
        'alt': 'Madison Booker in a Texas jersey',
        'author': 'Gamecock Central',
        'page': 'https://commons.wikimedia.org/wiki/File:Madison_Booker.jpg',
        'license': 'CC BY 2.0',
        'license_href': 'https://creativecommons.org/licenses/by/2.0/',
    },
    'Hannah Hidalgo': {
        'src': '/images/articles/wnba-draft-lottery-2027/hannah-hidalgo.webp',
        'alt': 'Hannah Hidalgo in a Notre Dame jersey',
        'author': 'Hameltion',
        'page': 'https://commons.wikimedia.org/wiki/File:UNC_vs_ND_(Jan_2025)_21_(cropped).jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
    'Mikaylah Williams': {
        'src': '/images/articles/wnba-draft-lottery-2027/mikaylah-williams.webp',
        'alt': 'Mikaylah Williams in an LSU jersey',
        'author': 'CCS Pictures',
        'page': 'https://commons.wikimedia.org/wiki/File:Mikaylah_Williams_2025.jpg',
        'license': 'CC BY-SA 2.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/2.0/',
    },
    'MiLaysia Fulwiley': {
        'src': '/images/articles/wnba-draft-lottery-2027/milaysia-fulwiley.webp',
        'alt': 'MiLaysia Fulwiley in a basketball jersey',
        'author': 'Gamecock Central',
        'page': 'https://commons.wikimedia.org/wiki/File:MiLaysia_Fulwiley_(cropped).jpg',
        'license': 'CC BY-SA 2.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/2.0/',
    },
    'Audi Crooks': {
        'src': '/images/articles/wnba-draft-lottery-2027/audi-crooks.webp',
        'alt': 'Audi Crooks in an Iowa State jersey, number 55',
        'author': 'Jar-Lar',
        'page': 'https://commons.wikimedia.org/wiki/File:WBB-IowaState-CentralCollege-2024.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
    'Oluchi Okananwa': {
        'src': '/images/articles/wnba-draft-lottery-2027/oluchi-okananwa.webp',
        'alt': 'Oluchi Okananwa',
        'author': 'Hameltion',
        'page': 'https://commons.wikimedia.org/wiki/File:Oluchi_Okananwa.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
    'Ashlyn Watkins': {
        'src': '/images/articles/wnba-draft-lottery-2027/ashlyn-watkins.webp',
        'alt': 'Ashlyn Watkins',
        'author': 'Gamecock Central',
        'page': 'https://commons.wikimedia.org/wiki/File:Ashlyn_Watkins_(cropped).jpg',
        'license': 'CC BY 2.0',
        'license_href': 'https://creativecommons.org/licenses/by/2.0/',
    },
    'Clara Strack': {
        'src': '/images/articles/wnba-draft-lottery-2027/clara-strack.webp',
        'alt': 'Clara Strack shooting in a Kentucky jersey',
        'author': 'CCS Pictures',
        'page': 'https://commons.wikimedia.org/wiki/File:Clara_Strack.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
}
HERO = {
    'src': '/images/articles/wnba-draft-lottery-2027/hero-1200.webp',
    'alt': 'JuJu Watkins smiling, seated in front of a blue curtain',
    'author': 'All-Pro Reels',
    'page': 'https://commons.wikimedia.org/wiki/File:JuJu_Watkins_2025.jpg',
    'license': 'CC BY-SA 4.0',
    'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    'width': 1200,
    'height': 675,
}
TEAM_MARK = {
    'HOU': 'connecticut-sun',
    'TOR': 'toronto-tempo',
    'WAS': 'washington-mystics',
    'SEA': 'seattle-storm',
    'POR': 'portland-fire',
    'LAL': 'los-angeles-sparks',
}


def e(value) -> str:
    return html.escape(str(value), quote=True)


def pct(fr: Fraction, places: int) -> str:
    quant = Decimal('1').scaleb(-places)
    val = (Decimal(fr.numerator) / Decimal(fr.denominator)) * 100
    return format(val.quantize(quant, rounding=ROUND_HALF_UP), f'.{places}f')


def pair_probability(first: str, second: str) -> Fraction:
    return Fraction(CHANCES[first], TOTAL) * Fraction(CHANCES[second], TOTAL - CHANCES[first])


def assignment(first: str, second: str) -> dict[int, str]:
    rest = [slot for slot in ORDER if slot not in {first, second}]
    out = {1: first, 2: second}
    for offset, slot in enumerate(rest):
        out[3 + offset] = slot
    return out


def pick_probabilities() -> dict[str, list[Fraction]]:
    """P(slot lands pick k), k = 1..7. Each list sums to 1. Each pick sums to 1."""
    table = {slot: [Fraction(0) for _ in range(7)] for slot in ORDER}
    for first in ORDER:
        for second in ORDER:
            if first == second:
                continue
            weight = pair_probability(first, second)
            for pick, slot in assignment(first, second).items():
                table[slot][pick - 1] += weight
    return table


def team_top_two() -> Fraction:
    """Los Angeles has two slots. This is P(at least one of them is pick 1 or 2)."""
    la = {'LAL', 'LAL-PHX'}
    total = Fraction(0)
    for first in ORDER:
        for second in ORDER:
            if first == second:
                continue
            if first in la or second in la:
                total += pair_probability(first, second)
    return total


def matrix_rows(table: dict[str, list[Fraction]]) -> list[dict]:
    rows = []
    for slot in SLOTS:
        probs = table[slot['id']]
        top2 = probs[0] + probs[1]
        expected = sum(Fraction(k + 1) * probs[k] for k in range(7))
        rows.append({
            'slot': slot,
            'probs': probs,
            'top2': top2,
            'expected': expected,
        })
    return rows


def write_csv(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = [
        'slot_id', 'team', 'pick_label', 'team_page', 'original_club', 'record', 'record_scope',
        'chances_of_1000', 'prelottery_order',
    ]
    header += [f'pick_{k}_pct' for k in range(1, 8)]
    header += [f'pick_{k}_fraction' for k in range(1, 8)]
    header += ['top_2_pct', 'top_2_fraction', 'expected_pick', 'method']
    with CSV_PATH.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for index, row in enumerate(rows, start=1):
            slot = row['slot']
            cells = [
                slot['id'], slot['team'], slot['label'], slot['href'], slot['original'],
                slot['record'], slot['record_scope'], slot['chances'], index,
            ]
            cells += [pct(prob, 6) for prob in row['probs']]
            cells += [f'{prob.numerator}/{prob.denominator}' for prob in row['probs']]
            cells += [pct(row['top2'], 6), f"{row['top2'].numerator}/{row['top2'].denominator}"]
            cells += [pct(row['expected'], 4), 'exact enumeration of 42 ordered pairs']
            writer.writerow(cells)


def default_results() -> dict:
    picks = []
    for number in range(1, 16):
        if number <= 7:
            picks.append({'pick': number, 'slot': None, 'team': None, 'label': 'Not drawn yet'})
        else:
            picks.append({'pick': number, 'slot': None, 'team': None, 'label': 'to be confirmed'})
    return {
        'status': 'pending',
        'updated': None,
        'source': '',
        'note': (
            'After the Nov. 15, 2026 drawing, set status to final, set updated to the date, '
            'name the source, and fill picks 1-7 with slot (HOU, TOR, WAS, SEA, POR, LAL, LAL-PHX) '
            'and team. Leave picks 8-15 as to be confirmed until a league draft order names them. '
            'A final file locks the simulator to this order.'
        ),
        'picks': picks,
    }


def write_results() -> None:
    if RESULTS_PATH.is_file():
        try:
            current = json.loads(RESULTS_PATH.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            current = {}
        if current.get('status') == 'final':
            return
    RESULTS_PATH.write_text(json.dumps(default_results(), indent=2) + '\n', encoding='utf-8')


def _norm(name: str) -> str:
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return ' '.join(text.lower().replace("'", '').replace('.', '').split())


def team_needs() -> list[dict]:
    """2026 regular-season minutes from the player file, classes from the free-agency CSV."""
    facts = json.loads((ROOT / 'data' / 'wnba' / 'team-facts.json').read_text(encoding='utf-8'))
    ages = {}
    for slot in SLOTS:
        block = facts['teams'].get(slot['facts']) or {}
        for person, info in (block.get('roster') or {}).items():
            ages[(slot['facts'], _norm(person))] = info.get('age')
    classes = {}
    with (ROOT / 'news' / 'wnba-free-agents-2027' / 'data' / 'wnba-2026-players-by-service-class.csv').open(encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            classes[(row['slug'], row['team_abbr'])] = row
    abbr = {
        'Connecticut Sun': 'CON', 'Toronto Tempo': 'TOR', 'Washington Mystics': 'WSH',
        'Seattle Storm': 'SEA', 'Portland Fire': 'POR', 'Los Angeles Sparks': 'LA',
    }
    buckets: dict[str, dict] = {}
    for slot in SLOTS:
        buckets[slot['id']] = {
            'slot': slot, 'positions': {}, 'players': [], 'minutes': 0.0, 'age_minutes': 0.0, 'age_sum': 0.0,
            'classes': {},
        }
    by_facts = {slot['facts']: slot['id'] for slot in SLOTS}
    # Two LA slots share one roster. Attach minutes to LAL only, then copy the card.
    for path in (ROOT / 'data' / 'wnba' / 'players').glob('*.json'):
        profile = json.loads(path.read_text(encoding='utf-8'))
        player = profile.get('player') or {}
        name = f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
        slug = profile.get('slug') or ''
        position = player.get('position_abbreviation') or player.get('position') or 'Other'
        for season in profile.get('season_stats') or []:
            if season.get('season') != 2026 or season.get('season_type') != 2:
                continue
            team = season.get('team') or {}
            code = abbr.get(team.get('full_name') or '')
            slot_id = by_facts.get(team.get('full_name') or '')
            if slot_id == 'LAL-PHX':
                slot_id = 'LAL'
            if not slot_id or not code:
                continue
            games = float(season.get('games_played') or 0)
            minutes = float(season.get('min') or 0) * games
            points = float(season.get('pts') or 0) * games
            if minutes <= 0 and points <= 0:
                continue
            bucket = buckets[slot_id]
            bucket['minutes'] += minutes
            bucket['positions'][position] = bucket['positions'].get(position, 0.0) + minutes
            age = ages.get((BY_ID[slot_id]['facts'], _norm(name)))
            if isinstance(age, (int, float)):
                bucket['age_minutes'] += minutes
                bucket['age_sum'] += minutes * float(age)
            fa = classes.get((slug, code)) or {}
            bucket['players'].append({
                'name': name, 'slug': slug, 'position': position, 'minutes': minutes,
                'points': points, 'age': age if isinstance(age, (int, float)) else None,
                'klass': fa.get('projected_class') or '',
            })
            if fa:
                cell = bucket['classes'].setdefault(fa['projected_class'], {'minutes': 0.0, 'players': 0})
                cell['minutes'] += float(fa['minutes'] or 0)
                cell['players'] += 1
    cards = []
    for slot in SLOTS:
        source_id = 'LAL' if slot['id'] == 'LAL-PHX' else slot['id']
        if slot['id'] == 'LAL-PHX':
            continue
        bucket = buckets[source_id]
        positions = []
        for position, amount in sorted(bucket['positions'].items(), key=lambda item: -item[1]):
            positions.append({
                'position': position,
                'minutes': int(round(amount)),
                'share': f'{100 * amount / bucket["minutes"]:.1f}',
            })
        age = None
        coverage = 0.0
        if bucket['age_minutes']:
            age = bucket['age_sum'] / bucket['age_minutes']
            coverage = 100 * bucket['age_minutes'] / bucket['minutes']
        leaders = sorted(bucket['players'], key=lambda item: -item['minutes'])[:4]
        class_minutes = sum(cell['minutes'] for cell in bucket['classes'].values()) or 1
        class_rows = []
        for name in ('UFA', 'RFA', 'Reserved'):
            cell = bucket['classes'].get(name)
            if not cell:
                continue
            class_rows.append({
                'name': name,
                'minutes': int(round(cell['minutes'])),
                'players': cell['players'],
                'share': f"{100 * cell['minutes'] / class_minutes:.1f}",
            })
        cards.append({
            'slot': slot,
            'minutes': int(round(bucket['minutes'])),
            'players': len(bucket['players']),
            'positions': positions,
            'age': None if age is None else f'{age:.1f}',
            'age_coverage': f'{coverage:.0f}',
            'classes': class_rows,
            'leaders': leaders,
        })
    return cards


CLASS_WORDS = {
    'UFA': 'unrestricted if the contract ends',
    'RFA': 'restricted if a qualifying offer is sent',
    'Reserved': 'reserved if a qualifying offer is sent',
}


def photo_credit(spec: dict) -> str:
    return (
        'Photo: '
        f'<a class="inline-link" href="{e(spec["page"])}" target="_blank" rel="noopener">{e(spec["author"])}</a>, '
        f'<a class="inline-link" href="{e(spec["license_href"])}" target="_blank" rel="noopener">{e(spec["license"])}</a>, via '
        f'<a class="inline-link" href="{e(spec["page"])}" target="_blank" rel="noopener">Wikimedia Commons</a>'
    )


_PHOTO_SRC: dict[str, str] | None = None
POS_WORD = {'G': 'Guard', 'F': 'Forward', 'C': 'Center'}


def _photograph_src(slug: str) -> str:
    global _PHOTO_SRC
    if _PHOTO_SRC is None:
        found = {}
        path = ROOT / 'content' / 'player-illustrations.json'
        if path.is_file():
            data = json.loads(path.read_text(encoding='utf-8'))
            for row in data.get('portraits') or []:
                src = str(row.get('src') or '')
                if row.get('approved') and row.get('kind') == 'photograph' and src.startswith('/'):
                    found[row['slug']] = src
        _PHOTO_SRC = found
    return _PHOTO_SRC.get(slug, '')


def _initials(name: str) -> str:
    parts = [part for part in name.split() if part[:1].isalpha()]
    if not parts:
        return '?'
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')).upper()


def _player_face(player: dict) -> str:
    src = _photograph_src(player['slug']) if player['slug'] else ''
    if src:
        return (
            f'<img class="face" src="{e(src)}" alt="" width="80" height="80" '
            'loading="lazy" decoding="async">'
        )
    return f'<span class="av" aria-hidden="true">{e(_initials(player["name"]))}</span>'


def _player_row(player: dict) -> str:
    name = e(player['name'])
    if player['slug']:
        name = f'<a href="/wnba/{e(player["slug"])}/">{name}</a>'
    bits = [player['position'] or 'Other']
    if player['klass']:
        bits.append(player['klass'])
    bits.append(f"{int(round(player['minutes'])):,} minutes")
    bits.append(f"{int(round(player['points'])):,} points")
    return (
        f'<li>{_player_face(player)}<div class="need-who">{name}'
        f'<span class="need-meta">{e(" · ".join(bits))}</span></div></li>'
    )


def _position_bar(positions: list[dict]) -> str:
    if not positions:
        return '<div class="need-tile"><b>n/a</b><span>Minutes</span></div>'
    segments = []
    spoken = []
    caption = []
    for row in positions:
        word = POS_WORD.get(row['position'], row['position'])
        spoken.append(f"{word} {row['share']}%")
        caption.append(f"{row['position']} {row['share']}")
        grow = float(row['share'])
        segments.append(
            f'<span class="pos-{e(row["position"])}" style="flex:{grow:.4f} {grow:.4f} 0"></span>'
        )
    return (
        '<div class="need-tile need-tile-bar">'
        f'<span class="pos-bar" role="img" aria-label="{e(", ".join(spoken))} of minutes">'
        f'{"".join(segments)}</span>'
        f'<span>{e(" · ".join(caption))}</span></div>'
    )


def _takeaway(card: dict, phoenix_top2: str) -> str:
    slot = card['slot']
    lead = card['positions'][0] if card['positions'] else None
    if lead:
        word = {'G': 'Guards', 'F': 'Forwards', 'C': 'Centers'}.get(lead['position'], lead['position'])
        first = f"{word} logged {lead['share']}% of these minutes."
    else:
        first = 'The player file has no position tags for these minutes.'
    ufa = next((row for row in card['classes'] if row['name'] == 'UFA'), None)
    count = ufa['players'] if ufa else 0
    if count == 1:
        second = '1 player row is unrestricted if the contract ends.'
    elif count:
        second = f'{count} player rows are unrestricted if the contract ends.'
    else:
        second = 'The free-agency file lists no unrestricted row for this club.'
    extra = ''
    if slot['id'] == 'HOU':
        extra = ' These minutes are the 2026 Connecticut Sun. The club plays 2027 as the Houston Comets.'
    elif slot['id'] == 'WAS':
        extra = " The lottery pick is Chicago's. This card is the Mystics roster that would make the selection."
    elif slot['id'] == 'LAL':
        extra = (
            ' Both Los Angeles lottery slots use this roster. '
            f"Phoenix's pick has a {phoenix_top2}% chance at a top-two selection."
        )
    return first + ' ' + second + extra


def needs_html(cards: list[dict], rows: list[dict]) -> str:
    by_id = {row['slot']['id']: row for row in rows}
    phoenix_top2 = pct(by_id['LAL-PHX']['top2'], 1)
    blocks = []
    for card in cards:
        slot = card['slot']
        mark = _slot_mark(slot)
        if mark:
            focal = {'TOR': 'center 75%', 'POR': 'center 40%'}.get(slot['id'], 'center 20%')
            photo = (
                '<figure class="lead-photo">'
                f'<img src="{e(mark["src"])}" alt="{e(mark["alt"])}" style="object-position:{focal}" '
                'width="1200" height="675" decoding="async" loading="lazy">'
                f'<figcaption>{photo_credit(mark)}</figcaption></figure>'
            )
            avatar = (
                f'<img class="lot-avatar" src="{e(mark["src"])}" alt="" style="object-position:{focal}" '
                'width="64" height="64" loading="lazy" decoding="async">'
            )
        else:
            photo = ''
            avatar = f'<span class="lot-avatar lot-initials" aria-hidden="true">{e(slot["circle"][:3])}</span>'
        top2 = pct(by_id[slot['id']]['top2'], 1)
        top_label = 'Top 2, own' if slot['id'] == 'LAL' else 'Top 2'
        age = card['age'] or 'n/a'
        ufa = next((row for row in card['classes'] if row['name'] == 'UFA'), None)
        ufa_count = ufa['players'] if ufa else 0
        players = ''.join(_player_row(player) for player in card['leaders'])
        blocks.append(
            '<article class="need-card">'
            f'{photo}<div class="need-body">'
            f'<div class="need-head">{avatar}<h3><a href="{e(slot["href"])}">{e(slot["team"])}</a></h3></div>'
            '<div class="need-tiles">'
            f'<div class="need-tile"><b>{top2}%</b><span>{top_label}</span></div>'
            f'<div class="need-tile"><b>{e(age)}</b><span>Weighted age</span></div>'
            f'{_position_bar(card["positions"])}'
            f'<div class="need-tile"><b>{ufa_count}</b><span>Unrestricted</span></div>'
            '</div>'
            f'<p class="need-take">{e(_takeaway(card, phoenix_top2))}</p>'
            f'<ul class="need-players">{players}</ul>'
            '</div></article>'
        )
    return '<div class="need-grid">' + ''.join(blocks) + '</div>'


def prospects_html() -> str:
    cards = []
    for prospect in PROSPECTS:
        full = prospect['full']
        early = prospect['early']
        note = f' {e(prospect["note"])}' if prospect['note'] else ''
        photo = PROSPECT_PHOTOS.get(prospect['name'])
        if photo:
            face = (
                f'<img class="face" src="{e(photo["src"])}" alt="{e(photo["alt"])}" '
                f'width="480" height="480" loading="lazy" decoding="async">'
            )
            credit = f'<p class="photo-credit">{photo_credit(photo)}</p>'
        else:
            face = f'<span class="av" aria-hidden="true">{e(prospect["initials"])}</span>'
            credit = '<p class="photo-credit">No freely licensed photo was found, so this card uses initials.</p>'
        cards.append(
            f'<article class="prospect">{face}'
            f'<div><h3>{prospect["board"]}. {e(prospect["name"])}</h3>'
            f'{credit}'
            f'<p>{e(prospect["pos"])}, {e(prospect["height"])}, {e(prospect["school"])}. '
            f'Ultimate Big Board rank {prospect["board"]}, {e(prospect["mocks"])} mocks.</p>'
            f'<p>{e(full["season"])} at {e(full["school"])}: {full["g"]} games, {e(full["pts"])} points, '
            f'{e(full["reb"])} rebounds, {e(full["ast"])} assists, {e(full["stl"])} steals, {e(full["blk"])} blocks, '
            f'{e(full["fg"])} from the field. '
            f'<a href="{e(prospect["sr"])}" target="_blank" rel="noopener">Sports-Reference</a>.</p>'
            f'<p>2026-27 at {e(early["school"])}, {early["g"]} game{"s" if early["g"] != 1 else ""} posted by Nov. 9, 2026: '
            f'{e(early["pts"])} points, {e(early["reb"])} rebounds, {e(early["ast"])} assists.{note}</p></div></article>'
        )
    return '<div class="prospect-list">' + ''.join(cards) + '</div>'


def _slot_mark(slot: dict) -> dict | None:
    key = TEAM_MARK.get(slot['id'])
    if not key and slot['id'].startswith('LAL'):
        key = TEAM_MARK['LAL']
    return team_hub.VISUALS.get(key or '')


def odds_cards(rows: list[dict]) -> str:
    """Phone cards: identity, two headline odds, and one bar. Zeros stay in the label only."""
    cards = []
    for row in rows:
        slot = row['slot']
        mark = _slot_mark(slot)
        if mark:
            avatar = (
                f'<img class="lot-avatar" src="{e(mark["src"])}" alt="" '
                f'width="64" height="64" loading="lazy" decoding="async">'
            )
        else:
            avatar = f'<span class="lot-avatar lot-initials" aria-hidden="true">{e(slot["circle"][:3])}</span>'
        legend_bits = []
        segments = []
        spoken = [f'{slot["label"]}, record {slot["record"]}']
        for index, prob in enumerate(row['probs'], start=1):
            shown = pct(prob, 1)
            spoken.append(f'Pick {index} {shown}%')
            if shown == '0.0':
                continue
            legend_bits.append(f'<span>#{index} {shown}</span>')
            grow = float(prob)
            segments.append(
                f'<span class="lot-p{index}" style="flex:{grow:.6f} {grow:.6f} 0"></span>'
            )
        spoken.append(f'Top 2 {pct(row["top2"], 1)}%')
        cards.append(
            '<article class="lot-card">'
            f'<div class="lot-id">{avatar}'
            f'<a href="{e(slot["href"])}">{e(slot["label"])}</a>'
            f'<span class="lot-rec">{e(slot["record"])}</span></div>'
            f'<p class="lot-stats"><span>Top 2: {pct(row["top2"], 1)}%</span>'
            f'<span>No. 1: {pct(row["probs"][0], 1)}%</span></p>'
            f'<div class="lot-bar" role="img" aria-label="{e(". ".join(spoken))}">'
            f'{"".join(segments)}</div>'
            f'<p class="lot-legend">{"".join(legend_bits)}</p>'
            '</article>'
        )
    return '<div class="lot-odds-cards">' + ''.join(cards) + '</div>'


def odds_table(rows: list[dict]) -> str:
    head = ''.join(f'<th scope="col">Pick {k}</th>' for k in range(1, 8))
    body = []
    for row in rows:
        slot = row['slot']
        cells = [
            f'<th scope="row"><a href="{e(slot["href"])}">{e(slot["label"])}</a></th>',
            f'<td data-label="Record">{e(slot["record"])}</td>',
            f'<td data-label="Chances (of 1,000)">{slot["chances"]}</td>',
        ]
        for index, prob in enumerate(row['probs'], start=1):
            cells.append(f'<td data-label="Pick {index}">{pct(prob, 1)}%</td>')
        cells.append(f'<td data-label="Top 2">{pct(row["top2"], 1)}%</td>')
        body.append('<tr>' + ''.join(cells) + '</tr>')
    table = (
        '<div class="table-wrap" data-fcb-data-table><table class="fcb-cards fcb-data-table">'
        '<thead><tr><th scope="col">Slot</th><th scope="col">Record</th>'
        f'<th scope="col">Chances</th>{head}<th scope="col">Top 2</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )
    return f'<div class="lot-odds">{table}{odds_cards(rows)}</div>'


def faq_pairs(rows: list[dict]) -> list[tuple[str, str]]:
    hou = next(row for row in rows if row['slot']['id'] == 'HOU')
    return [
        (
            'When is the 2027 WNBA Draft Lottery?',
            'Sunday, Nov. 15, 2026, from 7:30 to 8:00 p.m. ET (4:30 to 5:00 p.m. PT). '
            'It is the 26th annual WNBA Draft Lottery, presented by State Street Investment Management SPY.',
        ),
        (
            'When is the 2027 WNBA Draft?',
            'Monday, April 12, 2027. The lottery sets picks 1 and 2 only. '
            'The expansion draft for Portland and Toronto was April 3, 2026. That draft already happened.',
        ),
        (
            'How does the WNBA draft lottery work?',
            'Fourteen balls numbered 1 through 14 go into the machine, and four are drawn. '
            'There are 1,001 four-ball combinations, and 1,000 of them are assigned. '
            'The slot that holds the combination gets the first pick. The balls go back in, and the draw is repeated for the second pick. '
            'An unassigned combination, or one that belongs to the slot that already won, is redrawn. '
            'The five slots that were not drawn then take picks 3 through 7 in pre-lottery order.',
        ),
        (
            'Who has the best odds?',
            f'Houston and Toronto. Each has 329 of 1,000 combinations, a {pct(hou["probs"][0], 1)}% chance at the first pick '
            f'and a {pct(hou["top2"], 1)}% chance at a top-two pick. Los Angeles, counting both of its picks, '
            'has a 3.6% chance at No. 1.',
        ),
        (
            'What does the Houston and Toronto tie mean?',
            'Both clubs are at .250. Houston is 22-66 across 2025 and 2026. Toronto, an expansion team, is 11-33 in 2026 only. '
            'The first tiebreaker is the 2026 head-to-head. The Sun went 1-2 against the Tempo: Toronto won 106-102 on June 10 and 101-97 on June 19, '
            'and Connecticut won 95-81 on Sept. 24. Houston is first in the pre-lottery order, so the latest pick Houston can land is No. 3. '
            'Toronto is second, so the latest pick Toronto can land is No. 4.',
        ),
        (
            'Where can I watch the lottery?',
            'ESPN in the United States, after UConn vs. Louisville, and TSN in Canada. '
            'The Oct. 28 release does not name a separate streaming service. '
            'Bethany Donaphin, head of league operations, reveals the results. Ernst & Young oversees the drawing.',
        ),
        (
            'Will JuJu Watkins be the No. 1 pick?',
            'She is the consensus No. 1 on the Ultimate Big Board snapshot of Oct. 29, 2026: 8 of 8 mocks, weighted average 1.0. '
            'That is a projection, not the draft. She is on the 2026-27 USC roster. Sports-Reference had one game posted by Nov. 9, 2026. '
            'She can stay in school. This page does not say she will be the first pick.',
        ),
    ]


def faq_html(pairs: list[tuple[str, str]]) -> str:
    blocks = []
    for question, answer in pairs:
        blocks.append(f'<h3>{e(question)}</h3><p>{e(answer)}</p>')
    return '<section id="faq"><h2 class="section-title">Questions</h2>' + ''.join(blocks) + '</section>'


def faq_jsonld(pairs: list[tuple[str, str]]) -> str:
    entity = []
    for question, answer in pairs:
        entity.append({
            '@type': 'Question',
            'name': question,
            'acceptedAnswer': {'@type': 'Answer', 'text': answer},
        })
    payload = {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': entity}
    return '<script type="application/ld+json">' + json.dumps(payload, ensure_ascii=False) + '</script>'


def dataset_jsonld() -> str:
    payload = {
        '@context': 'https://schema.org',
        '@type': 'Dataset',
        'name': '2027 WNBA Draft Lottery pick probabilities',
        'description': (
            'Exact probability that each 2027 WNBA Draft Lottery slot lands picks 1 through 7, '
            'from the 1,000 combinations in the Oct. 28, 2026 league release.'
        ),
        'url': BASE + ROUTE,
        'creator': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': BASE + '/'},
        'license': 'https://creativecommons.org/publicdomain/zero/1.0/',
        'isAccessibleForFree': True,
        'dateModified': PUBLISHED,
        'isBasedOn': 'https://www.wnba.com/news/wnba-draft-lottery-2027-sunday-november-15',
        'distribution': [{
            '@type': 'DataDownload',
            'encodingFormat': 'text/csv',
            'contentUrl': BASE + '/data/wnba-draft-lottery-2027-odds.csv',
        }],
    }
    return '<script type="application/ld+json">' + json.dumps(payload) + '</script>'


def breadcrumb_jsonld() -> str:
    payload = {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': 'WNBA', 'item': BASE + '/wnba/'},
            {'@type': 'ListItem', 'position': 3, 'name': '2027 Draft Lottery', 'item': BASE + ROUTE},
        ],
    }
    return '<script type="application/ld+json">' + json.dumps(payload) + '</script>'


SIM_JS = r"""
<script>
(function () {
  var SLOTS = __SLOTS__;
  var ORDER = SLOTS.map(function (slot) { return slot.id; });
  var SEED = __SEED__;
  var board = document.getElementById('draw-board');
  var summary = document.getElementById('draw-summary');
  var one = document.getElementById('draw-one');
  var many = document.getElementById('draw-many');
  var reset = document.getElementById('draw-reset');
  var liveList = document.getElementById('live-order');
  var liveStatus = document.getElementById('live-status');

  function lcg(seed) {
    var state = seed >>> 0;
    return function () {
      state = (Math.imul(1664525, state) + 1013904223) >>> 0;
      return state;
    };
  }
  function below(next, n) {
    var limit = Math.floor(0x100000000 / n) * n;
    var x;
    do { x = next(); } while (x >= limit);
    return x % n;
  }
  function pick(next, items) {
    var total = 0;
    for (var i = 0; i < items.length; i++) total += items[i].chances;
    var r = below(next, total), acc = 0;
    for (var j = 0; j < items.length; j++) {
      acc += items[j].chances;
      if (r < acc) return items[j];
    }
    return items[items.length - 1];
  }
  function draw(next) {
    var pool = SLOTS.slice();
    var first = pick(next, pool);
    pool = pool.filter(function (slot) { return slot.id !== first.id; });
    var second = pick(next, pool);
    var used = {};
    used[first.id] = true;
    used[second.id] = true;
    var rest = [];
    for (var i = 0; i < ORDER.length; i++) {
      if (!used[ORDER[i]]) {
        rest.push(SLOTS.filter(function (slot) { return slot.id === ORDER[i]; })[0]);
      }
    }
    return [first, second].concat(rest);
  }
  function row(pickNo, slot) {
    return '<div class="pick-row"><span class="pick-no">' + pickNo + '</span>' +
      '<span class="av" aria-hidden="true">' + slot.circle + '</span>' +
      '<span class="pick-name">' + slot.label + '</span></div>';
  }
  function show(order, text) {
    summary.textContent = text;
    board.innerHTML = order.map(function (slot, index) { return row(index + 1, slot); }).join('');
  }
  function randomDraw() {
    var next = lcg((Math.floor(Math.random() * 0x7fffffff) ^ Date.now()) >>> 0);
    show(draw(next), 'One draw.');
  }
  function manyDraw() {
    var next = lcg(SEED);
    var counts = {};
    var bestKey = '', bestN = 0, best = null;
    for (var n = 0; n < 10000; n++) {
      var order = draw(next);
      var key = order.map(function (slot) { return slot.id; }).join(',');
      counts[key] = (counts[key] || 0) + 1;
      if (counts[key] > bestN) { bestN = counts[key]; bestKey = key; best = order; }
    }
    show(best, 'Most common order in 10,000 draws with seed ' + SEED + '. It came up ' + bestN + ' times.');
  }
  function clearBoard() {
    summary.textContent = 'No draw yet.';
    board.innerHTML = '';
  }
  function lock(order, source) {
    show(order, 'Locked to the published result' + (source ? ' (' + source + ')' : '') + '.');
    one.disabled = true;
    many.disabled = true;
    reset.disabled = true;
  }
  one.addEventListener('click', randomDraw);
  many.addEventListener('click', manyDraw);
  reset.addEventListener('click', clearBoard);

  function applyLive(data) {
    if (!data || !data.picks) return;
    var items = data.picks.slice().sort(function (a, b) { return a.pick - b.pick; });
    liveList.hidden = false;
    liveList.innerHTML = items.map(function (pick) {
      var text = pick.team || pick.label || 'to be confirmed';
      return '<li>Pick ' + pick.pick + ': ' + text + '</li>';
    }).join('');
    if (data.status !== 'final') {
      liveStatus.textContent = 'The drawing has not been entered. Picks 8 through 15 stay to be confirmed.';
      return;
    }
    var byId = {};
    SLOTS.forEach(function (slot) { byId[slot.id] = slot; });
    var order = [];
    for (var n = 1; n <= 7; n++) {
      var found = items.filter(function (pick) { return pick.pick === n; })[0];
      if (!found || !byId[found.slot]) return;
      order.push(byId[found.slot]);
    }
    liveStatus.textContent = 'Published result' + (data.updated ? ', updated ' + data.updated : '') + '.';
    lock(order, data.source || '');
  }
  fetch('/data/wnba-draft-lottery-2027-results.json', {cache: 'no-store'})
    .then(function (res) { return res.ok ? res.json() : null; })
    .then(applyLive)
    .catch(function () {});
})();
</script>
"""


def sim_script() -> str:
    payload = [
        {'id': slot['id'], 'label': slot['label'], 'circle': slot['circle'], 'chances': slot['chances']}
        for slot in SLOTS
    ]
    return SIM_JS.replace('__SLOTS__', json.dumps(payload)).replace('__SEED__', str(SEED))


def live_html() -> str:
    items = []
    for number in range(1, 16):
        label = 'Not drawn yet' if number <= 7 else 'to be confirmed'
        items.append(f'<li>Pick {number}: {label}</li>')
    return (
        '<section id="live-results"><h2 class="section-title">Live results</h2>'
        '<p id="live-status">The drawing has not been entered. Picks 8 through 15 stay to be confirmed.</p>'
        f'<ol id="live-order">{"".join(items)}</ol>'
        '<p class="table-note">This list reads the results file on this site, data/wnba-draft-lottery-2027-results.json. '
        'On Nov. 15, set status to final and fill picks 1 through 7. The simulator then locks to that order. '
        'Picks 8 through 15 are to be confirmed: the Oct. 28 release does not publish them, Indiana and Washington both finished 28-16, '
        'and the 2025 Atkins deal was announced as swap rights rather than a finished draft order.</p></section>'
    )


def page(rows: list[dict], cards: list[dict]) -> str:
    pairs = faq_pairs(rows)
    la_top = team_top_two()
    hero_figure = (
        '<figure class="lead-photo"><picture>'
        f'<source srcset="{e(HERO["src"])} 1200w" type="image/webp" sizes="(max-width: 900px) calc(94vw - 40px), 842px">'
        f'<img src="{e(HERO["src"])}" alt="{e(HERO["alt"])}" style="object-position:center 30%" '
        f'width="{HERO["width"]}" height="{HERO["height"]}" decoding="async" fetchpriority="high">'
        f'</picture><figcaption>{photo_credit(HERO)}</figcaption></figure>'
    )
    hero = (
        hero_figure
        + '<p class="lead">Sunday, Nov. 15, 2026, 4:30 to 5:00 p.m. PT (7:30 to 8:00 p.m. ET), '
        'on ESPN after UConn vs. Louisville and on TSN in Canada. This is the lottery, not the April 12, 2027 draft, '
        'and not the April 3, 2026 expansion draft. Data through Oct. 28, 2026.</p>'
        '<section id="simulator"><h2 class="section-title">Lottery simulator</h2>'
        '<p>One draw is random. The 10,000-draw button uses seed 20261115.</p>'
        '<div class="lot-actions">'
        '<button type="button" class="button primary" id="draw-one">One draw</button>'
        '<button type="button" class="button" id="draw-many">10,000 draws</button>'
        '<button type="button" class="button" id="draw-reset">Reset</button>'
        '</div><p id="draw-summary">No draw yet.</p><div id="draw-board"></div></section>'
        '<h2 class="section-title" id="probabilities">Chance of every pick</h2>'
        '<p>Houston and Toronto each hold 329 of 1,000 combinations.</p>'
    )
    methods = (
        '<p class="table-note">Source: <a href="https://www.wnba.com/news/wnba-draft-lottery-2027-sunday-november-15" target="_blank" rel="noopener">WNBA release, Oct. 28, 2026</a>. '
        'Data through Oct. 28, 2026. Methods: exact enumeration of the 42 orders for picks 1 and 2. '
        f'P(second | first) = remaining chances / (1,000 minus the winner\'s chances). '
        f'Los Angeles, counting both picks, has an {pct(la_top, 1)}% chance that at least one of them is in the top two. '
        'Free to use and republish (CC0). '
        '<a href="/data/wnba-draft-lottery-2027-odds.csv">Download CSV (CC0)</a>.</p>'
    )
    body = f'''<main id="content" class="shell article-wrap">
<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a><span aria-hidden="true">/</span><a href="/wnba/">WNBA</a><span aria-hidden="true">/</span><span>2027 Draft Lottery</span></nav>
<article class="article"><div class="meta-row"><span class="cat">WNBA</span><span class="divider"></span><span>Full Court Buckets</span></div>
<h1>{e(TITLE)}</h1>
<div class="byline-row"><a class="byline" href="/authors/ryan-moalemi/"><picture><source srcset="/images/authors/ryan-moalemi-photo-byline.webp" type="image/webp"><img src="/images/authors/ryan-moalemi-photo-byline.jpg?v=d51e90ea6c01" alt="Ryan Moalemi" width="80" height="80" decoding="async" loading="lazy"></picture><span>By Ryan Moalemi</span></a><time class="article-date" datetime="{PUBLISHED}">November 9, 2026</time></div>
{hero}
{odds_table(rows)}
{methods}
<section id="how"><h2 class="section-title">How the drawing works</h2>
<p>The league puts 14 balls, numbered 1 through 14, in the machine and draws four. That is 1,001 combinations. One combination is left unassigned, so 1,000 are in play. The slot that owns the combination gets pick 1. The four balls go back in, and the same draw sets pick 2. If the machine hits the unassigned combination, or a combination owned by the slot that already won, it draws again.</p>
<p>Picks 3 through 7 are not drawn. They follow the pre-lottery order among the five slots still waiting. That order, worst record first, is Houston, Toronto, Washington (Chicago's pick), Seattle, Portland, Los Angeles (own pick), Los Angeles (Phoenix's pick).</p>
<p>Five of the records are two seasons added together, 2025 and 2026: Chicago 26-62, Houston 22-66, Los Angeles 37-51, Phoenix 43-45, and Seattle 31-57. Portland and Toronto were expansion teams in 2026, so their odds use 2026 only: Portland 17-27 and Toronto 11-33. Houston and Toronto both land at .250, so each receives 329 combinations.</p>
<h3>The tie</h3>
<p>The release uses the 2026 head-to-head as the first tiebreaker. Houston, then the Connecticut Sun, went 1-2 against Toronto. The three games are in the site schedule file, which was taken from the WNBA schedule: Toronto 106, Connecticut 102 on June 10; Toronto 101, Connecticut 97 on June 19; Connecticut 95, Toronto 81 on Sept. 24. Houston therefore sits ahead of Toronto. Houston's latest possible pick is No. 3. Toronto's latest possible pick is No. 4.</p>
<h3>The traded picks</h3>
<p>Washington holds Chicago's pick. The Oct. 28 footnote says Chicago traded its own 2027 first-round pick to Washington for Ariel Atkins on Feb. 23, 2025. The team releases that day describe the first-round piece as the right to swap Washington's own 2027 first with Chicago's own 2027 first, plus Chicago's 2027 second-round pick. Those are the <a href="https://mystics.wnba.com/news/washington-mystics-acquire-third-overall-picki-in-the-wnba-draft" target="_blank" rel="noopener">Mystics release</a> and the <a href="https://www.wnba.com/news/chicago-sky-acquire-ariel-atkins" target="_blank" rel="noopener">league release on the Sky deal</a>. This page follows the Oct. 28 lottery assignment for the combinations. It does not assign Washington's own first-rounder.</p>
<p>Los Angeles holds Phoenix's pick. The <a href="https://www.wnba.com/news/rapid-reactions-trade-deadline-2026" target="_blank" rel="noopener">league's trade-deadline note</a> says Los Angeles sent Kelsey Plum to Phoenix for Monique Akoa Makani, a 2027 first-round pick, and a 2028 second-round pick. The lottery footnote dates that deal Aug. 2, 2026.</p>
<p>Houston is the relocated Connecticut Sun. The <a href="https://www.wnba.com/news/wnba-nba-approve-connecticut-sun-sale" target="_blank" rel="noopener">May 13, 2026 sale release</a> says the club stays in Connecticut for 2026 and moves to Houston for 2027, under Tilman J. Fertitta. The team URL on this site is still <a href="/wnba/teams/connecticut-sun/">/wnba/teams/connecticut-sun/</a>.</p>
<p>Bethany Donaphin, head of league operations, reveals the result on ESPN. Ernst &amp; Young oversees the drawing. The presentation name on the release is State Street Investment Management SPY. ESPN is airing the lottery for the 15th year in a row.</p>
</section>
<section id="needs"><h2 class="section-title">What the 2026 rosters look like</h2>
<p>Each card is the 2026 roster tied to that lottery pick.</p>
{needs_html(cards, rows)}
<p class="table-note">Minutes are 2026 regular-season per-game averages times games played, from the player file checked Nov. 8, 2026. Weighted age is the Oct. 28, 2026 WNBA.com roster snapshot in that file, weighted by those minutes. The bar splits the same minutes by position. Unrestricted is the count of player rows the <a href="/news/wnba-free-agents-2027/">2027 free-agency page</a> marks UFA if the contract ends. Restricted and reserved rows still need a qualifying offer. That file is not the league's February list. The four names on each card are the highest minute totals. Headshots are approved player photographs already on this site. A name with initials has no approved photograph.</p>
</section>
<section id="prospects"><h2 class="section-title">Early prospect board</h2>
<p>Order is the <a href="https://ultimatebigboard.com/wnba/2027/big-board/" target="_blank" rel="noopener">Ultimate Big Board</a> snapshot calculated Oct. 29, 2026. It is a consensus of mocks, not a draft. Every counting line is from the linked Sports-Reference page, read Nov. 9, 2026. The 2026-27 lines are one or two games. Headshots are Wikimedia Commons photos credited on each card. S'Mya Nichols has no freely licensed photo, so her card uses initials.</p>
{prospects_html()}
</section>
{live_html()}
<section id="playoff-records"><h2 class="section-title">2026 records behind picks 8 through 15</h2>
<p>The eight clubs in the top eight of the <a href="/standings/">2026 standings</a> finished the regular season, in the WNBA schedule file, at Minnesota 33-11, Golden State 32-12, Las Vegas 31-13, Atlanta 30-14, Washington 28-16, Indiana 28-16, Dallas 27-17, and New York 26-18. Those are records, not pick numbers. Washington and Indiana are tied, and the lottery release does not publish the rest of round 1.</p>
</section>
<section id="related"><h2 class="section-title">Related pages</h2>
<ul>
<li><a href="/news/wnba-free-agents-2027/">2027 free agents</a></li>
<li><a href="/news/wnba-expansion-teams/">Portland and Toronto expansion</a></li>
<li><a href="/wnba/teams/portland-fire/">Portland Fire</a></li>
<li><a href="/wnba/teams/toronto-tempo/">Toronto Tempo</a></li>
<li><a href="/wnba/teams/seattle-storm/">Seattle Storm</a></li>
<li><a href="/wnba/teams/los-angeles-sparks/">Los Angeles Sparks</a></li>
<li><a href="/wnba/teams/washington-mystics/">Washington Mystics</a></li>
<li><a href="/wnba/teams/connecticut-sun/">Connecticut Sun (Houston in 2027)</a></li>
</ul>
</section>
{faq_html(pairs)}
<section id="sources"><h2 class="section-title">Sources</h2>
<ul>
<li><a href="https://www.wnba.com/news/wnba-draft-lottery-2027-sunday-november-15" target="_blank" rel="noopener">WNBA Draft Lottery 2027 release, Oct. 28, 2026</a></li>
<li><a href="https://www.wnba.com/news/wnba-nba-approve-connecticut-sun-sale" target="_blank" rel="noopener">WNBA and NBA approve the Sun sale, May 13, 2026</a></li>
<li><a href="https://mystics.wnba.com/news/washington-mystics-acquire-third-overall-picki-in-the-wnba-draft" target="_blank" rel="noopener">Mystics on the Ariel Atkins trade, Feb. 23, 2025</a></li>
<li><a href="https://www.wnba.com/news/chicago-sky-acquire-ariel-atkins" target="_blank" rel="noopener">League release on the Sky and Ariel Atkins, Feb. 23, 2025</a></li>
<li><a href="https://www.wnba.com/news/rapid-reactions-trade-deadline-2026" target="_blank" rel="noopener">League trade-deadline note on Kelsey Plum, 2026</a></li>
<li>The 2026 WNBA schedule file on this site, taken from the league schedule, for the three Sun-Tempo games and the 2026 records</li>
<li><a href="/news/wnba-free-agents-2027/data/wnba-2026-players-by-service-class.csv">2026 players by service class (CSV)</a></li>
<li>WNBA.com roster snapshot saved on this site, checked Oct. 28, 2026, for ages</li>
<li>Sports-Reference player pages linked on each prospect card</li>
<li><a href="https://ultimatebigboard.com/wnba/2027/big-board/" target="_blank" rel="noopener">Ultimate Big Board, 2027 WNBA consensus, snapshot Oct. 29, 2026</a></li>
<li><a href="/news/wnba-expansion-teams/">Expansion draft, April 3, 2026</a></li>
</ul>
</section>
<p class="how-made">How this page was made: <a href="/authors/ryan-moalemi/">Ryan Moalemi</a> writes Full Court Buckets pages, sometimes with AI assistance. The pick probabilities are enumerated from the league release. Roster minutes come from the site's 2026 player file. College lines are the Sports-Reference pages linked above. <a href="/how-we-make-full-court-buckets/">How we make Full Court Buckets</a>.</p>
</article></main>
{sim_script()}
'''
    social = (
        f'<meta property="og:title" content="{e(TITLE)}">'
        f'<meta property="og:description" content="{e(DESCRIPTION)}">'
        f'<meta property="og:url" content="{BASE}{ROUTE}">'
        '<meta property="og:type" content="article">'
        '<meta property="og:site_name" content="Full Court Buckets">'
        f'<meta property="og:image" content="{BASE}{HERO["src"]}">'
        f'<meta property="og:image:width" content="{HERO["width"]}">'
        f'<meta property="og:image:height" content="{HERO["height"]}">'
        f'<meta property="og:image:alt" content="{e(HERO["alt"])}">'
        '<meta name="twitter:card" content="summary_large_image">'
        '<meta name="twitter:site" content="@fullcourtbucket">'
        f'<meta name="twitter:title" content="{e(TITLE)}">'
        f'<meta name="twitter:description" content="{e(DESCRIPTION)}">'
        f'<meta name="twitter:image" content="{BASE}{HERO["src"]}">'
        f'<meta name="twitter:image:alt" content="{e(HERO["alt"])}">'
    )
    style = '''<style>
.shell{width:min(1240px,94vw);margin:auto}
.article-wrap{padding:32px 0 80px}
.article{box-sizing:border-box;max-width:900px;margin:0 auto;background:#fff;border:1px solid var(--line,#e2ddd6);padding:28px;box-shadow:0 1px 3px rgba(40,20,80,.06)}
.meta-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px;color:#5a554e;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
.cat{color:#a85400}
.divider{width:1px;height:12px;background:#e2ddd6}
.article h1{margin:0 0 12px;font:800 clamp(36px,5vw,62px)/.98 Barlow,sans-serif;letter-spacing:-1.6px}
.article h2.section-title{margin:30px 0 12px;font:800 30px/1.05 Barlow,sans-serif;letter-spacing:-.6px}
.article h3{margin:18px 0 8px;font:800 22px/1.2 Barlow,sans-serif}
.article p{margin:0 0 22px;font-size:17px;line-height:1.8}
.article ul,.article ol{margin:0 0 22px;padding-left:22px;font-size:17px;line-height:1.75}
.article li{margin:0 0 8px}
.article .byline{display:flex;align-items:center;gap:10px;margin:0;font:600 15px/1.3 Inter,system-ui,sans-serif;text-decoration:none}
.article .byline img{width:40px;height:40px;max-width:40px;border-radius:50%;object-fit:cover}
.article .byline-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:0 0 10px}
.article .article-date{font:600 13px/1.3 Inter,system-ui,sans-serif}
.photo-credit{margin-top:4px;font-size:12px;line-height:1.35}
.button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 14px;border-radius:3px;font:700 15px/1 Inter,system-ui,sans-serif;cursor:pointer;background:#fff}
.button.primary{background:#5b22c9;border:1px solid #5b22c9;color:#fff}
.lot-actions{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px}
.lot-actions button:disabled{opacity:.45;cursor:default}
.pick-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #e6e1d8}
.pick-no{width:1.4em;font:800 18px/1 Barlow,sans-serif}
.face{width:72px;height:72px;max-width:72px;border-radius:50%;object-fit:cover;object-position:center 20%;flex:none}
.lot-odds-cards{display:none}
.lot-card{display:flex;flex-direction:column;gap:7px;padding:12px 10px;border:1px solid #e6e1d8;border-radius:8px;background:#fff}
.lot-id{display:flex;align-items:center;gap:8px;min-width:0;min-height:28px}
.lot-avatar{width:28px;height:28px;border-radius:50%;object-fit:cover;object-position:center 18%;flex:none}
.lot-initials{display:inline-flex;align-items:center;justify-content:center;background:#efe6ff;color:#2a1458;font:800 9px/1 Barlow,sans-serif}
.lot-id a{min-height:0;font:800 14px/1.15 Barlow,sans-serif;color:#2a1458;text-decoration:none}
.lot-rec{margin-left:auto;flex:none;font:600 12px/1 Inter,system-ui,sans-serif;color:#6b665e}
.article .lot-card p{margin:0}
.article .lot-stats{display:flex;gap:16px;font:800 20px/1.1 Barlow,sans-serif;color:#2a1458}
.lot-bar{display:flex;height:14px;border-radius:99px;overflow:hidden;background:#f6f1ff}
.lot-bar span{display:block;height:100%;min-width:0}
.lot-p1{background:#4c1d95}.lot-p2{background:#5b22c9}.lot-p3{background:#7c4fe0}.lot-p4{background:#9a78ea}.lot-p5{background:#b59cf2}.lot-p6{background:#d0c0f7}.lot-p7{background:#e6dcfb}
.article .lot-legend{display:flex;flex-wrap:wrap;gap:2px 10px;font:600 12px/1.25 Inter,system-ui,sans-serif;color:#3d3832}
.av{width:72px;height:72px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:#efe6ff;color:#2a1458;font:800 13px/1 Barlow,sans-serif;flex:none}
.need-grid,.prospect-list{display:grid;gap:16px}
.prospect{display:flex;gap:12px;align-items:flex-start}
.need-card{border:1px solid #e6e1d8;border-radius:8px;overflow:hidden;background:#fff}
.need-card figure.lead-photo{margin:0}
.need-card figure.lead-photo figcaption{padding:4px 12px 0}
.need-body{padding:10px 12px 12px}
.need-head{display:flex;align-items:center;gap:8px;margin:0 0 8px}
.need-head .lot-avatar{width:32px;height:32px}
.need-head h3{margin:0;font:800 20px/1.15 Barlow,sans-serif}
.need-head a{color:#2a1458;text-decoration:none}
.need-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:0 0 8px}
.need-tile{display:flex;flex-direction:column;justify-content:center;align-items:center;gap:3px;min-height:52px;padding:6px 4px;border-radius:6px;background:#f6f1ff;text-align:center}
.need-tile b{font:800 16px/1.1 Barlow,sans-serif;color:#2a1458}
.need-tile span{font:600 11px/1.25 Inter,system-ui,sans-serif;color:#5a554e}
.pos-bar{display:flex;width:100%;height:8px;border-radius:99px;overflow:hidden;background:#efe8ff}
.pos-bar span{display:block;height:100%;min-width:0}
.pos-G{background:#4c1d95}.pos-F{background:#7c4fe0}.pos-C{background:#d0c0f7}.pos-Other{background:#9a78ea}
.article .need-card p{margin:0 0 8px;font-size:15px;line-height:1.45}
.article .need-players{list-style:none;margin:0;padding:0}
.article .need-players li{display:flex;align-items:center;gap:8px;margin:0;padding:6px 0;border-top:1px solid #f3efe8;font-size:14px;line-height:1.3}
.need-players .face,.need-players .av{width:36px;height:36px;max-width:36px;font-size:11px}
.need-who{min-width:0}
.need-who a{font-weight:700;color:#2a1458;text-decoration:none}
.need-meta{display:block;color:#5a554e;font-size:12px;line-height:1.3}
.article .how-made{margin:22px 0 0;font-size:13px;line-height:1.55}
@media(max-width:900px){
.article-wrap{padding-top:8px}
.article{padding:22px 18px 28px;padding-top:12px}
.article h1{font-size:26px;line-height:1.05;letter-spacing:-.4px;margin-bottom:6px}
.meta-row{margin-bottom:6px}
.article .byline{font-size:14px}
}
@media(max-width:640px){
html body .lot-odds .table-wrap{display:none!important}
html body .lot-odds .lot-odds-cards{display:grid;gap:8px}
}
''' + internal_links.LEAD_CSS + '</style>'
    author = {
        '@context': 'https://schema.org', '@type': 'Article',
        'headline': TITLE, 'description': DESCRIPTION,
        'url': BASE + ROUTE, 'mainEntityOfPage': BASE + ROUTE,
        'datePublished': PUBLISHED, 'dateModified': PUBLISHED,
        'author': {
            '@type': 'Person', 'name': 'Ryan Moalemi',
            'url': BASE + '/authors/ryan-moalemi/',
        },
        'publisher': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': BASE + '/'},
    }
    doc = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        + social
        + f'<title>{e(TITLE)}</title>'
        f'<meta name="description" content="{e(DESCRIPTION)}">'
        '<meta name="author" content="Ryan Moalemi">'
        '<meta name="robots" content="index, follow">'
        f'<link rel="canonical" href="{BASE}{ROUTE}">'
        '<meta name="theme-color" content="#ffffff">'
        '<link rel="icon" href="/favicon.svg">'
        + style
        + faq_jsonld(pairs) + dataset_jsonld() + breadcrumb_jsonld()
        + '<script type="application/ld+json">' + json.dumps(author) + '</script>'
        + analytics.GA4_TAG
        + '</head><body>'
        + site_nav.render_header(site_nav.build_menu(ROOT), ROUTE)
        + body
        + '</body></html>'
    )
    doc = site_nav.ensure_assets(doc)
    doc = site_nav.install_footer(doc)
    doc = site_nav.strip_chrome_new_tabs(doc)
    if '\u2014' in doc:
        raise SystemExit('em dash in the lottery page')
    return doc


def main() -> None:
    if sum(CHANCES.values()) != TOTAL:
        raise SystemExit('chances must sum to 1,000')
    table = pick_probabilities()
    rows = matrix_rows(table)
    write_csv(rows)
    write_results()
    cards = team_needs()
    html_out = page(rows, cards)
    PAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PAGE_PATH.write_text(html_out, encoding='utf-8')
    print(f'Wrote {PAGE_PATH}')
    for row in rows:
        slot = row['slot']['id']
        print(slot, 'P1', pct(row['probs'][0], 4), 'top2', pct(row['top2'], 4))
    print('LA top2', pct(team_top_two(), 4))


if __name__ == '__main__':
    main()

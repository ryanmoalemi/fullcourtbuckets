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
TITLE = '2027 WNBA Draft Lottery Odds and Simulator (Drawing Nov 15)'
DESCRIPTION = (
    'Official 2027 WNBA Draft Lottery odds, full pick probabilities for picks 1-7, '
    'team needs, live results, and a free CSV. Drawing: Nov. 15, 2026.'
)
PUBLISHED = '2026-11-09'
MODIFIED = '2026-11-12'
CSV_PATH = ROOT / 'data' / 'wnba-draft-lottery-2027-odds.csv'
OUTCOMES_PATH = ROOT / 'data' / 'wnba-draft-lottery-2027-outcomes.csv'
RESULTS_PATH = ROOT / 'data' / 'wnba-draft-lottery-2027-results.json'
OFFICIAL_RELEASE = 'https://www.wnba.com/news/wnba-draft-lottery-2027-sunday-november-15'
PAGE_PATH = ROOT / 'wnba' / 'draft-lottery-2027' / 'index.html'
SEED = 20261115
TOTAL = 1000

# Pre-lottery order is worst record first. Houston won the head-to-head tiebreak
# over Toronto, so Houston is first and cannot land past pick 3.
SLOTS = [
    {
        'id': 'HOU', 'circle': 'HOU', 'team': 'Houston Comets (formerly Connecticut Sun)', 'short': 'Houston',
        'label': 'Houston (formerly Connecticut Sun)', 'href': '/wnba/teams/connecticut-sun/',
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
# Lottery card photos for teams whose hub image is a former player, a
# different city, or a venue. These stay on this page if the hub photos change.
TEAM_CARD_VISUALS = {
    'HOU': {
        'src': '/images/articles/wnba-draft-lottery-2027/brittney-griner-1200.webp',
        'alt': 'Brittney Griner clapping in a Connecticut Sun jersey during a July 2026 game',
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:260706_Lynx_Sun_JohnMc164.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0',
        'focal': 'center 20%',
    },
    'TOR': {
        'src': '/images/articles/wnba-draft-lottery-2027/marina-mabrey-1200.webp',
        'alt': 'Marina Mabrey in a Toronto Tempo jersey during a July 2026 game',
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:Marina_Mabrey_Tempo.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0',
        'focal': 'center 20%',
    },
    'POR': {
        'src': '/images/articles/wnba-draft-lottery-2027/emily-engstler-1200.webp',
        'alt': 'Emily Engstler of the Portland Fire dribbling during a July 2026 game',
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:Emily_Engstler_Fire.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0',
        'focal': 'center 20%',
    },
}


def e(value) -> str:
    return html.escape(str(value), quote=True)


def pct(fr: Fraction, places: int) -> str:
    quant = Decimal('1').scaleb(-places)
    val = (Decimal(fr.numerator) / Decimal(fr.denominator)) * 100
    return format(val.quantize(quant, rounding=ROUND_HALF_UP), f'.{places}f')


def dec(fr: Fraction, places: int) -> str:
    """Format a fraction as a decimal, rounding only at the end. Not a percentage."""
    quant = Decimal('1').scaleb(-places)
    val = Decimal(fr.numerator) / Decimal(fr.denominator)
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
            cells += [dec(row['expected'], 4), 'exact enumeration of 42 ordered pairs']
            writer.writerow(cells)


def write_outcomes_csv() -> None:
    """One row for each of the 42 first-and-second pick orders, with exact weights."""
    header = [
        'first', 'second', 'probability_fraction', 'probability_pct',
        'pick_1', 'pick_2', 'pick_3', 'pick_4', 'pick_5', 'pick_6', 'pick_7',
    ]
    rows = []
    total = Fraction(0)
    for first in ORDER:
        for second in ORDER:
            if first == second:
                continue
            weight = pair_probability(first, second)
            total += weight
            assigned = assignment(first, second)
            rows.append([
                first, second,
                f'{weight.numerator}/{weight.denominator}',
                pct(weight, 6),
                *[assigned[k] for k in range(1, 8)],
            ])
    if len(rows) != 42 or total != 1:
        raise SystemExit('outcomes CSV must enumerate 42 orders that sum to 1')
    OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTCOMES_PATH.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def top_n(probs: list[Fraction], n: int) -> Fraction:
    return sum(probs[:n], Fraction(0))


def exact_second_or_third(probs: list[Fraction]) -> Fraction:
    return probs[1] + probs[2]


def worst_pick(probs: list[Fraction]) -> int:
    return max(index + 1 for index, prob in enumerate(probs) if prob > 0)


def hou_then_tor() -> Fraction:
    return Fraction(CHANCES['HOU'], TOTAL) * Fraction(CHANCES['TOR'], TOTAL - CHANCES['HOU'])


def summary_table(rows: list[dict]) -> str:
    body = []
    for row in rows:
        slot = row['slot']
        probs = row['probs']
        body.append(
            '<tr>'
            f'<th scope="row"><a href="{e(slot["href"])}">{e(slot["label"])}</a></th>'
            f'<td data-label="Top two">{pct(top_n(probs, 2), 1)}%</td>'
            f'<td data-label="Top three">{pct(top_n(probs, 3), 1)}%</td>'
            f'<td data-label="Exactly No. 2 or No. 3">{pct(exact_second_or_third(probs), 1)}%</td>'
            f'<td data-label="Worst pick">No. {worst_pick(probs)}</td>'
            '</tr>'
        )
    return (
        '<div class="table-wrap summary-wrap" data-fcb-data-table>'
        '<table class="fcb-cards fcb-data-table" id="lottery-summary">'
        '<thead><tr><th scope="col">Slot</th><th scope="col">Top two</th>'
        '<th scope="col">Top three</th><th scope="col">Exactly No. 2 or No. 3</th>'
        '<th scope="col">Worst pick</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


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
            'A final file locks the simulator to this order. To update the page title after the '
            'drawing, set title to the post-drawing headline. When status is final, the page '
            'reads that title and updates the h1, document title, og:title, and twitter:title '
            'without a rebuild.'
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
    """2026 regular-season minutes from the player file, ages from the roster snapshot."""
    facts = json.loads((ROOT / 'data' / 'wnba' / 'team-facts.json').read_text(encoding='utf-8'))
    ages = {}
    for slot in SLOTS:
        block = facts['teams'].get(slot['facts']) or {}
        for person, info in (block.get('roster') or {}).items():
            ages[(slot['facts'], _norm(person))] = info.get('age')
    buckets: dict[str, dict] = {}
    for slot in SLOTS:
        buckets[slot['id']] = {
            'slot': slot, 'positions': {}, 'players': [], 'minutes': 0.0, 'age_minutes': 0.0, 'age_sum': 0.0,
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
            slot_id = by_facts.get(team.get('full_name') or '')
            if slot_id == 'LAL-PHX':
                slot_id = 'LAL'
            if not slot_id:
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
            bucket['players'].append({
                'name': name, 'slug': slug, 'position': position, 'minutes': minutes,
                'points': points, 'age': age if isinstance(age, (int, float)) else None,
            })
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
        cards.append({
            'slot': slot,
            'minutes': int(round(bucket['minutes'])),
            'players': len(bucket['players']),
            'positions': positions,
            'age': None if age is None else f'{age:.1f}',
            'age_coverage': f'{coverage:.0f}',
            'leaders': leaders,
        })
    return cards


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
    bits.append(f"{int(round(player['minutes'])):,} minutes")
    bits.append(f"{int(round(player['points'])):,} points")
    return (
        f'<li>{_player_face(player)}<div class="need-who">{name}'
        f'<span class="need-meta">{e(" · ".join(bits))}</span></div></li>'
    )


def _position_bar(positions: list[dict]) -> str:
    if not positions:
        return '<div class="stat-tile need-tile"><b>n/a</b><span>Minutes</span></div>'
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
        '<div class="stat-tile need-tile need-tile-bar">'
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
    return first + extra


def needs_html(cards: list[dict], rows: list[dict]) -> str:
    by_id = {row['slot']['id']: row for row in rows}
    phoenix_top2 = pct(by_id['LAL-PHX']['top2'], 1)
    blocks = []
    for card in cards:
        slot = card['slot']
        mark = _slot_mark(slot)
        if mark:
            focal = mark.get('focal') or {'TOR': 'center 75%', 'POR': 'center 40%'}.get(slot['id'], 'center 20%')
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
        age = card['age'] or 'n/a'
        players = ''.join(_player_row(player) for player in card['leaders'])
        blocks.append(
            '<article class="fcb-card need-card">'
            f'{photo}<div class="need-body">'
            f'<div class="need-head">{avatar}<h3><a href="{e(slot["href"])}">{e(slot["team"])}</a></h3></div>'
            '<div class="stat-tiles need-tiles">'
            f'<div class="stat-tile need-tile"><b>{e(age)}</b><span>Weighted age</span></div>'
            f'{_position_bar(card["positions"])}'
            '</div>'
            f'<p class="need-take">{e(_takeaway(card, phoenix_top2))}</p>'
            f'<ul class="need-players">{players}</ul>'
            '</div></article>'
        )
    return '<div class="need-grid">' + ''.join(blocks) + '</div>'


def _mocks_short(mocks: str) -> str:
    left, _, right = mocks.partition(' of ')
    if left.isdigit() and right.isdigit():
        return f'{left}/{right}'
    return mocks


def prospect_section_note() -> str:
    notes = [f'{item["name"]}: {item["note"]}' for item in PROSPECTS if item['note']]
    return (
        'Every counting line is from the linked Sports-Reference page, read Nov. 9, 2026. '
        'The 2026-27 lines are one or two games. Headshots are Wikimedia Commons photos credited on each card. '
        "S'Mya Nichols has no freely licensed photo, so her card uses initials. "
        + ' '.join(notes)
    )


def prospects_html() -> str:
    cards = []
    for prospect in PROSPECTS:
        full = prospect['full']
        early = prospect['early']
        photo = PROSPECT_PHOTOS.get(prospect['name'])
        if photo:
            face = (
                f'<img class="face" src="{e(photo["src"])}" alt="" '
                f'width="80" height="80" loading="lazy" decoding="async">'
            )
            credit = f'<p class="card-credit">{photo_credit(photo)}</p>'
        else:
            face = f'<span class="av" aria-hidden="true">{e(prospect["initials"])}</span>'
            credit = ''
        games = '1 game' if early['g'] == 1 else f"{early['g']} games"
        season_line = (
            f"{full['season']} at {full['school']}, {full['g']} games: "
            f"{full['stl']} steals, {full['blk']} blocks."
        )
        early_line = (
            f"2026-27 at {early['school']}, {games} posted by Nov. 9, 2026: "
            f"{early['pts']} points, {early['reb']} rebounds, {early['ast']} assists."
        )
        cards.append(
            '<article class="fcb-card need-card prospect">'
            '<div class="need-body">'
            '<div class="need-head">'
            f'{face}'
            '<div class="need-title">'
            f'<h3>{prospect["board"]}. {e(prospect["name"])}</h3>'
            f'<span class="need-id">{e(prospect["pos"])}, {e(prospect["height"])}, {e(prospect["school"])}</span>'
            '</div></div>'
            f'{credit}'
            '<div class="stat-tiles need-tiles">'
            f'<div class="stat-tile need-tile"><b>{prospect["board"]}</b><span>Big Board</span></div>'
            f'<div class="stat-tile need-tile"><b>{e(_mocks_short(prospect["mocks"]))}</b><span>Mocks</span></div>'
            '<div class="stat-tile need-tile line-tile">'
            f'<b>{e(full["pts"])} · {e(full["reb"])} · {e(full["ast"])}</b>'
            '<span>PTS · REB · AST</span>'
            '</div>'
            f'<div class="stat-tile need-tile"><b>{e(full["fg"])}</b><span>FG%</span></div>'
            '</div>'
            f'<p class="early-line">{e(season_line)}</p>'
            f'<p class="early-line">{e(early_line)}</p>'
            f'<p class="sr-link"><a href="{e(prospect["sr"])}" target="_blank" rel="noopener">Sports-Reference</a></p>'
            '</div></article>'
        )
    return '<div class="prospect-list">' + ''.join(cards) + '</div>'


def _slot_mark(slot: dict) -> dict | None:
    if slot['id'] in TEAM_CARD_VISUALS:
        return TEAM_CARD_VISUALS[slot['id']]
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
        '<div class="table-wrap"><table class="fcb-cards fcb-data-table" id="prelottery-odds">'
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
        'dateModified': MODIFIED,
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
  function esc(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function avatar(slot) {
    if (slot.photo && slot.photo.src) {
      var style = slot.photo.focal ? ' style="object-position:' + esc(slot.photo.focal) + '"' : '';
      return '<img class="av" src="' + esc(slot.photo.src) + '" alt="" width="72" height="72" loading="lazy" decoding="async"' + style + '>';
    }
    return '<span class="av" aria-hidden="true">' + esc(slot.circle) + '</span>';
  }
  function row(pickNo, slot) {
    return '<div class="pick-row"><span class="pick-no">' + pickNo + '</span>' +
      avatar(slot) +
      '<span class="pick-name">' + esc(slot.label) + '</span></div>';
  }
  function show(order, text) {
    summary.textContent = text;
    board.innerHTML = order.map(function (slot, index) { return row(index + 1, slot); }).join('');
  }
  function randomDraw() {
    var next = lcg((Math.floor(Math.random() * 0x7fffffff) ^ Date.now()) >>> 0);
    show(draw(next), 'One draw.');
  }
  function fmtCount(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  function pct1(n) {
    return (Math.round((n / 10000) * 1000) / 10).toFixed(1);
  }
  function manyDraw() {
    var next = lcg(SEED);
    var pick1 = {};
    SLOTS.forEach(function (slot) { pick1[slot.id] = 0; });
    var counts = {}, bestN = 0, best = null;
    for (var n = 0; n < 10000; n++) {
      var order = draw(next);
      pick1[order[0].id]++;
      var key = order.map(function (slot) { return slot.id; }).join(',');
      counts[key] = (counts[key] || 0) + 1;
      if (counts[key] > bestN) { bestN = counts[key]; best = order; }
    }
    var hou = SLOTS.filter(function (slot) { return slot.id === 'HOU'; })[0];
    var houN = pick1.HOU;
    var torN = pick1.TOR;
    show(best,
      'In these 10,000 draws, Houston was first ' + fmtCount(houN) + ' times (' + pct1(houN) +
      '%) and Toronto ' + fmtCount(torN) + ' times (' + pct1(torN) +
      '%), in line with the ' + hou.p1 + '% pick-1 odds in the table. The board below is the most common full order, which came up ' +
      fmtCount(bestN) + ' times.');
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
      liveStatus.textContent = 'The drawing has not taken place yet. Picks 8 through 15 stay to be confirmed.';
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
    if (data.title) {
      var heading = document.querySelector('.article h1') || document.querySelector('h1');
      if (heading) heading.textContent = data.title;
      document.title = data.title;
      var tags = document.querySelectorAll('meta[property="og:title"], meta[name="twitter:title"]');
      for (var i = 0; i < tags.length; i++) tags[i].setAttribute('content', data.title);
    }
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
    table = pick_probabilities()
    payload = []
    for slot in SLOTS:
        item = {
            'id': slot['id'],
            'label': slot['label'],
            'circle': slot['circle'],
            'chances': slot['chances'],
            'p1': pct(table[slot['id']][0], 1),
        }
        mark = _slot_mark(slot)
        if mark and mark.get('src'):
            item['photo'] = {
                'src': mark['src'],
                'focal': mark.get('focal') or '',
            }
        payload.append(item)
    return SIM_JS.replace('__SLOTS__', json.dumps(payload)).replace('__SEED__', str(SEED))


def live_html() -> str:
    items = []
    for number in range(1, 16):
        label = 'Not drawn yet' if number <= 7 else 'to be confirmed'
        items.append(f'<li>Pick {number}: {label}</li>')
    return (
        '<section id="live-results"><h2 class="section-title">Lottery results</h2>'
        '<p id="live-status">Results will appear here after the Nov. 15, 2026 drawing. Picks 8 through 15 stay to be confirmed.</p>'
        f'<ol id="live-order">{"".join(items)}</ol>'
        '<p class="table-note">The lottery is drawn Nov. 15, 2026. Picks 1 through 7 appear here once the league announces the order, '
        'and the simulator then locks to that order. '
        'Picks 8 through 15 are to be confirmed: the Oct. 28 release does not publish them, Indiana and Washington both finished 28-16, '
        'and the 2025 Atkins deal was announced as swap rights rather than a finished draft order.</p></section>'
    )


def page(rows: list[dict], cards: list[dict]) -> str:
    pairs = faq_pairs(rows)
    la_top = team_top_two()
    hou = next(row for row in rows if row['slot']['id'] == 'HOU')
    tor = next(row for row in rows if row['slot']['id'] == 'TOR')
    was = next(row for row in rows if row['slot']['id'] == 'WAS')
    first_then_second = hou_then_tor()
    both_orders = first_then_second * 2
    hero_figure = (
        '<figure class="lead-photo"><picture>'
        f'<source srcset="{e(HERO["src"])} 1200w" type="image/webp" sizes="(max-width: 900px) calc(94vw - 40px), 842px">'
        f'<img src="{e(HERO["src"])}" alt="{e(HERO["alt"])}" style="object-position:center 30%" '
        f'width="{HERO["width"]}" height="{HERO["height"]}" decoding="async" fetchpriority="high">'
        f'</picture><figcaption>{photo_credit(HERO)}</figcaption></figure>'
    )
    stakes = (
        '<p class="lead">The 2027 WNBA Draft Lottery is Sunday, Nov. 15, 2026, from 4:30 to 5:00 p.m. PT '
        '(7:30 to 8:00 p.m. ET) on ESPN, after UConn vs. Louisville, and on TSN in Canada. '
        'The draft itself is Monday, April 12, 2027.</p>'
        '<p>The Connecticut Sun played their last season in Connecticut in 2026 '
        'and will enter 2027 as the Houston Comets, after the WNBA and NBA approved the sale '
        'and relocation on May 13, 2026. Toronto just finished an 11-33 expansion debut. '
        'The top of this draft is expected to turn on JuJu Watkins, the USC guard who is '
        'eligible for the 2027 WNBA Draft because she turns 22 in the 2027 calendar year, '
        'and who is the No. 1 name on the consensus board this page uses.</p>'
    )
    findings = (
        f'<p>Houston and Toronto each have a {pct(hou["top2"], 1)}% top-two chance. '
        f"Houston can't fall below No. 3, while Toronto drops to No. 4 {pct(tor['probs'][3], 1)}% of the time. "
        f'Washington (from Chicago) has a {pct(was["top2"], 1)}% top-two chance and a {pct(top_n(was["probs"], 3), 1)}% top-three chance.</p>'
    )
    credit = (
        '<p class="table-note" id="calculations">'
        "Calculations: Full Court Buckets, using the WNBA's published lottery allocations and drawing rules. "
        f'Source: <a href="{OFFICIAL_RELEASE}" target="_blank" rel="noopener">WNBA release, Oct. 28, 2026</a>. '
        "FCB's calculated odds dataset is available under CC0. Free to use and republish (CC0). "
        '<a href="/data/wnba-draft-lottery-2027-odds.csv">Download CSV (CC0)</a>. '
        '<a href="/data/wnba-draft-lottery-2027-outcomes.csv">42 weighted outcomes (CSV, CC0)</a>. '
        'Data questions or corrections: <a href="mailto:ryan@fullcourtbuckets.com">ryan@fullcourtbuckets.com</a>.</p>'
    )
    difference = (
        f'<p>Houston and Toronto each hold {CHANCES["HOU"]} of {TOTAL} combinations, so they have the same chance at picks 1 and 2. '
        f'The difference is the floor. Houston cannot fall below No. 3. Toronto can fall to No. 4, and does so {pct(tor["probs"][3], 1)}% of the time.</p>'
    )
    slots_note = (
        "<p>The seven lottery slots are held by six teams. Los Angeles holds its own slot and Phoenix's.</p>"
    )
    methods = (
        '<p class="table-note" id="methods">Data through Oct. 28, 2026. Methods: exact enumeration of the 42 orders for picks 1 and 2. '
        f"P(second | first) = remaining chances / (1,000 minus the winner's chances). "
        f'Los Angeles, counting both picks, has an {pct(la_top, 1)}% chance that at least one of them is in the top two. '
        "Corrected the CSV's expected-pick column on Nov. 12, 2026; pick probabilities unchanged. "
        'This is the lottery, not the April 12, 2027 draft, and not the April 3, 2026 expansion draft.</p>'
        f'<p class="table-note" id="methods-footnote">Worked example: Houston first then Toronto second = {CHANCES["HOU"]}/{TOTAL} x {CHANCES["TOR"]}/{TOTAL - CHANCES["HOU"]} = {pct(first_then_second, 4)}%, '
        f'and the two orders together = {pct(both_orders, 1)}%.</p>'
    )
    simulator = (
        '<section id="simulator"><h2 class="section-title">Lottery simulator</h2>'
        '<p>This simulator lets you see how a lottery drawing can come out, including cases where Houston or Toronto miss the top two. '
        'One draw is random; the 10,000-draw button always starts from the same seed, 20261115, so everyone sees the same totals, which you can compare with the exact odds in the table above.</p>'
        '<div class="lot-actions">'
        '<button type="button" class="button primary" id="draw-one">One draw</button>'
        '<button type="button" class="button" id="draw-many">10,000 draws</button>'
        '<button type="button" class="button" id="draw-reset">Reset</button>'
        '</div><p id="draw-summary">No draw yet.</p><div id="draw-board"></div></section>'
    )
    body = f'''<main id="content" class="shell article-wrap">
<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a><span aria-hidden="true">/</span><a href="/wnba/">WNBA</a><span aria-hidden="true">/</span><span>2027 Draft Lottery</span></nav>
<article class="article"><div class="meta-row"><span class="cat">WNBA</span><span class="divider"></span><span>Full Court Buckets</span></div>
<h1>{e(TITLE)}</h1>
<div class="byline-row"><a class="byline" href="/authors/ryan-moalemi/"><picture><source srcset="/images/authors/ryan-moalemi-photo-byline.webp" type="image/webp"><img src="/images/authors/ryan-moalemi-photo-byline.jpg?v=d51e90ea6c01" alt="Ryan Moalemi" width="80" height="80" decoding="async" loading="lazy"></picture><span>By Ryan Moalemi</span></a><time class="article-date" datetime="{PUBLISHED}">November 9, 2026</time></div>
{hero_figure}
{stakes}
{findings}
<h2 class="section-title" id="probabilities">Chance of every pick</h2>
{summary_table(rows)}
{odds_table(rows)}
{credit}
{difference}
{slots_note}
{methods}
<section id="how"><h2 class="section-title">How the drawing works</h2>
<p>The league puts 14 balls, numbered 1 through 14, in the machine and draws four. That is 1,001 combinations. One combination is left unassigned, so 1,000 are in play. The slot that owns the combination gets pick 1. The four balls go back in, and the same draw sets pick 2. If the machine hits the unassigned combination, or a combination owned by the slot that already won, it draws again.</p>
<p>Picks 3 through 7 are not drawn. They follow the pre-lottery order among the five slots still waiting. That order, worst record first, is Houston, Toronto, Washington (Chicago's pick), Seattle, Portland, Los Angeles (own pick), Los Angeles (Phoenix's pick).</p>
<p>Five of the records are two seasons added together, 2025 and 2026: Chicago 26-62, Houston 22-66, Los Angeles 37-51, Phoenix 43-45, and Seattle 31-57. Portland and Toronto were expansion teams in 2026, so their odds use 2026 only: Portland 17-27 and Toronto 11-33. Houston and Toronto both land at .250, so each receives 329 combinations.</p>
<h3>The tie</h3>
<p>The <a href="https://www.wnba.com/news/wnba-draft-lottery-2027-sunday-november-15" target="_blank" rel="noopener">Oct. 28, 2026 league release</a> uses the 2026 head-to-head as the first tiebreaker. Houston, then the Connecticut Sun, went 1-2 against Toronto. The three games are in the site schedule file, which was taken from the WNBA schedule: Toronto 106, Connecticut 102 on June 10; Toronto 101, Connecticut 97 on June 19; Connecticut 95, Toronto 81 on Sept. 24. Houston therefore sits ahead of Toronto. Houston's latest possible pick is No. 3. Toronto's latest possible pick is No. 4. Those floors also follow the drawing rules in that release: Houston cannot land past No. 3, and Toronto cannot land past No. 4.</p>
<h3>The traded picks</h3>
<p>Washington holds Chicago's pick. The Oct. 28 footnote says Chicago traded its own 2027 first-round pick to Washington for Ariel Atkins on Feb. 23, 2025. The team releases that day describe the first-round piece as the right to swap Washington's own 2027 first with Chicago's own 2027 first, plus Chicago's 2027 second-round pick. Those are the <a href="https://mystics.wnba.com/news/washington-mystics-acquire-third-overall-picki-in-the-wnba-draft" target="_blank" rel="noopener">Mystics release</a> and the <a href="https://www.wnba.com/news/chicago-sky-acquire-ariel-atkins" target="_blank" rel="noopener">league release on the Sky deal</a>. This page follows the Oct. 28 lottery assignment for the combinations. It does not assign Washington's own first-rounder.</p>
<p>Los Angeles holds Phoenix's pick. The <a href="https://www.wnba.com/news/rapid-reactions-trade-deadline-2026" target="_blank" rel="noopener">league's trade-deadline note</a> says Los Angeles sent Kelsey Plum to Phoenix for Monique Akoa Makani, a 2027 first-round pick, and a 2028 second-round pick. The lottery footnote dates that deal Aug. 2, 2026.</p>
<p>Houston is the relocated Connecticut Sun. The <a href="https://www.wnba.com/news/wnba-nba-approve-connecticut-sun-sale" target="_blank" rel="noopener">May 13, 2026 sale release</a> says the club stays in Connecticut for 2026 and moves to Houston for 2027, under Tilman J. Fertitta. The team URL on this site is still <a href="/wnba/teams/connecticut-sun/">/wnba/teams/connecticut-sun/</a>.</p>
<p>Bethany Donaphin, head of league operations, reveals the result on ESPN. Ernst &amp; Young oversees the drawing. The presentation name on the release is State Street Investment Management SPY. ESPN is airing the lottery for the 15th year in a row.</p>
</section>
{simulator}
<section id="prospects"><h2 class="section-title">Early prospect board</h2>
<p>Order is the <a href="https://ultimatebigboard.com/wnba/2027/big-board/" target="_blank" rel="noopener">Ultimate Big Board</a> snapshot calculated Oct. 29, 2026. It is a consensus of mocks, not a draft.</p>
{prospects_html()}
<p class="section-note table-note">{e(prospect_section_note())}</p>
</section>
{live_html()}
<section id="playoff-records"><h2 class="section-title">2026 records behind picks 8 through 15</h2>
<p>The eight clubs in the top eight of the <a href="/standings/">2026 standings</a> finished the regular season, in the WNBA schedule file, at Minnesota 33-11, Golden State 32-12, Las Vegas 31-13, Atlanta 30-14, Washington 28-16, Indiana 28-16, Dallas 27-17, and New York 26-18. Those are records, not pick numbers. Washington and Indiana are tied, and the lottery release does not publish the rest of round 1.</p>
</section>
<section id="needs"><h2 class="section-title">What the 2026 rosters look like</h2>
<p>Each card is the 2026 roster tied to that lottery pick.</p>
{needs_html(cards, rows)}
<p class="section-note table-note">Minutes are 2026 regular-season per-game averages times games played, from the player file checked Nov. 8, 2026. Weighted age is the Oct. 28, 2026 WNBA.com roster snapshot in that file, weighted by those minutes. The bar splits the same minutes by position. The four names on each card are the highest minute totals. Headshots are approved player photographs already on this site. A name with initials has no approved photograph.</p>
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
<li><a href="/data/wnba-draft-lottery-2027-outcomes.csv">42 weighted lottery outcomes (CSV, CC0)</a></li>
<li><a href="https://www.wnba.com/news/wnba-nba-approve-connecticut-sun-sale" target="_blank" rel="noopener">WNBA and NBA approve the Sun sale, May 13, 2026</a></li>
<li><a href="https://mystics.wnba.com/news/washington-mystics-acquire-third-overall-picki-in-the-wnba-draft" target="_blank" rel="noopener">Mystics on the Ariel Atkins trade, Feb. 23, 2025</a></li>
<li><a href="https://www.wnba.com/news/chicago-sky-acquire-ariel-atkins" target="_blank" rel="noopener">League release on the Sky and Ariel Atkins, Feb. 23, 2025</a></li>
<li><a href="https://www.wnba.com/news/rapid-reactions-trade-deadline-2026" target="_blank" rel="noopener">League trade-deadline note on Kelsey Plum, 2026</a></li>
<li>The 2026 WNBA schedule file on this site, taken from the league schedule, for the three Sun-Tempo games and the 2026 records</li>
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
.article .lead{font-size:18px}
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
.lot-id a{min-height:0;flex:1 1 auto;min-width:0;font:800 14px/1.15 Barlow,sans-serif;color:#2a1458;text-decoration:none}
.lot-rec{margin-left:auto;flex:none;font:600 12px/1 Inter,system-ui,sans-serif;color:#6b665e}
.article .lot-card p{margin:0}
.article .lot-stats{display:flex;gap:16px;font:800 20px/1.1 Barlow,sans-serif;color:#2a1458}
.lot-bar{display:flex;height:14px;border-radius:99px;overflow:hidden;background:#f6f1ff}
.lot-bar span{display:block;height:100%;min-width:0}
.lot-p1{background:#4c1d95}.lot-p2{background:#5b22c9}.lot-p3{background:#7c4fe0}.lot-p4{background:#9a78ea}.lot-p5{background:#b59cf2}.lot-p6{background:#d0c0f7}.lot-p7{background:#e6dcfb}
.article .lot-legend{display:flex;flex-wrap:wrap;gap:2px 10px;font:600 12px/1.25 Inter,system-ui,sans-serif;color:#3d3832}
.av{width:72px;height:72px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:#efe6ff;color:#2a1458;font:800 13px/1 Barlow,sans-serif;flex:none}
.pick-row img.av{object-fit:cover;object-position:center 18%;background:none;display:block}
.need-grid,.prospect-list{display:grid;gap:16px}
.prospect .need-head{margin-bottom:4px}
.prospect .face,.prospect .av{width:40px;height:40px;max-width:40px;font-size:12px}
.need-title{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px;min-width:0}
.prospect .need-head h3{font-size:18px}
.need-id{font:600 13px/1.2 Inter,system-ui,sans-serif;color:#5a554e}
.article .card-credit,.article .early-line,.article .sr-link{margin:0 0 8px;font-size:12px;line-height:1.35;color:#5a554e}
.article .sr-link{margin-bottom:0}
.line-tile b{font-size:13px;letter-spacing:-.2px}
.need-card{border:1px solid #e6e1d8;border-radius:8px;overflow:hidden;background:#fff}
.need-card figure.lead-photo{margin:0}
.need-card figure.lead-photo figcaption{padding:4px 12px 0}
.need-body{padding:10px 12px 12px}
.need-head{display:flex;align-items:center;gap:8px;margin:0 0 8px}
.need-head .lot-avatar{width:32px;height:32px}
.need-head h3{margin:0;min-width:0;font:800 20px/1.15 Barlow,sans-serif}
.need-head a{color:#2a1458;text-decoration:none}
.need-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:0 0 8px}
.need-card:not(.prospect) .need-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
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
        'datePublished': PUBLISHED, 'dateModified': MODIFIED,
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
    write_outcomes_csv()
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

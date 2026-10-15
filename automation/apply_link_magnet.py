#!/usr/bin/env python3
"""Insert citation blocks into the five link-magnet pages. Safe to run again."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import citation

ROOT = Path(__file__).resolve().parents[1]


def once(html: str, old: str, new: str, label: str) -> str:
    count = html.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    return html.replace(old, new, 1)


def under_headline(html: str) -> str:
    """Quick-cite follows the lead photo. The byline stays under the H1."""
    import internal_links as links
    return links.place_quick_cite(html)


def ensure_assets(html: str) -> str:
    if '/assets/citation.css' not in html:
        html = html.replace(
            'href="/assets/site-nav.css"',
            'href="/assets/site-nav.css">\n<link rel="stylesheet" href="/assets/citation.css"',
            1,
        )
    if '/assets/citation.js' not in html:
        html = html.replace(
            'src="/assets/site-nav.js"',
            'src="/assets/citation.js" defer></script>\n<script src="/assets/site-nav.js"',
            1,
        )
    return html


def ensure_dataset(html: str, script: str) -> str:
    if '"@type": "Dataset"' in html or '"@type":"Dataset"' in html:
        return html
    return html.replace('</head>', script + '\n</head>', 1)


def load(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def save(relative: str, html: str) -> None:
    (ROOT / relative).write_text(html, encoding='utf-8')


def apply_viewership() -> None:
    relative = 'news/wnba-finals-2026-audience-growth-dream-valkyries/index.html'
    payload = json.loads((ROOT / 'data/viewership-attendance.json').read_text(encoding='utf-8'))
    headers, rows = citation.viewership_csv_rows(payload)
    citation.write_csv(ROOT / 'news/wnba-finals-2026-audience-growth-dream-valkyries/finals-audience.csv', headers, rows)
    html = ensure_assets(load(relative))
    html = ensure_dataset(html, citation.dataset_script(
        '2026 WNBA Finals audience and search demand',
        'Published Full Court Buckets figures for 2026 WNBA audience averages and October search estimates. Games 1-4 follow the WNBA release of Oct. 13, 2026. Games 5-7 are not listed in that release. The game-by-game sheet is the ratings tracker. Full Court Buckets gathers and verifies its own data.',
        citation.VIEWERSHIP_URL,
        citation.VIEWERSHIP_URL + 'finals-audience.csv',
    ))
    blocks = citation.viewership_blocks(payload)
    if 'fcb-quick-cite' not in html:
        html = once(
            html,
            'million different people.</p><p><a class="inline-link" href="/wnba/angel-reese/"',
            'million different people.</p>\n' + blocks['cite'] + '\n<p><a class="inline-link" href="/wnba/angel-reese/"',
            'viewership cite',
        )
    # The game-by-game table lives on the ratings tracker. Do not paste it back here.
    if citation.TRACKER_PATH not in html:
        html = once(
            html,
            '<h2 class="section-title" id="finals-tv-schedule">',
            citation.ratings_hub_crosslink() + '\n<h2 class="section-title" id="finals-tv-schedule">',
            'ratings hub link',
        )
    if 'id="verified-viewership-table"' not in html:
        html = once(
            html,
            '<div class="table-wrap"><table><thead><tr><th>Audience measure</th>',
            '<div class="table-wrap" id="verified-viewership-table"><table><thead><tr><th>Audience measure</th>',
            'viewership table id',
        )
    audience_embed = citation.embed_block(
        'verified-viewership-table',
        citation.embed_snippet(
            citation.VIEWERSHIP_URL,
            'verified-viewership-table',
            citation.BASE + '/images/articles/wnba-finals-2026-audience-growth-dream-valkyries/chart-audience-measures.png',
            'Chart: average WNBA viewers per game, 2026',
        ),
        'finals-audience.csv',
    )
    if 'embed-verified-viewership-table' not in html:
        html = once(
            html,
            '</table></div>\n<p class="table-source"',
            '</table></div>\n' + audience_embed + '\n<p class="table-source"',
            'audience embed',
        )
    search_embed = citation.embed_block(
        'search-demand-estimates',
        citation.embed_snippet(
            citation.VIEWERSHIP_URL,
            'search-demand-estimates',
            citation.BASE + '/images/articles/wnba-finals-2026-audience-growth-dream-valkyries/chart-search-interest.png',
            'Chart: estimated US monthly Google searches, October 2026',
        ),
        'finals-audience.csv',
    )
    if 'embed-search-demand-estimates' not in html:
        html = once(
            html,
            '</figure><h2 class="section-title">What audience should the Finals draw</h2>',
            '</figure>\n' + search_embed + '\n<h2 class="section-title">What audience should the Finals draw</h2>',
            'search embed',
        )
    # The visible schedule table is the Oct. 13 release, same rows as the ratings hub.
    # Do not offer a second embed of it. The citable sheet is the tracker.
    html = citation.add_heading_anchors(html, citation.VIEWERSHIP_FORCED)
    save(relative, under_headline(html))


def apply_cards() -> None:
    relative = 'news/top-10-womens-college-basketball-cards-to-collect-2026/index.html'
    citation.write_csv(
        ROOT / 'news/top-10-womens-college-basketball-cards-to-collect-2026/card-sales.csv',
        citation.CARD_HEADERS,
        citation.CARD_ROWS,
    )
    html = ensure_assets(load(relative))
    html = ensure_dataset(html, citation.dataset_script(
        'Women\'s college basketball card sales selected for this 2026 guide',
        'Ten card sales selected for the Full Court Buckets 2026 guide, with school, grade, platform, date, and price. Not a complete market history. Full Court Buckets gathers and verifies its own data.',
        citation.CARDS_URL,
        citation.CARDS_URL + 'card-sales.csv',
    ))
    if 'id="card-sales-comparison-table"' not in html:
        html = once(
            html,
            '<section id="juju-watkins">',
            citation.cards_blocks() + '\n<section id="juju-watkins">',
            'cards table',
        )
    html = citation.add_heading_anchors(html, {}, citation.CARD_PLAYERS)
    save(relative, under_headline(html))


def number_sources(html: str) -> str:
    if 'id="source-1"' in html:
        return html
    marker = '<ol class="sources">'
    start = html.find(marker)
    end = html.find('</ol>', start)
    if start < 0 or end < 0:
        raise SystemExit('expansion sources list missing')
    block = html[start:end]
    number = 0

    def repl(match: re.Match) -> str:
        nonlocal number
        number += 1
        return f'<li id="source-{number}">[ <a href="#source-{number}">{number}</a> ] {match.group(1)}</li>'

    block = re.sub(r'<li>(.*?)</li>', repl, block, flags=re.S)
    return html[:start] + block + html[end:]


def apply_expansion() -> None:
    relative = 'news/wnba-expansion-teams/index.html'
    headers = ['section', 'city_or_team', 'season', 'record_or_fee', 'notes']
    rows = [
        ['2026 season', 'Portland Fire', '2026', '17-27', '5th in the West. Point differential not on this page.'],
        ['2026 season', 'Toronto Tempo', '2026', '11-33', '6th in the East. Point differential not on this page.'],
        ['Year-1 comparison', 'Golden State Valkyries', '2025', '23-21', 'Won a playoff series? No. Lost in the first round.'],
        ['Future fee', 'Cleveland', '2028', '$250 million', 'NBA ownership group. League size 16.'],
        ['Future fee', 'Detroit', '2029', '$250 million', 'NBA ownership group. League size 17.'],
        ['Future fee', 'Philadelphia', '2030', '$250 million', 'NBA ownership group. League size 18.'],
    ]
    citation.write_csv(ROOT / 'news/wnba-expansion-teams/expansion.csv', headers, rows)
    html = ensure_assets(load(relative))
    if 'fcb-quick-cite' not in html:
        html = once(
            html,
            'neither team made the playoffs</a>.</p>\n\n<h2 class="section-title">Portland and Toronto at a glance</h2>',
            'neither team made the playoffs</a>.</p>\n' + citation.expansion_quick_cite() + '\n<h2 class="section-title">Portland and Toronto at a glance</h2>',
            'expansion cite',
        )
    needle = '<div class="table-wrap"><table>\n<thead><tr><th></th><th><a class="inline-link" href="/wnba/teams/portland-fire/" target="_blank" rel="noopener">Portland Fire</a> (2026)</th>'
    if 'id="year-1-expansion-comparison"' not in html:
        html = once(
            html,
            needle,
            needle.replace('<div class="table-wrap">', '<div class="table-wrap" id="year-1-expansion-comparison">', 1),
            'year-1 id',
        )
    compare_embed = citation.embed_block(
        'year-1-expansion-comparison',
        citation.embed_snippet(citation.EXPANSION_URL, 'year-1-expansion-comparison'),
        'expansion.csv',
    )
    if 'embed-year-1-expansion-comparison' not in html:
        html = once(
            html,
            '</tbody></table></div>\n\n<p><a href="https://www.basketball-reference.com/wnba/teams/GSV/"',
            '</tbody></table></div>\n' + compare_embed + '\n<p><a href="https://www.basketball-reference.com/wnba/teams/GSV/"',
            'year-1 embed',
        )
    draft_embed = citation.embed_block(
        'expansion-draft-picks',
        citation.embed_snippet(citation.EXPANSION_URL, 'expansion-draft-picks'),
        'expansion.csv',
    )
    if 'embed-expansion-draft-picks' not in html:
        html = once(
            html,
            '</table></div>\n\n<h2 class="section-title">First-season results</h2>',
            '</table></div>\n' + draft_embed + '\n<h2 class="section-title">First-season results</h2>',
            'draft embed',
        )
    if 'id="expansion-draft-coin-toss"' not in html:
        html = once(
            html,
            '<li><a href="https://www.espn.com/wnba/story/_/id/48322982/tempo-win-wnba-expansion-coin-toss-choose-draft-sixth" target="_blank" rel="noopener">Toronto won',
            '<li id="expansion-draft-coin-toss"><a href="https://www.espn.com/wnba/story/_/id/48322982/tempo-win-wnba-expansion-coin-toss-choose-draft-sixth" target="_blank" rel="noopener">Toronto won',
            'coin toss id',
        )
    if 'id="expansion-fee-table"' not in html:
        html = once(
            html,
            '<h2 class="section-title">FAQ</h2>',
            citation.expansion_fee_block() + '\n<h2 class="section-title">FAQ</h2>',
            'fee table',
        )
    html = number_sources(html)
    if 'href="#source-7"' not in html.split('id="sources"')[0] if 'id="sources"' in html else 'href="#source-7"' not in html:
        # Footnotes in the body, not inside the source list. Add them before numbering would duplicate.
        pass
    if html.count('href="#source-7"') < 2:
        html = once(
            html,
            'didn\'t take the No. 1 expansion pick</a>.',
            'didn\'t take the No. 1 expansion pick</a> <a href="#source-7">[7]</a>.',
            'coin footnote',
        )
    if html.count('href="#source-17"') < 2:
        html = once(
            html,
            'paid a $250 million expansion fee, per AP</a>.',
            'paid a $250 million expansion fee, per AP</a> <a href="#source-17">[17]</a>.',
            'fee footnote',
        )
    html = citation.add_heading_anchors(html, citation.EXPANSION_FORCED)
    save(relative, under_headline(html))


def apply_liberty() -> None:
    relative = 'news/liberty-offseason-five-gm-moves/index.html'
    headers = ['measure', 'liberty', 'dream', 'notes']
    rows = [
        ['Field-goal percentage', '47.1%', '42.0%', 'Three-game totals'],
        ['Turnovers', '45', '27', 'New York margin -18'],
        ['Offensive rebounds', '20', '29', ''],
        ['Field goals', '90 of 191', '94 of 224', 'Dream attempted 33 more shots'],
        ['Game scores', '82, 98, 83', '92, 101, 85', 'Game 2 went to overtime. Game 3 was 85-83.'],
        ['2027 salary cap', 'Unavailable', '', 'Not a published dollar figure on this page'],
        ['Six listed 2027 cap hits', '$5,224,516', '', 'Her Hoop Stats, Oct. 1, 2026'],
        ['Breanna Stewart 2026 cap hit', '$1,190,000', '', 'Newsweek, April 17, 2026'],
        ['Elizabeth Williams 2027 cap hit', '$600,000', '', 'Chicago contract cited for a proposed trade'],
        ['Manuela Puoch 2027 scale', '$288,600', '', 'Unsigned'],
    ]
    citation.write_csv(ROOT / 'news/liberty-offseason-five-gm-moves/liberty-series.csv', headers, rows)
    html = ensure_assets(load(relative))
    if 'id="sweep-stat-breakdown"' not in html:
        html = once(
            html,
            '<h2 class="section-title">1. Keep the five and address the lost possessions</h2>',
            citation.liberty_sweep_block() + '\n<h2 class="section-title">1. Keep the five and address the lost possessions</h2>',
            'liberty sweep',
        )
    if 'id="semifinal-totals"' not in html:
        html = once(
            html,
            '<div class="table-wrap">\n<table>\n<caption>Totals across three games',
            '<div class="table-wrap" id="semifinal-totals">\n<table>\n<caption>Totals across three games',
            'semifinal id',
        )
    totals_embed = citation.embed_block(
        'semifinal-totals',
        citation.embed_snippet(citation.LIBERTY_URL, 'semifinal-totals'),
        'liberty-series.csv',
    )
    if 'embed-semifinal-totals' not in html:
        html = once(
            html,
            '</table>\n</div>\n<p>Jonquel Jones had 26 points',
            '</table>\n</div>\n' + totals_embed + '\n<p>Jonquel Jones had 26 points',
            'totals embed',
        )
    if 'id="liberty-2027-contracts"' not in html:
        html = once(
            html,
            '<h2 class="section-title">5. Set spending limits before filling the last six spots</h2>',
            citation.liberty_contract_block() + '\n<h2 class="section-title">5. Set spending limits before filling the last six spots</h2>',
            'contracts',
        )
    html = citation.add_heading_anchors(html, citation.LIBERTY_FORCED)
    save(relative, under_headline(html))


def apply_contact_line() -> None:
    author = 'authors/ryan-moalemi/index.html'
    html = load(author)
    if 'ryan@fullcourtbuckets.com' not in html:
        html = ensure_assets(html)
        html = once(
            html,
            '<p>My goal for Full Court Buckets is to cover the WNBA thoughtfully and fairly, with genuine respect for every player in the league. I hope our coverage highlights their talent, gives their stories the attention they deserve, and inspires more people to become fans.</p>',
            '<p>My goal for Full Court Buckets is to cover the WNBA thoughtfully and fairly, with genuine respect for every player in the league. I hope our coverage highlights their talent, gives their stories the attention they deserve, and inspires more people to become fans.</p>\n' + citation.media_line_html(),
            'author line',
        )
        save(author, html)
    contact = 'contact/index.html'
    html = load(contact)
    if 'ryan@fullcourtbuckets.com' not in html:
        html = ensure_assets(html)
        html = once(
            html,
            '<h2>Response time</h2>',
            citation.media_line_html() + '\n<h2>Response time</h2>',
            'contact line',
        )
        save(contact, html)


def main() -> None:
    apply_viewership()
    apply_cards()
    apply_expansion()
    apply_liberty()
    apply_contact_line()
    print('citation blocks inserted')


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()

#!/usr/bin/env python3
"""Retired writer for /news/2026-wnba-finals-ratings-tracker/.

That URL is the WNBA Finals attendance database. main() does not write it.
article_html() remains so the old ratings markup can still be tested.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_viewership_attendance as viewership
import citation
import internal_links as links
import news_heroes
import site_nav

ROOT = Path(__file__).resolve().parents[1]
SLUG = citation.TRACKER_SLUG
HEADLINE = '2026 WNBA Finals ratings tracker: game-by-game TV viewers'
DESCRIPTION = (
    'Game-by-game TV viewers for the 2026 WNBA Finals, updated after each game, '
    'with citation, embed code and CSV.'
)
IMAGE_DIR = ROOT / 'images' / 'articles' / SLUG
SOURCE_NAME = 'ratings-sheet.webp'
SOCIAL_NAME = 'social-card.webp'
SOCIAL_WIDTH = 1200
SOCIAL_HEIGHT = 630
MATCHUP_PAGE = (1200, 675)
MATCHUP_OG = (1200, 630)
MATCHUP_PAGE_NAME = 'matchup-1200.webp'
MATCHUP_OG_NAME = 'matchup-og.webp'
REESE_PHOTO = ROOT / 'images' / 'articles' / 'wnba-finals-2026-audience-growth-dream-valkyries' / 'angel-reese-dream-2026.webp'
CARD_TITLE = '2026 WNBA Finals Ratings Tracker'
BASELINE_SOCIAL_STAT = '51 telecasts topped 1M viewers in 2026 (up from 19)'
HUB_FORCED = {
    '2026 wnba finals game-by-game ratings': 'finals-ratings-tracker',
    'regular-season and playoff benchmarks': 'finals-benchmarks',
    'october search interest': 'october-search-interest',
    'finals average viewers, where a source is on file': 'finals-average-viewers',
    'figures left off this page': 'figures-left-off',
}
ARCHIVE_NOTE = (
    '<p>This preview was published before the game. For the result, read our game recap. '
    f'<a href="{citation.TRACKER_PATH}">2026 WNBA Finals ratings tracker</a>.</p>'
)


HERO_ALT = 'Angel Reese of the Atlanta Dream in a white number 5 jersey looks up'
HERO_CREDIT = 'Photo: John Mac, CC BY-SA 4.0, via Wikimedia Commons'
PENDING_HEADLINE = (
    'Game 1 Sat Oct 17, 12:30 PM PT on NBC/Peacock; ratings pending. '
    'The 2025 Finals averaged 1.5 million.'
)
ONE_LINE_CITE = (
    'Full Court Buckets, "2026 WNBA Finals ratings tracker: game-by-game TV viewers," '
    'October 14, 2026. https://fullcourtbuckets.com/news/2026-wnba-finals-ratings-tracker/'
)
PAST_FINALS = ((2022, 534_000), (2023, 728_000), (2024, 1_600_000), (2025, 1_500_000))
_MONTH_NUM = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
}
_CLUB = {
    'Atlanta Dream': 'ATL',
    'Golden State Valkyries': 'GSV',
}
REESE_CREDIT = (
    '<p class="tracker-credit">Photo: Angel Reese of the Atlanta Dream, May 27, 2026. '
    '<a class="inline-link" href="https://commons.wikimedia.org/wiki/File:Angel_Reese_Dream_2.jpg" target="_blank" rel="noopener">John Mac</a>, '
    '<a class="inline-link" href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>, '
    'via <a class="inline-link" href="https://commons.wikimedia.org/wiki/File:Angel_Reese_Dream_2.jpg" target="_blank" rel="noopener">Wikimedia Commons</a>. '
    'The photo is the card and the social image.</p>'
)


def _millions(viewers: int) -> str:
    if viewers >= 1_000_000 and viewers % 10_000 == 0:
        text = f'{viewers / 1_000_000:.2f}'.rstrip('0').rstrip('.')
        return f'{text} million'
    return f'{viewers:,}'


def tracker_social_headline(payload: dict | None) -> str:
    """Baseline season stat, or the latest Finals game that has a released audience.

    A released number is an integer viewers field on a Finals game in the
    viewership file. The newest date wins. Pending cells stay off the card.
    """
    released = []
    for row in (payload or {}).get('games') or []:
        game = str(row.get('game') or '')
        if not game.startswith('Finals Game '):
            continue
        viewers = row.get('viewers')
        if isinstance(viewers, bool) or not isinstance(viewers, int) or viewers <= 0:
            continue
        released.append((str(row.get('date') or ''), game, viewers))
    if not released:
        return BASELINE_SOCIAL_STAT
    _date, game, viewers = max(released)
    number = game.replace('Finals Game ', '', 1).strip()
    return f'Game {number} averaged {_millions(viewers)} viewers'


def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines = []
    current = ''
    for word in text.split():
        trial = word if not current else f'{current} {word}'
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or ['']


def _face_centered_crop(image: Image.Image, width: int, height: int) -> Image.Image:
    """Crop to the frame with the largest detected face at the center.

    The homepage card uses object-fit: cover and object-position center, so the
    face has to sit in the middle of both the 16:9 card and the shorter og frame.
    """
    src = image.convert('RGB')
    sw, sh = src.size
    target = width / height
    if sw / sh > target:
        crop_w = int(round(sh * target))
        crop_h = sh
    else:
        crop_w = sw
        crop_h = int(round(sw / target))
    crop_w = min(crop_w, sw)
    crop_h = min(crop_h, sh)
    faces = news_heroes.detect_faces(src)
    if faces:
        x, y, fw, fh = max(faces, key=lambda box: box[2] * box[3])
        cx = x + fw / 2
        cy = y + fh / 2
    else:
        cx, cy = sw / 2, sh * 0.38
    left = max(0, min(int(round(cx - crop_w / 2)), sw - crop_w))
    top = max(0, min(int(round(cy - crop_h / 2)), sh - crop_h))
    cropped = src.crop((left, top, left + crop_w, top + crop_h))
    return cropped.resize((width, height), Image.Resampling.LANCZOS)


def draw_matchup(size: tuple[int, int], dest: Path) -> Path:
    """Angel Reese alone. Page frame is 1200x675; the og crop is 1200x630.

    The source is the credited Dream photo already in the repo. The frame is
    the photo only. A missing file stops the build.
    """
    if not REESE_PHOTO.is_file():
        raise SystemExit(f'matchup photo is missing: {REESE_PHOTO.relative_to(ROOT)}')
    with Image.open(REESE_PHOTO) as reese:
        canvas = _face_centered_crop(reese, size[0], size[1])
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, 'WEBP', quality=86, method=6)
    return dest


def _short_viewers(viewers: int) -> str:
    if viewers >= 1_000_000:
        text = f'{viewers / 1_000_000:.2f}'.rstrip('0').rstrip('.')
        return f'{text}M'
    if viewers >= 1_000:
        return f'{round(viewers / 1000)}K'
    return f'{viewers:,}'


def headline_stat(payload: dict | None) -> str:
    """Latest released Finals audience, or the Game 1 pending line, plus 2025."""
    line = tracker_social_headline(payload)
    if line == BASELINE_SOCIAL_STAT:
        return PENDING_HEADLINE
    return f'{line}. The 2025 Finals averaged 1.5 million.'


def _short_date(text: str) -> str:
    match = re.match(r'([A-Z][a-z]{2}),\s+([A-Z][a-z]{2})\.?\s+(\d{1,2})', text)
    if not match or match.group(2) not in _MONTH_NUM:
        return text
    return f'{match.group(1)} {_MONTH_NUM[match.group(2)]}/{int(match.group(3))}'


def _short_matchup(text: str) -> str:
    teams = text.split(',', 1)[0]
    if ' at ' not in teams:
        return teams
    away, home = teams.split(' at ', 1)
    return f'{_CLUB.get(away.strip(), away.strip())} @ {_CLUB.get(home.strip(), home.strip())}'


def _short_network(text: str) -> str:
    return text.replace(' and ', '/').replace(', ', '/')


def _short_tip(text: str) -> str:
    parts = re.findall(r'(\d{1,2}:\d{2})\s*([ap])\.?m\.?', text, re.I)
    if len(parts) < 2:
        return text
    (left, left_mer), (right, right_mer) = parts[0], parts[1]
    meridians = tuple('AM' if mer.lower() == 'a' else 'PM' for mer in (left_mer, right_mer))
    if meridians[0] == meridians[1]:
        return f'{left} / {right} {meridians[0]}'
    return f'{left} {meridians[0]} / {right} {meridians[1]}'


def _compact_viewers(game_no: str, row: list, payload: dict | None) -> str:
    for item in (payload or {}).get('games') or []:
        if str(item.get('game') or '') != f'Finals Game {game_no}':
            continue
        viewers = item.get('viewers')
        if isinstance(viewers, bool) or not isinstance(viewers, int) or viewers <= 0:
            break
        return _short_viewers(viewers)
    cell = row[6] if len(row) > 6 else 'Pending tip-off'
    if cell == 'Pending tip-off':
        return 'Pending'
    return str(cell)


def compact_ratings_table(payload: dict | None) -> str:
    """Four scheduled games, one line each. Games 5-7 stay in the footnote."""
    rows = []
    for row in citation.FINALS_TRACKER_ROWS:
        if row[-1] == 'If necessary':
            continue
        game, date, matchup, network, tip = row[:5]
        rows.append([
            game,
            _short_date(date),
            _short_matchup(matchup),
            _short_network(network),
            _short_tip(tip),
            _compact_viewers(game, row, payload),
        ])
    table = citation.data_table(
        ['Game', 'Date', 'Matchup', 'Network', 'Tip', 'Viewers'],
        rows,
    )
    table = table.replace(
        '<div class="fcb-table-wrap">',
        '<div class="fcb-table-wrap tracker-sheet">',
        1,
    )
    table = table.replace(
        '<table class="fcb-data-table">',
        f'<table class="fcb-data-table tracker-compact" aria-label="{links.esc(SHEET_HEADING)}">',
        1,
    )
    return (
        '<section class="tracker-sheet-block">\n'
        f'<h2 class="section-title" id="finals-ratings-tracker">{SHEET_HEADING}</h2>\n'
        f'{table}\n'
        f'{tracker_footnote()}\n'
        '</section>'
    )


def tracker_footnote() -> str:
    return (
        '<p class="tracker-note">Games 1-2: Chase Center. '
        'Games 3-4: State Farm Arena (Wed, Oct. 21, 2026). '
        'Game 4 tips at 1:00 p.m. ET / 10:00 a.m. PT. '
        'Games 5-7, if necessary, are on USA Network (simulcast on CNBC) and Peacock (' f'<a class="inline-link" href="{citation.USA_SPORTS_G3_RELEASE}">USA Sports release of Oct. 21, 2026</a>). '
        'Dates and tip times for those games are not listed. '
        'Viewer cells stay Pending tip-off. '
        f'<a class="inline-link" href="{citation.WNBA_FINALS_RELEASE}">WNBA release of Oct. 13, 2026</a>. '
        f'Networks: <a class="inline-link" href="{citation.NBC_FINALS_NETWORKS}">NBC Sports</a> '
        f'and the <a class="inline-link" href="{citation.VALKYRIES_FINALS_PREVIEW}">Valkyries</a>.</p>'
    )


def journalist_tools() -> str:
    return (
        '<nav class="tracker-tools" aria-label="Journalist tools">'
        f'<button type="button" class="fcb-tracker-cite" data-citation="{links.esc(ONE_LINE_CITE)}">Cite this</button>'
        '<a href="#finals-csv">Download CSV</a>'
        '<a href="#finals-embed">Embed</a>'
        '</nav>'
    )


NBC_REGULAR_SEASON = (
    'https://www.nbcsports.com/pressbox/press-releases/'
    'fever-sky-on-sunday-night-basketball-on-nbc-and-peacock-is-the-most-watched-'
    'wnba-regular-season-game-since-opening-weekend-of-leagues-inaugural-1997-season'
)
NBC_REGULAR_SEASON_VIEWERS = 1_750_000
NBC_REGULAR_SEASON_GAMES = 7
SHEET_HEADING = 'Finals games (ratings added after each game)'


def _past_finals_found(payload: dict | None) -> dict:
    found = {}
    for row in (payload or {}).get('seasons') or []:
        year = row.get('season')
        viewers = row.get('finals_avg_viewers')
        if year in {item[0] for item in PAST_FINALS} and isinstance(viewers, int) and viewers > 0:
            found[year] = viewers
    return found


def _past_finals_line(payload: dict | None) -> str:
    found = _past_finals_found(payload)
    parts = [f'{year} {_short_viewers(found.get(year, viewers))}' for year, viewers in PAST_FINALS]
    return ', '.join(parts)


def _past_finals_html(payload: dict | None) -> str:
    found = _past_finals_found(payload)
    parts = [
        f'<strong>{year} {_short_viewers(found.get(year, viewers))}</strong>'
        for year, viewers in PAST_FINALS
    ]
    return ', '.join(parts)


def _nbc_broadcast(payload: dict | None) -> tuple[int, int, str]:
    """NBC and Peacock regular-season average stored on the viewership file.

    The file's 2026 NBC row is 1,750,000 across 7 games, TV and streaming.
    A missing row keeps that verified fallback.
    """
    viewers = NBC_REGULAR_SEASON_VIEWERS
    games = NBC_REGULAR_SEASON_GAMES
    source = NBC_REGULAR_SEASON
    for row in (payload or {}).get('broadcasts') or []:
        if row.get('season') != 2026 or row.get('network') != 'NBC':
            continue
        value = row.get('avg_viewers')
        count = row.get('games')
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            viewers = value
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            games = count
        link = row.get('source')
        if isinstance(link, str) and link.startswith('http'):
            source = link
        break
    return viewers, games, source


def _nbc_fact_html(payload: dict | None) -> str:
    viewers, games, source = _nbc_broadcast(payload)
    return (
        f'NBC and Peacock averaged <strong>{_millions(viewers)}</strong> '
        f'across {games} regular-season games, TV and streaming '
        f'(<a href="{links.esc(source)}">NBC Sports, Aug. 26, 2026</a>).'
    )


def past_finals_averages(payload: dict | None) -> str:
    """Kept for a leftover section. The published page folds this line into fast facts."""
    return (
        '<section class="tracker-averages" id="past-finals-averages">'
        '<h2>Past Finals averages</h2>'
        f'<p>{_past_finals_line(payload)}.</p>'
        '</section>'
    )


def page_stat(payload: dict | None) -> str:
    """Latest released Finals audience. Empty until a game has a real viewer count."""
    line = tracker_social_headline(payload)
    if line == BASELINE_SOCIAL_STAT:
        return ''
    return f'{line}. The 2025 Finals averaged 1.5 million.'


def _tag_ratings_embed(block: str) -> str:
    block = block.replace('<div class="fcb-embed">', '<div class="fcb-embed" id="finals-embed">', 1)
    return block.replace('<a class="fcb-csv"', '<a id="finals-csv" class="fcb-csv"', 1)


def draw_social_card(payload: dict | None) -> Path:
    """1200x630 share card. Not used in the page body.

    Type is sized so a phone preview of this frame still reads the stat.
    """
    image = Image.new('RGB', (SOCIAL_WIDTH, SOCIAL_HEIGHT), (5, 5, 6))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 18, SOCIAL_HEIGHT), fill=(255, 152, 0))
    bold = ROOT / 'assets' / 'fonts' / 'Inter-Bold.ttf'
    medium = ROOT / 'assets' / 'fonts' / 'Inter-Medium.ttf'
    title_font = ImageFont.truetype(str(bold), 72)
    stat_font = ImageFont.truetype(str(bold), 64)
    mark_font = ImageFont.truetype(str(medium), 36)
    max_width = SOCIAL_WIDTH - 112
    title_lines = _wrap_lines(draw, CARD_TITLE, title_font, max_width)
    stat_lines = _wrap_lines(draw, tracker_social_headline(payload), stat_font, max_width)
    x = 56
    y = 56
    for line in title_lines:
        draw.text((x, y), line, font=title_font, fill=(255, 152, 0))
        y += 84
    y += 16
    for line in stat_lines:
        draw.text((x, y), line, font=stat_font, fill=(245, 243, 239))
        y += 76
    draw.text((x, SOCIAL_HEIGHT - 72), 'Full Court Buckets', font=mark_font, fill=(165, 161, 155))
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    dest = IMAGE_DIR / SOCIAL_NAME
    image.save(dest, 'WEBP', quality=86, method=6)
    return dest


def article_dict(source: Path) -> dict:
    rel = '/' + source.resolve().relative_to(ROOT.resolve()).as_posix()
    return {
        'slug': SLUG,
        'url': citation.TRACKER_PATH,
        'title': HEADLINE,
        'description': DESCRIPTION,
        'category': 'WNBA',
        'date': '2026-10-14',
        'image': rel,
        'imageAlt': HERO_ALT,
        'imageCredit': HERO_CREDIT,
        'teams': ['atlanta-dream', 'golden-state-valkyries'],
        'imageWidth': MATCHUP_PAGE[0],
        'imageHeight': MATCHUP_PAGE[1],
        'imageFocal': 'center center',
        'imageSource': rel,
    }


def shell_from_audience() -> str:
    html = (ROOT / 'news' / 'wnba-finals-2026-audience-growth-dream-valkyries' / 'index.html').read_text(encoding='utf-8')
    html = re.sub(r'<script type="application/ld\+json">.*?</script>', '', html, flags=re.S)
    start = html.find('<article')
    end = html.find('</article>')
    if start < 0 or end < 0:
        raise SystemExit('audience article shell is missing')
    return html[:start] + 'ARTICLE' + html[end + len('</article>'):]


def set_attr(html: str, pattern: str, value: str) -> str:
    return re.sub(pattern, lambda match: match.group(1) + value + match.group(3), html, count=1)


def write_head(html: str, article: dict) -> str:
    title = HEADLINE + ' | Full Court Buckets'
    html = re.sub(r'<title>.*?</title>', f'<title>{links.esc(title)}</title>', html, count=1, flags=re.S)
    html = set_attr(html, r'(<meta name="description" content=")(.*?)(")', links.esc(DESCRIPTION))
    html = set_attr(html, r'(<meta property="og:title" content=")(.*?)(")', links.esc(HEADLINE))
    html = set_attr(html, r'(<meta property="og:description" content=")(.*?)(")', links.esc(DESCRIPTION))
    html = set_attr(html, r'(<meta name="twitter:title" content=")(.*?)(")', links.esc(HEADLINE))
    html = set_attr(html, r'(<meta name="twitter:description" content=")(.*?)(")', links.esc(DESCRIPTION))
    html = set_attr(
        html,
        r'(<meta property="article:published_time" content=")(.*?)(")',
        article['date'],
    )
    html = html.replace(
        'Dream sweep the Liberty 85-83 and reach the WNBA Finals.',
        'Finals Game 1 is Saturday, Oct. 17. Viewer counts are pending.',
    )
    return html


def _tracker_table_block(rest: str) -> tuple[str, str]:
    """Pull the ratings heading and its table out of the hub body."""
    heading_at = rest.find('<h2')
    heading_end = rest.find('</h2>', heading_at)
    table_at = rest.find('<div class="fcb-table-wrap"', heading_end if heading_end >= 0 else 0)
    table_end = rest.find('</table></div>', table_at)
    if heading_at < 0 or heading_end < 0 or table_at < 0 or table_end < 0:
        return '', rest
    heading_end += len('</h2>')
    table_end += len('</table></div>')
    block = rest[heading_at:heading_end].strip() + '\n' + rest[table_at:table_end].strip()
    remainder = rest[:heading_at] + rest[heading_end:table_at] + rest[table_end:]
    return block, remainder


def _lower_sections(rest: str) -> tuple[str, str, str]:
    """Charts stay below the facts. The network note and ratings embed move to the sources."""
    _heading, rest = _tracker_table_block(rest)
    rest = re.sub(
        r'\s*<p>Games 1 through 4 are the only ones dated.*?</p>',
        '\n',
        rest,
        count=1,
        flags=re.S,
    )
    note_at = rest.find('<p class="fcb-note">')
    embed_at = rest.find('<div class="fcb-embed">')
    bench_at = rest.find('id="finals-benchmarks"')
    if note_at < 0 or embed_at < note_at or bench_at < embed_at:
        return '', '', rest.strip()
    heading_at = rest.rfind('<h2', 0, bench_at)
    if heading_at < 0:
        heading_at = bench_at
    note = rest[note_at:embed_at].strip()
    embed = _tag_ratings_embed(rest[embed_at:heading_at].strip())
    charts = rest[heading_at:].strip()
    return note, embed, charts


def _fast_facts(payload: dict) -> tuple[str, str]:
    """Existing fast-facts aside, with past Finals averages and the NBC average added."""
    blocks = citation.ratings_hub_blocks(payload)
    cite, _, rest = blocks.partition('</aside>')
    cite += '</aside>'
    extras = (
        f'<li>Past Finals averages: {_past_finals_html(payload)}.</li>\n'
        f'<li>{_nbc_fact_html(payload)}</li>\n'
    )
    cite = cite.replace('<ul>\n', '<ul>\n' + extras, 1)
    return cite, rest


def article_html(payload: dict) -> str:
    cite, rest = _fast_facts(payload)
    note, embed, charts = _lower_sections(rest)
    stat = page_stat(payload)
    stat_html = f'<p class="tracker-stat">{links.esc(stat)}</p>\n' if stat else ''
    sheet = compact_ratings_table(payload)
    tools = journalist_tools()
    if stat_html:
        top = f'{stat_html}{sheet}\n{cite}\n{tools}'
    else:
        top = f'{cite}\n{tools}\n{sheet}'
    return f'''<article class="article"><div class="meta-row"><span class="cat">WNBA</span><span class="divider"></span><span>Full Court Buckets</span></div><h1>{links.esc(HEADLINE)}</h1>
<div class="byline-row">{links.BYLINE_HTML}<time class="article-date" datetime="2026-10-14">October 14, 2026</time></div>
{top}
{charts}
{note}
{REESE_CREDIT}
{embed}
{citation.finals_tracker_update_callout(ROOT)}
<p class="how-made">How this story was made: drafted with AI tools from the sources linked above, then reviewed and edited by Ryan Moalemi. {links.HOW_MADE_LINK}</p>
<p class="brand-sign">Full Court Buckets &middot; WNBA News. Analysis. Commentary.</p></article>'''


def under_headline(html: str) -> str:
    """Keep the tracker order. Other pages put the quick cite under the lead photo."""
    if links._is_ratings_tracker_page(html, {'slug': SLUG}):
        return links.order_ratings_tracker(html)
    return links.place_quick_cite(html)


def save_article(article: dict, articles: list) -> None:
    path = ROOT / 'articles.json'
    rest = [item for item in articles if item.get('slug') != SLUG]
    path.write_text(json.dumps([article, *rest], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def insert_listing(relative: str, marker: str, card: str) -> None:
    path = ROOT / relative
    html = path.read_text(encoding='utf-8')
    if citation.TRACKER_PATH in html:
        return
    at = html.find(marker)
    if at < 0:
        raise SystemExit(f'{relative} is missing {marker}')
    at += len(marker)
    path.write_text(html[:at] + card + html[at:], encoding='utf-8')


def point_audience_story_at_the_hub() -> None:
    path = ROOT / 'news' / 'wnba-finals-2026-audience-growth-dream-valkyries' / 'index.html'
    html = path.read_text(encoding='utf-8')
    start = html.find('<h2 class="section-title" id="finals-ratings-tracker">')
    finish = html.find('<h2 class="section-title" id="finals-tv-schedule">')
    if start < 0 or finish < start:
        raise SystemExit('audience page is missing the tracker block')
    if citation.TRACKER_PATH not in html[start:finish]:
        html = html[:start] + citation.ratings_hub_crosslink() + '\n' + html[finish:]
    html = html.replace(
        'Published Full Court Buckets figures for 2026 WNBA audience averages, October search estimates, and the Finals schedule. Viewer cells for games that have not been played stay pending. ',
        'Published Full Court Buckets figures for 2026 WNBA audience averages and October search estimates. The game-by-game Finals sheet is the ratings tracker. ',
    )
    path.write_text(html, encoding='utf-8')


def refresh_news_itemlist() -> None:
    """The news hub test reads the first href on the page, which is the ItemList."""
    path = ROOT / 'news' / 'index.html'
    html = path.read_text(encoding='utf-8')
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    if not match or 'ItemList' not in match.group(1):
        raise SystemExit('news hub is missing its ItemList')
    data = json.loads(match.group(1))
    articles = links._ordered_articles(links.load_articles(ROOT))
    items = []
    for index, article in enumerate(articles, 1):
        items.append({
            '@type': 'ListItem',
            'position': index,
            'url': links.article_absolute(article),
            'name': article.get('title') or '',
        })
    graph = data.get('@graph') or []
    updated = False
    for node in graph:
        entity = node.get('mainEntity') or {}
        if entity.get('@type') == 'ItemList':
            entity['numberOfItems'] = len(items)
            entity['itemListElement'] = items
            updated = True
    if not updated:
        raise SystemExit('news hub ItemList was not updated')
    blob = json.dumps(data, ensure_ascii=False, separators=(', ', ': '))
    path.write_text(html[:match.start(1)] + blob + html[match.end(1):], encoding='utf-8')


def refresh_html_sitemap() -> None:
    path = ROOT / 'sitemap' / 'index.html'
    html = path.read_text(encoding='utf-8')
    href = citation.TRACKER_PATH
    if f'href="{href}"' in html:
        return
    marker = '<section class="section" id="sitemap-news"><h2>News</h2><ul class="sitemap-list">'
    if marker not in html:
        raise SystemExit('HTML sitemap is missing the news list')
    item = f'<li><a href="{href}">{links.esc(HEADLINE)}</a></li>'
    path.write_text(html.replace(marker, marker + item, 1), encoding='utf-8')


def refresh_team_stories() -> None:
    """Team pages list this story when the club is named, and as a league fallback otherwise."""
    import team_season

    pattern = re.compile(r'<section class="section" id="team-news">.*?</section>', re.S)
    for page in sorted((ROOT / 'wnba' / 'teams').glob('*/index.html')):
        slot = links._slot_for_slug(ROOT, page.parent.name)
        expected = team_season.stories_section(ROOT, slot)
        html = page.read_text(encoding='utf-8')
        match = pattern.search(html)
        if not match or not expected or match.group(0) == expected:
            continue
        page.write_text(html[:match.start()] + expected + html[match.end():], encoding='utf-8')
    import team_coverage
    team_coverage.refresh(ROOT)


def add_archive_note() -> None:
    path = ROOT / 'news' / 'finals-game-1-preview-dream-valkyries' / 'index.html'
    html = path.read_text(encoding='utf-8')
    if 'This preview was published before the game.' in html:
        return
    marker = '</time></div>'
    if marker not in html:
        raise SystemExit('Game 1 preview byline marker is missing')
    html = html.replace(marker, marker + ARCHIVE_NOTE, 1)
    path.write_text(html, encoding='utf-8')


OLD_LISTING_ALT = (
    'Angel Reese of the Atlanta Dream in a white Dream jersey beside '
    'Cecilia Zandalasini of the Golden State Valkyries'
)


def replace_listing_alt() -> None:
    """The card filename stays. Listings that baked the old two-player alt get the Reese line."""
    for path in ROOT.rglob('*.html'):
        if '__pycache__' in path.parts:
            continue
        text = path.read_text(encoding='utf-8')
        if OLD_LISTING_ALT not in text:
            continue
        path.write_text(text.replace(OLD_LISTING_ALT, HERO_ALT), encoding='utf-8')


def main() -> None:
    """Leave the attendance page in place. This builder no longer publishes it."""
    print(
        'Skipped. /news/2026-wnba-finals-ratings-tracker/ is the attendance database. '
        'This builder does not write that page.',
        file=sys.stderr,
    )
    return
    payload = json.loads((ROOT / 'data' / 'viewership-attendance.json').read_text(encoding='utf-8'))
    page_image = draw_matchup(MATCHUP_PAGE, IMAGE_DIR / MATCHUP_PAGE_NAME)
    og_image = draw_matchup(MATCHUP_OG, IMAGE_DIR / MATCHUP_OG_NAME)
    articles = links.load_articles(ROOT)
    article = next(item for item in articles if item.get('slug') == SLUG)
    page_rel = '/' + page_image.resolve().relative_to(ROOT.resolve()).as_posix()
    og_rel = '/' + og_image.resolve().relative_to(ROOT.resolve()).as_posix()
    article['title'] = HEADLINE
    article['description'] = DESCRIPTION
    article['image'] = page_rel
    article['imageAlt'] = HERO_ALT
    article['imageCredit'] = HERO_CREDIT
    article['imageWidth'] = MATCHUP_PAGE[0]
    article['imageHeight'] = MATCHUP_PAGE[1]
    article['imageFocal'] = 'center center'
    article['imageSource'] = page_rel
    article['imageHero'] = page_rel
    article['imageHeroWidth'] = MATCHUP_PAGE[0]
    article['imageHeroHeight'] = MATCHUP_PAGE[1]
    article.pop('imageHero2x', None)
    article.pop('imageHero2xWidth', None)
    article.pop('imageHero2xHeight', None)
    article['imageOg'] = og_rel
    article['imageOgWidth'] = MATCHUP_OG[0]
    article['imageOgHeight'] = MATCHUP_OG[1]
    news_heroes.ensure_article_hero(ROOT, article)
    save_article(article, articles)
    articles = links.load_articles(ROOT)
    article = next(item for item in articles if item['slug'] == SLUG)
    payload = json.loads((ROOT / 'data' / 'viewership-attendance.json').read_text(encoding='utf-8'))
    headers, rows = citation.ratings_hub_csv_rows(payload)
    citation.write_csv(ROOT / 'news' / SLUG / 'finals-ratings.csv', headers, rows)
    page = shell_from_audience()
    page = write_head(page, article)
    page = page.replace('ARTICLE', article_html(payload), 1)
    absolute = links.article_absolute(article)
    page = links._upsert_meta(page, absolute, DESCRIPTION)
    page = links.ensure_author_meta(page)
    page = links._upsert_article_schema(page, article, absolute)
    page = links._insert_visible_breadcrumb(page, HEADLINE)
    page = links.ensure_how_made(page, article)
    page = links.ensure_byline(page)
    page = links.order_news_lead(page, article)
    page = links.ensure_article_end(page, ROOT, article, articles)
    page = news_heroes.apply_article_html(page, article)
    page = under_headline(page)
    page = citation.add_heading_anchors(page, HUB_FORCED)
    dataset = citation.dataset_script(
        '2026 WNBA Finals game-by-game ratings',
        'Dates, networks, and tip times for the 2026 WNBA Finals from the Oct. 13, 2026 WNBA release, plus published season benchmarks. Viewer cells stay pending until tip-off. Full Court Buckets gathers and verifies its own data.',
        citation.TRACKER_URL,
        citation.TRACKER_URL + 'finals-ratings.csv',
    )
    if '"@type": "Dataset"' not in page and '"@type":"Dataset"' not in page:
        page = page.replace('</head>', dataset + '\n</head>', 1)
    page = site_nav.install(page, citation.TRACKER_PATH, site_nav.build_menu(ROOT))
    dest = ROOT / 'news' / SLUG / 'index.html'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page, encoding='utf-8')
    stub = ROOT / SLUG / 'index.html'
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(links.redirect_stub(article), encoding='utf-8')
    card = links._news_list_item(article)
    insert_listing('news/index.html', '<ol class="news-list">', card)
    insert_listing('authors/ryan-moalemi/index.html', '<h2>Stories</h2>\n<ol class="news-list">', card)
    home = ROOT / 'index.html'
    home.write_text(links.apply_homepage(home.read_text(encoding='utf-8'), articles), encoding='utf-8')
    sitemap = ROOT / 'pages-sitemap.xml'
    sitemap.write_text(links.sync_news_sitemap(sitemap.read_text(encoding='utf-8'), articles), encoding='utf-8')
    (ROOT / 'search-index.json').write_text(site_nav.search_index_document(ROOT), encoding='utf-8')
    point_audience_story_at_the_hub()
    add_archive_note()
    refresh_news_itemlist()
    refresh_html_sitemap()
    replace_listing_alt()
    refresh_team_stories()
    viewership.build(ROOT)
    print(f'Wrote {dest.relative_to(ROOT)}')


if __name__ == '__main__':
    main()

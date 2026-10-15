#!/usr/bin/env python3
"""Publish /news/2026-wnba-finals-ratings-tracker/ from the shared Finals rows.

The game-by-game sheet is citation.FINALS_TRACKER_ROWS, which matches
data/viewership-attendance.json and the Oct. 13, 2026 WNBA release.
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
MATCHUP_LABEL = '2026 WNBA Finals Ratings Tracker'
REESE_PHOTO = ROOT / 'images' / 'articles' / 'wnba-finals-2026-audience-growth-dream-valkyries' / 'angel-reese-dream-2026.webp'
ZANDA_PHOTO = ROOT / 'images' / 'articles' / 'finals-game-1-preview-dream-valkyries' / 'cecilia-zandalasini-valkyries-2026.webp'
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


HERO_ALT = (
    'Angel Reese of the Atlanta Dream in a white Dream jersey beside '
    'Cecilia Zandalasini of the Golden State Valkyries'
)
HERO_CREDIT = 'Photos: John Mac, CC BY-SA 4.0, via Wikimedia Commons'
MATCHUP_CAPTION = (
    'Angel Reese of the Atlanta Dream, May 27, 2026. Photo: '
    '<a class="inline-link" href="https://commons.wikimedia.org/wiki/File:Angel_Reese_Dream_2.jpg" target="_blank" rel="noopener">John Mac</a>, '
    '<a class="inline-link" href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>, '
    'via <a class="inline-link" href="https://commons.wikimedia.org/wiki/File:Angel_Reese_Dream_2.jpg" target="_blank" rel="noopener">Wikimedia Commons</a>. '
    'Cecilia Zandalasini with the Valkyries at Target Center on Aug. 24, 2026, not from this series. Photo: '
    '<a class="inline-link" href="https://commons.wikimedia.org/wiki/File:260824_Lynx_Valkries_JohnMc249_(55485544642).jpg" target="_blank" rel="noopener">John Mac</a> / '
    '<a class="inline-link" href="https://commons.wikimedia.org/wiki/File:260824_Lynx_Valkries_JohnMc249_(55485544642).jpg" target="_blank" rel="noopener">Wikimedia Commons</a> '
    '(<a class="inline-link" href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>).'
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


def _head_safe_panel(image: Image.Image, width: int, height: int) -> Image.Image:
    """Fill one half of the frame without cutting off the top of the head.

    A landscape photo keeps its full height and loses side margins.
    A portrait photo keeps the top of the frame, where these credited
    shots place the player's head.
    """
    src = image.convert('RGB')
    sw, sh = src.size
    target = width / height
    if sw / sh > target:
        crop_w = int(round(sh * target))
        left = max(0, (sw - crop_w) // 2)
        src = src.crop((left, 0, left + crop_w, sh))
    else:
        crop_h = min(sh, int(round(sw / target)))
        src = src.crop((0, 0, sw, crop_h))
    return src.resize((width, height), Image.Resampling.LANCZOS)


def _label_overlay(width: int, height: int) -> Image.Image:
    """Dark gradient strip with the tracker name, sized for a phone preview."""
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    strip = int(height * 0.38)
    start = height - strip
    for y in range(start, height):
        fade = (y - start) / max(1, strip - 1)
        alpha = int(235 * (fade ** 1.05))
        draw.line([(0, y), (width, y)], fill=(5, 5, 6, alpha))
    font_size = 72 if width >= 1200 else 56
    font = ImageFont.truetype(str(ROOT / 'assets' / 'fonts' / 'Inter-Bold.ttf'), font_size)
    lines = _wrap_lines(draw, MATCHUP_LABEL, font, width - 80)
    line_h = int(font_size * 1.12)
    y = height - (line_h * len(lines)) - 26
    for line in lines:
        text_w = draw.textlength(line, font=font)
        draw.text(((width - text_w) / 2, y), line, font=font, fill=(245, 243, 239, 255))
        y += line_h
    return overlay


def draw_matchup(size: tuple[int, int], dest: Path) -> Path:
    """Side-by-side credited photos. Page frame is 1200x675; the og crop is 1200x630.

    Sources are the Dream and Valkyries photos already published with credit.
    Missing files stop the build instead of substituting another picture.
    """
    missing = [path for path in (REESE_PHOTO, ZANDA_PHOTO) if not path.is_file()]
    if missing:
        names = ', '.join(str(path.relative_to(ROOT)) for path in missing)
        raise SystemExit(f'matchup photos are missing: {names}')
    width, height = size
    half = width // 2
    with Image.open(REESE_PHOTO) as reese, Image.open(ZANDA_PHOTO) as zanda:
        left = _head_safe_panel(reese, half, height)
        right = _head_safe_panel(zanda, width - half, height)
    canvas = Image.new('RGB', size, (5, 5, 6))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (half, 0))
    seam = ImageDraw.Draw(canvas)
    seam.rectangle((half - 2, 0, half + 1, height), fill=(5, 5, 6))
    framed = Image.alpha_composite(canvas.convert('RGBA'), _label_overlay(width, height))
    dest.parent.mkdir(parents=True, exist_ok=True)
    framed.convert('RGB').save(dest, 'WEBP', quality=86, method=6)
    return dest


def matchup_figure() -> str:
    """Compact photo under the summary. The ratings table stays directly below it."""
    src = f'/images/articles/{SLUG}/{MATCHUP_PAGE_NAME}'
    width, height = MATCHUP_PAGE
    return (
        f'<figure class="tracker-matchup"><img src="{src}" alt="{links.esc(HERO_ALT)}" '
        f'width="{width}" height="{height}" decoding="async" fetchpriority="high" '
        f'style="object-position:center center"><figcaption>{MATCHUP_CAPTION}</figcaption></figure>'
    )


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


def article_html(payload: dict) -> str:
    blocks = citation.ratings_hub_blocks(payload)
    cite, _, rest = blocks.partition('</aside>')
    cite += '</aside>'
    table, after = _tracker_table_block(rest)
    summary = (
        '<p class="lead">The WNBA set four 2026 Finals games on Oct. 13, '
        'and not one of them has a released audience.</p>'
    )
    return f'''<article class="article"><div class="meta-row"><span class="cat">WNBA</span><span class="divider"></span><span>Full Court Buckets</span></div><h1>{links.esc(HEADLINE)}</h1>
<div class="byline-row">{links.BYLINE_HTML}<time class="article-date" datetime="2026-10-14">October 14, 2026</time></div>
{summary}
{matchup_figure()}
{table}
{cite}
{citation.finals_tracker_update_callout(ROOT)}
<p>Game 1 is Saturday, Oct. 17, at 3:30 p.m. ET on NBC and Peacock, with the <a class="inline-link" href="/wnba/teams/atlanta-dream/" target="_blank" rel="noopener">Atlanta Dream</a> at the <a class="inline-link" href="/wnba/teams/golden-state-valkyries/" target="_blank" rel="noopener">Golden State Valkyries</a>. Games 5, 6 and 7 are if necessary. The Oct. 13 release does not list their dates or tip times. NBC Sports and the Valkyries list those games on USA and Peacock.</p>
<p>Game 3 is Wednesday, Oct. 21, at State Farm Arena, at 8:00 p.m. ET on USA and Peacock. That is the schedule to cite while the viewer cells stay empty.</p>
{after}
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


def main() -> None:
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
    refresh_team_stories()
    viewership.build(ROOT)
    print(f'Wrote {dest.relative_to(ROOT)}')


if __name__ == '__main__':
    main()

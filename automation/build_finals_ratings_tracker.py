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
HEADLINE = 'Four 2026 WNBA Finals games are set, and every viewer count is still pending'
DESCRIPTION = (
    'Four 2026 WNBA Finals games are on the Oct. 13 schedule. '
    'Viewer cells stay pending until tip-off.'
)
IMAGE_DIR = ROOT / 'images' / 'articles' / SLUG
SOURCE_NAME = 'ratings-sheet.webp'
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


def draw_sheet() -> Path:
    """16:9 artwork. The hero crop stays 16:9. Open Graph uses the site's 1.91 crop."""
    width, height = 2400, 1350
    image = Image.new('RGB', (width, height), (7, 7, 10))
    draw = ImageDraw.Draw(image)
    for x in range(18):
        color = (
            int(125 + (241 - 125) * x / 17),
            int(53 + (0 - 53) * x / 17),
            int(255 + (145 - 255) * x / 17),
        )
        draw.rectangle((0, x * 4, width, x * 4 + 4), fill=color)
    bold = ImageFont.truetype(str(ROOT / 'assets' / 'fonts' / 'Inter-Bold.ttf'), 84)
    medium = ImageFont.truetype(str(ROOT / 'assets' / 'fonts' / 'Inter-Medium.ttf'), 40)
    small = ImageFont.truetype(str(ROOT / 'assets' / 'fonts' / 'Inter-Medium.ttf'), 32)
    draw.text((120, 150), 'FULL COURT BUCKETS', font=medium, fill=(255, 152, 0))
    draw.text((120, 230), 'Viewer counts are still pending', font=bold, fill=(245, 243, 239))
    draw.text((120, 350), '2026 WNBA Finals. Four games from the Oct. 13 release.', font=medium, fill=(210, 204, 198))
    rows = (
        'Game 1   Sat, Oct. 17   NBC, Peacock          Pending tip-off',
        'Game 2   Mon, Oct. 19   USA, CNBC, Peacock    Pending tip-off',
        'Game 3   Wed, Oct. 21   USA, CNBC, Peacock    Pending tip-off',
        'Game 4   Sat, Oct. 24   NBC, Peacock          Pending tip-off',
        'Games 5-7   Not listed in that release',
    )
    y = 500
    for row in rows:
        draw.text((120, y), row, font=small, fill=(245, 243, 239))
        y += 90
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    dest = IMAGE_DIR / SOURCE_NAME
    image.save(dest, 'WEBP', quality=82, method=6)
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
        'imageAlt': 'Chart of the 2026 WNBA Finals schedule with viewer counts still pending',
        'imageCredit': 'Chart: Full Court Buckets',
        'teams': ['atlanta-dream', 'golden-state-valkyries'],
        'imageWidth': 2400,
        'imageHeight': 1350,
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


def article_html(payload: dict) -> str:
    blocks = citation.ratings_hub_blocks(payload)
    cite, _, rest = blocks.partition('</aside>')
    cite += '</aside>'
    return f'''<article class="article"><div class="meta-row"><span class="cat">WNBA</span><span class="divider"></span><span>Full Court Buckets</span></div><h1>{links.esc(HEADLINE)}</h1>
{cite}
<figure class="lead-photo"><img src="/images/articles/{SLUG}/{SOURCE_NAME}" alt="Chart of the 2026 WNBA Finals schedule with viewer counts still pending" width="2400" height="1350"><figcaption>The 2026 WNBA Finals ratings sheet. Viewer cells stay pending until a network releases them. Chart: Full Court Buckets.</figcaption></figure>
{links.BYLINE_HTML}<time class="article-date" datetime="2026-10-14">October 14, 2026</time>
<p class="lead">The WNBA set four 2026 Finals games on Oct. 13, and not one of them has a released audience.</p>
<p>Game 1 is Saturday, Oct. 17, at 3:30 p.m. ET on NBC and Peacock, with the <a class="inline-link" href="/wnba/teams/atlanta-dream/" target="_blank" rel="noopener">Atlanta Dream</a> at the <a class="inline-link" href="/wnba/teams/golden-state-valkyries/" target="_blank" rel="noopener">Golden State Valkyries</a>. Games 5, 6 and 7 are if necessary, and the Oct. 13 release does not list them.</p>
<p>Game 3 is Wednesday, Oct. 21, at State Farm Arena, at 8:00 p.m. ET on USA, CNBC and Peacock. That is the schedule to cite while the viewer cells stay empty.</p>
{rest}
<p class="how-made">How this story was made: drafted with AI tools from the sources linked above, then reviewed and edited by Ryan Moalemi. {links.HOW_MADE_LINK}</p>
<p class="brand-sign">Full Court Buckets &middot; WNBA News. Analysis. Commentary.</p></article>'''


def under_headline(html: str) -> str:
    match = re.search(r'\n?<aside class="fcb-quick-cite".*?</aside>\n?', html, re.S)
    if not match:
        return html
    block = match.group(0).strip()
    html = html[:match.start()] + html[match.end():]
    at = html.find('</h1>')
    if at < 0:
        return block + html
    return html[:at + len('</h1>')] + '\n' + block + '\n' + html[at + len('</h1>'):]


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


def add_archive_note() -> None:
    path = ROOT / 'news' / 'finals-game-1-preview-dream-valkyries' / 'index.html'
    html = path.read_text(encoding='utf-8')
    if 'This preview was published before the game.' in html:
        return
    needle = '</time></div><p class="lead">'
    if needle not in html:
        raise SystemExit('Game 1 preview byline marker is missing')
    html = html.replace(needle, '</time></div>' + ARCHIVE_NOTE + '<p class="lead">', 1)
    path.write_text(html, encoding='utf-8')


def main() -> None:
    source = draw_sheet()
    article = article_dict(source)
    news_heroes.ensure_article_hero(ROOT, article)
    articles = [item for item in links.load_articles(ROOT) if item.get('slug') != SLUG]
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

#!/usr/bin/env python3
"""Turn content/articles/<slug>/ into the news pages the site already uses.

A folder holds article.md and photo.jpg. This writes news/<slug>/index.html from
the shared article chrome, the root redirect, the hero and social images, and the
listings the last recap was added to. Running it again changes nothing.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))

import internal_links as links  # noqa: E402
import news_heroes  # noqa: E402
import rss_feed  # noqa: E402
import site_nav  # noqa: E402
import team_coverage  # noqa: E402

CONTENT = ROOT / 'content' / 'articles'
SHELL_PAGE = ROOT / 'news' / 'dream-valkyries-finals-game-1-recap' / 'index.html'
DISCLAIMER = '21+. Gamble responsibly. 1-800-GAMBLER.'
BETTING_RE = re.compile(r'betting odds|DraftKings|moneyline|Gamble responsibly', re.I)
SIZES = '(max-width: 900px) calc(94vw - 40px), 842px'
BROADCAST_STYLE = 'font-size:14px;color:#8a877f;margin:18px 0 0'
TRACKER_PATH = '/news/2026-wnba-finals-ratings-tracker/'


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith('---'):
        raise ValueError('article.md must start with front matter')
    parts = text.split('---', 2)
    if len(parts) < 3:
        raise ValueError('article.md front matter is not closed')
    meta: dict = {}
    key = None
    for line in parts[1].splitlines():
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith('- ') and key:
            meta.setdefault(key, [])
            if not isinstance(meta[key], list):
                raise ValueError(f'{key} mixes a value and a list')
            meta[key].append(stripped[2:].strip().strip('"').strip("'"))
            continue
        name, _, raw = line.partition(':')
        name = name.strip()
        raw = raw.strip()
        key = name
        if not raw:
            meta[name] = []
        elif raw.startswith('[') and raw.endswith(']'):
            meta[name] = [
                item.strip().strip('"').strip("'")
                for item in raw[1:-1].split(',')
                if item.strip()
            ]
        else:
            meta[name] = raw.strip('"').strip("'")
    return meta, parts[2].strip('\n')


def inline(text: str) -> str:
    def link(label: str, href: str) -> str:
        return (
            f'<a class="inline-link" href="{esc(href)}" target="_blank" '
            f'rel="{"nofollow noopener" if BETTING_HOST_RE.search(href) else "noopener"}">'
            f'{esc(label)}</a>'
        )

    parts = re.split(r'(\[[^\]]+\]\([^)]+\))', text)
    out = []
    for part in parts:
        match = re.fullmatch(r'\[([^\]]+)\]\(([^)]+)\)', part)
        if match:
            out.append(link(match.group(1), match.group(2)))
        else:
            out.append(esc(part))
    rendered = ''.join(out)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', rendered)


BETTING_HOST_RE = re.compile(r'//(?:[a-z0-9-]+\.)*(?:draftkings|kalshi|dunkelindex|fanduel|betmgm|caesars|polymarket)\.', re.I)
DYNAMIC_LINE_RE = re.compile(r'\{dynamic:([a-z0-9-]+)\}')
TABLE_SEPARATOR_RE = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$')


def table_cells(line: str) -> list[str]:
    row = line.strip()
    if row.startswith('|'):
        row = row[1:]
    if row.endswith('|'):
        row = row[:-1]
    return [cell.strip() for cell in row.split('|')]


def table_html(rows: list[str]) -> str:
    """Render a pipe table (header row, --- separator, body rows) as a scrollable table."""
    header = table_cells(rows[0])
    body = [table_cells(row) for row in rows[2:]]
    head_html = ''.join(f'<th scope="col">{inline(cell)}</th>' for cell in header)
    body_rows = []
    for cells in body:
        cells = (cells + [''] * len(header))[:len(header)]
        body_rows.append('<tr>' + ''.join(f'<td>{inline(cell)}</td>' for cell in cells) + '</tr>')
    return (
        '<div class="table-wrap"><table>'
        f'<thead><tr>{head_html}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody>'
        '</table></div>'
    )


def body_html(markdown: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    bullets: list[str] = []
    table: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        text = ' '.join(part.strip() for part in paragraph).strip()
        paragraph.clear()
        if text:
            blocks.append(('p', text))

    def flush_bullets() -> None:
        if not bullets:
            return
        blocks.append(('ul', list(bullets)))
        bullets.clear()

    def flush_table() -> None:
        if not table:
            return
        if len(table) >= 2 and TABLE_SEPARATOR_RE.match(table[1].strip()):
            blocks.append(('table', list(table)))
        else:
            # Not a real table (no separator row): keep the text as a paragraph.
            paragraph.extend(table)
            flush_paragraph()
        table.clear()

    for line in markdown.splitlines():
        if line.strip().startswith('|'):
            flush_paragraph()
            flush_bullets()
            table.append(line.strip())
            continue
        flush_table()
        if not line.strip():
            flush_paragraph()
            flush_bullets()
            continue
        dyn = DYNAMIC_LINE_RE.fullmatch(line.strip())
        if dyn:
            flush_paragraph()
            flush_bullets()
            blocks.append(('dynamic', dyn.group(1)))
            continue
        if line.startswith('## '):
            flush_paragraph()
            flush_bullets()
            blocks.append(('h2', line[3:].strip()))
            continue
        if line.startswith('- '):
            flush_paragraph()
            bullets.append(line[2:].strip())
            continue
        paragraph.append(line.strip())
    flush_table()
    flush_paragraph()
    flush_bullets()

    html_blocks = []
    first = True
    disclaimer = False
    for kind, value in blocks:
        if kind == 'h2':
            html_blocks.append(f'<h2 class="section-title">{esc(value)}</h2>')
            continue
        if kind == 'ul':
            items = ''.join(f'<li>{inline(item)}</li>' for item in value)
            html_blocks.append(f'<ul>{items}</ul>')
            continue
        if kind == 'table':
            html_blocks.append(table_html(value))
            continue
        if kind == 'dynamic':
            # Body is filled by automation/dynamic_sections.py (same workflow run).
            html_blocks.append(
                f'<div data-fcb-dynamic="{esc(value)}" data-fcb-source="data/games data/finals-schedule.json" '
                f'data-fcb-updated=""></div><!--/fcb-dynamic-->')
            continue
        if value.startswith('TV: ') and not first:
            # The closing broadcast line keeps its small grey style on every rebuild.
            html_blocks.append(f'<p class="broadcast-line" style="{BROADCAST_STYLE}">{inline(value)}</p>')
            continue
        html_blocks.append(f'<p{" class=\"lead\"" if first else ""}>{inline(value)}</p>')
        first = False
        if BETTING_RE.search(value) and DISCLAIMER not in markdown and not disclaimer:
            html_blocks.append(f'<p>{esc(DISCLAIMER)}</p>')
            disclaimer = True
    return '\n'.join(html_blocks)


def focal_for(meta: dict, existing: dict | None) -> str:
    raw = str(meta.get('focal_y') or '').strip()
    if not raw and existing and existing.get('imageFocal'):
        return str(existing['imageFocal'])
    if not raw:
        return 'center 20%'
    if re.fullmatch(r'\d{1,3}(?:\.\d+)?', raw):
        return f'center {raw}%'
    if re.fullmatch(r'\d{1,3}(?:\.\d+)?%', raw):
        return f'center {raw}'
    return raw


def caption_html(credit: str, credit_url: str, license_url: str) -> str:
    match = re.fullmatch(r'Photo: (.+), (.+), via Wikimedia Commons', credit.strip())
    if match and credit_url and license_url:
        author, license_name = match.group(1), match.group(2)
        return (
            'Photo: '
            f'<a class="inline-link" href="{esc(credit_url)}" target="_blank" rel="noopener">{esc(author)}</a>, '
            f'<a class="inline-link" href="{esc(license_url)}" target="_blank" rel="noopener">{esc(license_name)}</a>, via '
            f'<a class="inline-link" href="{esc(credit_url)}" target="_blank" rel="noopener">Wikimedia Commons</a>'
        )
    return esc(credit)


def load_articles() -> list:
    return json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))


def record_for(meta: dict, folder: Path, existing: dict | None) -> dict:
    slug = meta['slug']
    title = meta['title']
    article = dict(existing or {})
    article.update({
        'slug': slug,
        'url': f'/news/{slug}/',
        'title': meta.get('card_title') or title,
        'description': meta.get('description') or '',
        'category': meta.get('category') or 'news',
        'date': meta['date'],
        'imageAlt': meta.get('hero_alt') or title,
        'imageCredit': meta.get('photo_credit') or '',
        'teams': list(meta.get('teams') or []),
        'imageFocal': focal_for(meta, existing),
    })
    if str(meta.get('game_id') or '').strip():  # links score rows to this recap; no ESPN box-score line
        article['gameId'] = str(meta['game_id']).strip()
    if str(meta.get('preview_game_id') or '').strip():  # rail 'Next' links this preview before tip
        article['previewGameId'] = str(meta['preview_game_id']).strip()
    return article


def images_ready(article: dict, photo: bytes) -> bool:
    source = str(article.get('imageSource') or '')
    hero = str(article.get('imageHero') or '')
    og = str(article.get('imageOg') or '')
    if not source or not hero or not og:
        return False
    source_path = ROOT / source.lstrip('/')
    if not source_path.is_file() or source_path.read_bytes() != photo:
        return False
    for key in ('imageHero', 'imageOg'):
        if not (ROOT / str(article[key]).lstrip('/')).is_file():
            return False
    if article.get('imageHero2x') and not (ROOT / str(article['imageHero2x']).lstrip('/')).is_file():
        return False
    return True


def write_images(article: dict, photo_path: Path, photo: bytes) -> None:
    slug = article['slug']
    dest_dir = ROOT / 'images' / 'articles' / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    source_name = Path(str(article.get('imageSource') or '')).name or 'photo.jpg'
    source = dest_dir / source_name
    if not source.is_file() or source.read_bytes() != photo:
        shutil.copyfile(photo_path, source)
    article['image'] = '/' + source.relative_to(ROOT).as_posix()
    article['imageSource'] = article['image']
    news_heroes.ensure_article_hero(ROOT, article)
    article['image'] = article['imageHero']
    article['imageWidth'] = article['imageHeroWidth']
    article['imageHeight'] = article['imageHeroHeight']


def figure_html(article: dict, meta: dict) -> str:
    hero = article['imageHero']
    srcset = f'{hero} {article["imageHeroWidth"]}w'
    if article.get('imageHero2x'):
        srcset += f', {article["imageHero2x"]} {article["imageHero2xWidth"]}w'
    focal = article.get('imageFocal') or 'center 20%'
    caption = caption_html(
        str(meta.get('photo_credit') or article.get('imageCredit') or ''),
        str(meta.get('photo_credit_url') or ''),
        str(meta.get('license_url') or ''),
    )
    return (
        f'<figure class="lead-photo"><picture><source srcset="{esc(srcset)}" type="image/webp" '
        f'sizes="{SIZES}"></source><img src="{esc(hero)}" alt="{esc(article["imageAlt"])}" '
        f'style="object-position:{esc(focal)}" srcset="{esc(srcset)}" sizes="{SIZES}" '
        f'width="{article["imageHeroWidth"]}" height="{article["imageHeroHeight"]}" '
        f'decoding="async" fetchpriority="high"></picture>'
        f'<figcaption>{caption}</figcaption></figure>'
    )


def archive_note_html(meta: dict) -> str:
    """Preview archive note under the byline once the game is played (front matter recap_url).

    Kept in the source so a rebuild of the preview never drops it.
    """
    url = str(meta.get('recap_url') or '').strip()
    if not url:
        return ''
    return (
        '<p>This preview was published before the game. For the result, read our '
        f'<a href="{esc(url)}">game recap</a>. '
        f'<a href="{TRACKER_PATH}">2026 WNBA Finals ratings tracker</a>.</p>'
    )


def top_link_html(meta: dict) -> str:
    """Optional one-line link under the byline (front matter top_link_text + top_link_url)."""
    text, url = str(meta.get('top_link_text') or '').strip(), str(meta.get('top_link_url') or '').strip()
    if not (text and url):
        return ''
    return f'<p class="top-link"><a href="{esc(url)}">{esc(text)} &rarr;</a></p>'


def render_page(meta: dict, markdown: str, article: dict, articles: list) -> str:
    slug = article['slug']
    dest = ROOT / 'news' / slug / 'index.html'
    existed = dest.is_file()
    if existed:
        page = dest.read_text(encoding='utf-8')
    else:
        page = SHELL_PAGE.read_text(encoding='utf-8')
        page = page.replace('dream-valkyries-finals-game-1-recap', slug)
    title = meta['title']
    social = meta.get('social_title') or title
    description = article.get('description') or ''
    when = links._format_date(article['date'])
    body = body_html(markdown)
    if str(meta.get('data_table_first') or '').strip().lower() in ('true', 'yes', '1'):
        # Ryan's news exception: headline, byline, 16:9 lead photo, one-line opening, then this table.
        body = body.replace('<div class="table-wrap">', '<div class="table-wrap" data-fcb-data-table>', 1)
    linked = bool(meta.get('photo_credit_url') or meta.get('license_url'))
    sentence = links.HOW_MADE_OTHER if linked else links.HOW_MADE_OTHER_UNLINKED
    how = f'<p class="how-made">{sentence} {links.HOW_MADE_LINK}</p>'
    article_html = (
        '<article class="article">'
        f'<div class="meta-row"><span class="cat">{esc(article["category"])}</span>'
        '<span class="divider"></span><span>Full Court Buckets</span></div>'
        f'<h1>{esc(title)}</h1>'
        f'<div class="byline-row">{links.BYLINE_HTML}'
        f'<time class="article-date" datetime="{esc(article["date"])}">{esc(when)}</time></div>'
        f'{archive_note_html(meta)}{top_link_html(meta)}{figure_html(article, meta)}{body}{how}'
        '<p class="brand-sign">Full Court Buckets &middot; WNBA News. Analysis. Commentary.</p>'
        '</article>'
    )
    article_html = links.glue_headline_scores(article_html)
    page = re.sub(r'<article class="article">.*?</article>', article_html, page, count=1, flags=re.S)
    page = links.ensure_article_end(page, ROOT, article, articles)
    page = set_title(page, title, social, description, article)
    ticker = str(meta.get('ticker') or '').strip()
    if ticker or not existed:
        # A new story must not keep the shell page's score in the Now bar.
        ticker_text = ticker or 'WNBA news, analysis and commentary.'
        page = re.sub(
            r'(<div class="ticker-text">)(.*?)(</div>)',
            lambda match: match.group(1) + esc(ticker_text) + match.group(3),
            page,
            count=1,
            flags=re.S,
        )
    page = re.sub(
        r'(<nav class="breadcrumbs"[^>]*>.*)(<span>)(.*?)(</span></nav>)',
        lambda match: match.group(1) + match.group(2) + esc(title) + match.group(4),
        page,
        count=1,
        flags=re.S,
    )
    return page


def set_title(page: str, title: str, social: str, description: str, article: dict) -> str:
    slug = article['slug']
    canonical = f'https://fullcourtbuckets.com/news/{slug}/'
    og_image = links.BASE + article['imageOg']
    page = re.sub(r'<title>.*?</title>', f'<title>{esc(title)} | Full Court Buckets</title>', page, count=1)

    def meta(attr: str, value: str, prop: str) -> None:
        nonlocal page
        pattern = rf'(<meta {prop}="{attr}" content=").*?(">)'
        page = re.sub(pattern, lambda match: match.group(1) + esc(value) + match.group(2), page, count=1)

    meta('description', description, 'name')
    meta('og:title', social, 'property')
    meta('og:description', description, 'property')
    meta('og:url', canonical, 'property')
    meta('og:image', og_image, 'property')
    meta('twitter:title', social, 'name')
    meta('twitter:description', description, 'name')
    meta('twitter:image', og_image, 'name')
    meta('article:published_time', article['date'], 'property')
    page = re.sub(
        r'(<link rel="canonical" href=").*?(">)',
        lambda match: match.group(1) + esc(canonical) + match.group(2),
        page,
        count=1,
    )
    schema = {
        '@context': 'https://schema.org',
        '@type': 'NewsArticle',
        'headline': social,
        'description': description,
        'image': [og_image],
        'datePublished': article['date'],
        'dateModified': article['date'],
        'author': {
            '@type': 'Person',
            'name': 'Ryan Moalemi',
            'url': 'https://fullcourtbuckets.com/authors/ryan-moalemi/',
        },
        'publisher': {
            '@type': 'Organization',
            'name': 'Full Court Buckets',
            'logo': {'@type': 'ImageObject', 'url': 'https://fullcourtbuckets.com/logo.png'},
        },
        'mainEntityOfPage': {'@type': 'WebPage', '@id': canonical},
        'url': canonical,
    }
    replacement = '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False) + '</script>'
    page = re.sub(
        r'<script type="application/ld\+json">\{"@context": "https://schema.org", "@type": "NewsArticle".*?</script>',
        lambda _: replacement,
        page,
        count=1,
    )
    page = re.sub(
        r'("itemListElement": \[{"@type": "ListItem", "position": 1, "name": "Home".*?"position": 3, "name": ").*?(", "item": )',
        lambda match: match.group(1) + json.dumps(social, ensure_ascii=False)[1:-1] + match.group(2),
        page,
        count=1,
    )
    return page


def write_if_changed(path: Path, text: str) -> bool:
    if path.is_file() and path.read_text(encoding='utf-8') == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return True


def redirect_html(slug: str) -> str:
    return links.permanent_redirect(f'https://fullcourtbuckets.com/news/{slug}/')


def upsert_record(articles: list, article: dict) -> tuple[list, bool]:
    for index, other in enumerate(articles):
        if other.get('slug') == article['slug']:
            merged = dict(other)
            merged.update(article)
            changed = merged != other
            articles[index] = merged
            return articles, changed
    date = article.get('date') or ''
    index = len(articles)
    for cursor, other in enumerate(articles):
        if (other.get('date') or '') <= date:
            index = cursor
            break
    articles.insert(index, article)
    return articles, True


def save_articles(articles: list) -> None:
    text = json.dumps(articles, ensure_ascii=False, indent=2) + '\n'
    write_if_changed(ROOT / 'articles.json', text)


def prepend_news_list(path: Path, item_html: str, article: dict) -> None:
    text = path.read_text(encoding='utf-8')
    href = links.article_href(article)
    if href in text.split('class="news-list">', 1)[-1][:8000] and f'href="{href}"' in text:
        marker = 'class="news-list">'
        # Already listed. Replace the existing item when the card changed.
        pattern = re.compile(
            r'<li><a class="news-item" href="' + re.escape(href) + r'">.*?</li>',
            re.S,
        )
        updated = pattern.sub(lambda _: item_html, text, count=1)
        write_if_changed(path, updated)
        return
    marker = 'class="news-list">'
    if marker not in text:
        raise SystemExit(f'news list missing in {path}')
    text = text.replace(marker, marker + item_html, 1)

    def bump(match: re.Match) -> str:
        raw = match.group(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)
        changed = False

        def visit(node) -> None:
            nonlocal changed
            if isinstance(node, dict):
                main = node.get('mainEntity') if node.get('@type') == 'CollectionPage' else None
                if isinstance(main, dict) and main.get('@type') == 'ItemList':
                    elements = list(main.get('itemListElement') or [])
                    url = links.article_absolute(article)
                    if not any(isinstance(el, dict) and el.get('url') == url for el in elements):
                        elements.insert(0, {
                            '@type': 'ListItem',
                            'position': 1,
                            'url': url,
                            'name': article['title'],
                        })
                        for position, element in enumerate(elements, 1):
                            if isinstance(element, dict):
                                element['position'] = position
                        main['numberOfItems'] = len(elements)
                        main['itemListElement'] = elements
                        changed = True
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(data)
        if not changed:
            return match.group(0)
        return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'

    text = re.sub(r'<script type="application/ld\+json">(.*?)</script>', bump, text, flags=re.S)
    write_if_changed(path, text)


def update_homepage(articles: list) -> None:
    path = ROOT / 'index.html'
    text = path.read_text(encoding='utf-8')
    featured = links._story_card(articles[0]).replace(
        '<a class="article-card"',
        '<a class="article-card" id="featured-story"',
        1,
    )
    text = re.sub(
        r'<a class="article-card" id="featured-story" href=".*?">.*?</a>',
        lambda _: featured,
        text,
        count=1,
        flags=re.S,
    )
    text = links._replace_marker(text, 'fcb-stories', links._more_story_cards(articles))
    # Keep the homepage Now line in step with the newest story, as the nightly build does.
    text = links.apply_ticker(text, articles)
    write_if_changed(path, text)


def update_latest(article: dict, articles: list) -> None:
    href = links.article_href(article)
    title = esc(article['title'])
    item = f'<li><a href="{href}">{title}</a></li>'
    lead = articles[0].get('slug') == article['slug']
    for path in (ROOT / 'news').glob('*/index.html'):
        if path.parent.name == article['slug']:
            continue
        text = path.read_text(encoding='utf-8')
        match = re.search(
            r'(<section class="article-latest"><h2>Latest news</h2><ul>)(.*?)(</ul></section>)',
            text,
        )
        if not match:
            continue
        block = match.group(2)
        if href in block:
            updated = re.sub(
                r'(<li><a href="' + re.escape(href) + r'">).*?(</a></li>)',
                lambda found: found.group(1) + title + found.group(2),
                block,
                count=1,
            )
        elif lead:
            kept = re.findall(r'<li>.*?</li>', block)
            updated = item + ''.join(kept[:2])
        else:
            continue
        if updated == block:
            continue
        path.write_text(text[:match.start(2)] + updated + text[match.end(2):], encoding='utf-8')


def update_sitemap_html(article: dict) -> None:
    path = ROOT / 'sitemap' / 'index.html'
    text = path.read_text(encoding='utf-8')
    href = links.article_href(article)
    item = f'<li><a href="{href}">{esc(article["title"])}</a></li>'
    if href in text:
        text = re.sub(
            r'(<li><a href="' + re.escape(href) + r'">).*?(</a></li>)',
            lambda match: match.group(1) + esc(article['title']) + match.group(2),
            text,
            count=1,
        )
    else:
        marker = 'id="sitemap-news"><h2>News</h2><ul class="sitemap-list">'
        if marker not in text:
            raise SystemExit('html sitemap news list missing')
        text = text.replace(marker, marker + item, 1)
    write_if_changed(path, text)


def sync_feeds(articles: list) -> None:
    write_if_changed(ROOT / 'feed.xml', rss_feed.feed_document(ROOT))
    for name in ('sitemap.xml', 'pages-sitemap.xml'):
        path = ROOT / name
        if path.is_file():
            write_if_changed(path, links.sync_news_sitemap(path.read_text(encoding='utf-8'), articles))
    write_if_changed(ROOT / 'search-index.json', site_nav.search_index_document(ROOT))


def publish_folder(folder: Path, articles: list) -> list:
    meta, markdown = parse_front_matter((folder / 'article.md').read_text(encoding='utf-8'))
    slug = str(meta.get('slug') or folder.name)
    if slug != folder.name:
        raise SystemExit(f'{folder.name}: front matter slug is {slug}')
    meta['slug'] = slug
    for required in ('title', 'date', 'description', 'hero_alt', 'photo_credit'):
        if not str(meta.get(required) or '').strip():
            raise SystemExit(f'{slug}: missing {required}')
    photo_path = folder / 'photo.jpg'
    if not photo_path.is_file():
        raise SystemExit(f'{slug}: photo.jpg is missing')
    photo = photo_path.read_bytes()
    from PIL import Image  # every post photo is a true 16:9 file (test_photo_aspect)
    with Image.open(photo_path) as im:
        ratio = im.size[0] / im.size[1]
    if not 1.74 <= ratio <= 1.80:
        raise SystemExit(f'{slug}: photo.jpg is {ratio:.3f}:1; it must be 16:9. '
                         f'Run python3 automation/crop_16x9.py {photo_path} and check heads by eye.')
    existing = next((item for item in articles if item.get('slug') == slug), None)
    is_new = existing is None
    article = record_for(meta, folder, existing)
    requested_focal = str(meta.get('focal_y') or '').strip()
    focal_changed = bool(requested_focal) and (existing or {}).get('imageFocal') != article.get('imageFocal')
    if not (existing and images_ready(existing, photo) and not focal_changed):
        write_images(article, photo_path, photo)
    articles, record_changed = upsert_record(articles, article)
    # The record now in the list is the one listings and the article end should see.
    article = next(item for item in articles if item.get('slug') == slug)
    page = render_page(meta, markdown, article, articles)
    page = site_nav.apply_now_bar(site_nav.ensure_fonts(page))
    import strip_espn_stats
    page = strip_espn_stats.clean(page)  # never credit ESPN for game stats  # keep the shared Now bar + fonts on rebuild
    page_changed = write_if_changed(ROOT / 'news' / slug / 'index.html', page)
    write_if_changed(ROOT / slug / 'index.html', redirect_html(slug))
    if not (is_new or record_changed or page_changed):
        return articles
    save_articles(articles)
    if is_new or record_changed:
        item = links._news_list_item(article)
        prepend_news_list(ROOT / 'news' / 'index.html', item, article)
        prepend_news_list(ROOT / 'authors' / 'ryan-moalemi' / 'index.html', item, article)
        window = {item.get('slug') for item in articles[:1 + links.MORE_STORY_LIMIT]}
        if is_new or slug in window:
            update_homepage(articles)
        update_sitemap_html(article)
        update_latest(article, articles)
        sync_feeds(articles)
    if is_new or page_changed or record_changed:
        team_coverage.refresh(ROOT)
    return articles


def main() -> None:
    folders = sorted(path for path in CONTENT.glob('*/') if (path / 'article.md').is_file())
    if not folders:
        return
    articles = load_articles()
    for folder in folders:
        articles = publish_folder(folder, articles)
    save_articles(articles)


if __name__ == '__main__':
    main()

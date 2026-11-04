"""Build /feed.xml (RSS 2.0) from articles.json, newest first.

News items carry the full article HTML in content:encoded. The description
stays the short summary.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

SITE = 'https://fullcourtbuckets.com'
FEED_URL = SITE + '/feed.xml'
TITLE = 'Full Court Buckets'
DESCRIPTION = 'Independent WNBA news and analysis'
AUTHOR = 'Ryan Moalemi'
LIMIT = 30
PACIFIC = ZoneInfo('America/Los_Angeles')
LINK_TAG = (f'<link rel="alternate" type="application/rss+xml" '
            f'title="{TITLE}" href="{FEED_URL}">')
IMAGE_TYPES = {'.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
ARTICLE_RE = re.compile(
    r'<article\b[^>]*\bclass="[^"]*\barticle\b[^"]*"[^>]*>(.*?)</article>',
    re.S,
)
ASIDE_RE = re.compile(r'<aside class="article-end">.*?</aside>', re.S)
SCRIPT_RE = re.compile(r'<script\b[^>]*>.*?</script>', re.S | re.I)
ATTR_RE = re.compile(r'\b(href|src|srcset)=("|\')([^"\']*)\2')
BARE_AMP_RE = re.compile(r'&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)')
CONTENT_NS = 'http://purl.org/rss/1.0/modules/content/'


def _date(value: str) -> datetime:
    day = datetime.strptime(value[:10], '%Y-%m-%d')
    return day.replace(hour=12, tzinfo=PACIFIC)


def _abs(url: str) -> str:
    return url if url.startswith('http') else SITE + url


def _xml_text(value: str) -> str:
    return ''.join(char for char in value if char in '\t\n\r' or ord(char) >= 32)


def _cdata(value: str) -> str:
    return '<![CDATA[' + _xml_text(value).replace(']]>', ']]]]><![CDATA[>') + ']]>'


def _absolute_url(value: str, page: str) -> str:
    """Off-site feed readers cannot resolve a root-relative or same-page link."""
    if value.startswith(('http://', 'https://', 'mailto:', 'tel:', '//', 'data:')):
        return value
    if value.startswith('/'):
        return SITE + value
    if value.startswith('#') or value.startswith('?'):
        return page + value
    base = page if page.endswith('/') else page.rsplit('/', 1)[0] + '/'
    return base + value


def _absolute_attr(match: re.Match, page: str) -> str:
    name, quote, value = match.group(1), match.group(2), match.group(3)
    if name == 'srcset':
        chunks = []
        for chunk in value.split(','):
            bits = chunk.strip().split()
            if bits:
                bits[0] = _absolute_url(bits[0], page)
            chunks.append(' '.join(bits))
        value = ', '.join(chunks)
    else:
        value = _absolute_url(value, page)
    return f'{name}={quote}{value}{quote}'


def feed_html(html: str, page: str) -> str:
    """Make the article fragment safe to embed in content:encoded."""
    html = html.replace('</source>', '')
    html = BARE_AMP_RE.sub('&amp;', html)
    return ATTR_RE.sub(lambda match: _absolute_attr(match, page), html)


def article_markup(root: Path, article: dict) -> str:
    """Full article HTML for a news story, without the related-stories aside."""
    url = str(article.get('url') or '')
    slug = str(article.get('slug') or '').strip()
    if not slug or not url.startswith('/news/'):
        return ''
    path = root / 'news' / slug / 'index.html'
    if not path.is_file():
        return ''
    match = ARTICLE_RE.search(path.read_text(encoding='utf-8'))
    if not match:
        return ''
    body = ASIDE_RE.sub('', match.group(1))
    body = SCRIPT_RE.sub('', body)
    page = SITE + url if url.startswith('/') else url
    return feed_html(body, page).strip()


def feed_document(root: Path, articles: list[dict] | None = None) -> str:
    if articles is None:
        path = root / 'articles.json'
        articles = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []
    items = [a for a in articles if a.get('url') and a.get('title') and a.get('date')]
    items.sort(key=lambda a: (a['date'], a.get('dateModified') or ''), reverse=True)
    items = items[:LIMIT]
    built = max((_date(a['date']) for a in items), default=_date('2026-01-01'))
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
           f'xmlns:content="{CONTENT_NS}" '
           'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/">',
           '  <channel>',
           f'    <title>{TITLE}</title>',
           f'    <link>{SITE}/</link>',
           f'    <description>{escape(DESCRIPTION)}</description>',
           '    <language>en-us</language>',
           f'    <lastBuildDate>{format_datetime(built)}</lastBuildDate>',
           f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>',
           '    <image>',
           f'      <url>{SITE}/logo.png</url>',
           f'      <title>{TITLE}</title>',
           f'      <link>{SITE}/</link>',
           '    </image>']
    for a in items:
        link = _abs(a['url'])
        out += ['    <item>',
                f'      <title>{escape(a["title"])}</title>',
                f'      <link>{escape(link)}</link>',
                f'      <guid isPermaLink="true">{escape(link)}</guid>',
                f'      <pubDate>{format_datetime(_date(a["date"]))}</pubDate>',
                f'      <dc:creator>{AUTHOR}</dc:creator>']
        if a.get('category'):
            out.append(f'      <category>{escape(a["category"])}</category>')
        out.append(f'      <description>{escape(a.get("description") or a["title"])}</description>')
        markup = article_markup(root, a)
        if markup:
            out.append(f'      <content:encoded>{_cdata(markup)}</content:encoded>')
        image = a.get('imageOg') or a.get('imageHero') or a.get('image')
        if image:
            kind = IMAGE_TYPES.get(Path(image).suffix.lower(), 'image/webp')
            size = root / image.lstrip('/')
            length = size.stat().st_size if size.exists() else 0
            out.append(f'      <enclosure url="{escape(_abs(image))}" length="{length}" type="{kind}"/>')
            out.append(f'      <media:content url="{escape(_abs(image))}" medium="image" type="{kind}"/>')
        out.append('    </item>')
    out += ['  </channel>', '</rss>', '']
    return '\n'.join(out)


def ensure_link(page_html: str) -> str:
    if 'type="application/rss+xml"' in page_html or '</head>' not in page_html:
        return page_html
    if 'http-equiv="refresh"' in page_html:
        # Redirect stubs must stay byte-identical to internal_links.permanent_redirect().
        return page_html
    return page_html.replace('</head>', LINK_TAG + '</head>', 1)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    (root / 'feed.xml').write_text(feed_document(root), encoding='utf-8')

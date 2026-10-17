"""Build /feed.xml (RSS 2.0) from articles.json, newest first."""
from __future__ import annotations

import json
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


def _date(value: str) -> datetime:
    day = datetime.strptime(value[:10], '%Y-%m-%d')
    return day.replace(hour=12, tzinfo=PACIFIC)


def _abs(url: str) -> str:
    return url if url.startswith('http') else SITE + url


def feed_document(root: Path, articles: list[dict] | None = None) -> str:
    if articles is None:
        articles = json.loads((root / 'articles.json').read_text(encoding='utf-8'))
    items = [a for a in articles if a.get('url') and a.get('title') and a.get('date')]
    items.sort(key=lambda a: (a['date'], a.get('dateModified') or ''), reverse=True)
    items = items[:LIMIT]
    built = max((_date(a['date']) for a in items), default=_date('2026-01-01'))
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
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
    return page_html.replace('</head>', LINK_TAG + '</head>', 1)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    (root / 'feed.xml').write_text(feed_document(root), encoding='utf-8')

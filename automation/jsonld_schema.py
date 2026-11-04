"""JSON-LD fillers for pages the builders already publish.

NewsArticle dateModified is copied from datePublished when a page has no
separate modification date. Dataset nodes describe CSV files the page already
links, using that page's own title and description.
"""
from __future__ import annotations

import json
import re
from html import unescape

BASE = 'https://fullcourtbuckets.com'
CC0 = 'https://creativecommons.org/publicdomain/zero/1.0/'
AUTHOR = {
    '@type': 'Person',
    'name': 'Ryan Moalemi',
    'url': BASE + '/authors/ryan-moalemi/',
}

JSONLD_RE = re.compile(
    r'(<script\b[^>]*type="application/ld\+json"[^>]*>)(.*?)(</script>)',
    re.S,
)
CSV_RE = re.compile(r'href="([^"]+\.csv)"', re.I)
CANON_RE = re.compile(r'<link rel="canonical" href="([^"]+)"', re.I)
H1_RE = re.compile(r'<h1\b[^>]*>(.*?)</h1>', re.S | re.I)
DESC_RE = re.compile(r'<meta\b[^>]*name="description"[^>]*content="([^"]*)"', re.I)
DESC_RE_ALT = re.compile(r'<meta\b[^>]*content="([^"]*)"[^>]*name="description"', re.I)
TAG_RE = re.compile(r'<[^>]+>')


def dataset_node(name: str, description: str, url: str, csv_urls: list[str]) -> dict:
    """One Dataset. csv_urls are absolute contentUrl values already on the page."""
    distributions = [
        {'@type': 'DataDownload', 'encodingFormat': 'text/csv', 'contentUrl': csv}
        for csv in csv_urls
    ]
    distribution = distributions[0] if len(distributions) == 1 else distributions
    return {
        '@type': 'Dataset',
        'name': name,
        'description': description,
        'url': url,
        'creator': {
            '@type': 'Organization',
            'name': 'Full Court Buckets',
            'url': BASE + '/',
        },
        'license': CC0,
        'isAccessibleForFree': True,
        'distribution': distribution,
    }


def dataset_script(name: str, description: str, url: str, csv_urls: list[str]) -> str:
    payload = {'@context': 'https://schema.org', **dataset_node(name, description, url, csv_urls)}
    raw = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    return '<script type="application/ld+json">' + raw + '</script>'


def has_dataset(html: str) -> bool:
    return '"Dataset"' in html


def _plain(fragment: str) -> str:
    return re.sub(r'\s+', ' ', TAG_RE.sub(' ', unescape(fragment))).strip()


def _description(html: str) -> str:
    match = DESC_RE.search(html) or DESC_RE_ALT.search(html)
    return _plain(match.group(1)) if match else ''


def absolute_csv(page_url: str, href: str) -> str:
    if href.startswith('http://') or href.startswith('https://'):
        return href
    if href.startswith('/'):
        return BASE + href
    base = page_url if page_url.endswith('/') else page_url.rsplit('/', 1)[0] + '/'
    return base + href


def ensure_csv_dataset(html: str) -> str:
    """Add Dataset JSON-LD when the page links a CSV and does not already have one."""
    if has_dataset(html) or '</head>' not in html:
        return html
    hrefs = []
    for href in CSV_RE.findall(html):
        if href not in hrefs:
            hrefs.append(href)
    if not hrefs:
        return html
    canon = CANON_RE.search(html)
    title = H1_RE.search(html)
    description = _description(html)
    if not canon or not title or not description:
        return html
    page_url = unescape(canon.group(1))
    name = _plain(title.group(1))
    if not name or not page_url.startswith(BASE):
        return html
    script = dataset_script(name, description, page_url, [absolute_csv(page_url, href) for href in hrefs])
    return html.replace('</head>', script + '</head>', 1)


def _types(node) -> list[str]:
    kind = node.get('@type') if isinstance(node, dict) else None
    if isinstance(kind, str):
        return [kind]
    if isinstance(kind, list):
        return [item for item in kind if isinstance(item, str)]
    return []


def _fill_news_dates(node) -> bool:
    changed = False
    if isinstance(node, dict):
        if 'NewsArticle' in _types(node):
            published = str(node.get('datePublished') or '').strip()
            modified = str(node.get('dateModified') or '').strip()
            if published and not modified:
                node['dateModified'] = published
                changed = True
            author = node.get('author')
            name = ''
            if isinstance(author, dict):
                name = str(author.get('name') or '')
            elif isinstance(author, list) and author and isinstance(author[0], dict):
                name = str(author[0].get('name') or '')
            elif isinstance(author, str):
                name = author
            if not name:
                node['author'] = dict(AUTHOR)
                changed = True
        for value in node.values():
            if _fill_news_dates(value):
                changed = True
    elif isinstance(node, list):
        for item in node:
            if _fill_news_dates(item):
                changed = True
    return changed


def fill_newsarticle_dates(html: str) -> str:
    """Give every NewsArticle a dateModified. Use datePublished when no later edit is recorded."""

    def sub(match: re.Match) -> str:
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            return match.group(0)
        if not _fill_news_dates(data):
            return match.group(0)
        raw = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')
        return match.group(1) + raw + match.group(3)

    return JSONLD_RE.sub(sub, html)

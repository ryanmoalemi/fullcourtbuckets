#!/usr/bin/env python3
"""Crawl indexable HTML and report the internal link graph.

Nav, footer, breadcrumb, and sitemap links are counted apart from contextual
links (the links in the main copy). Orphans are indexable pages with no
inbound contextual link. Dead ends are indexable pages with no outbound
contextual link to another indexable page.

Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import csv
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

HOSTS = {'fullcourtbuckets.com', 'www.fullcourtbuckets.com'}
SKIP_DIRS = {
    '.git', '.github', 'automation', 'content', 'data', 'images',
    'portrait-handoff', 'portrait-masters', 'node_modules',
}
VOID_TAGS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
    'meta', 'param', 'source', 'track', 'wbr',
}
CHROME_TAGS = {'header', 'footer', 'nav'}
SITEMAP_NAMES = ('sitemap.xml', 'pages-sitemap.xml', 'player-sitemap.xml')


def page_url(relative: Path) -> str:
    parts = relative.parts
    if parts[-1] == 'index.html':
        parent = '/'.join(parts[:-1])
        return '/' if not parent else f'/{parent}/'
    return '/' + '/'.join(parts)


def file_for_url(root: Path, url: str) -> Path | None:
    """Map a normalized site path to a file, if one exists."""
    path = url.split('?', 1)[0].split('#', 1)[0]
    if not path.startswith('/'):
        return None
    rel = path.lstrip('/')
    if rel == '':
        candidate = root / 'index.html'
        return candidate if candidate.is_file() else None
    direct = root / rel
    if direct.is_file():
        return direct
    index = root / rel.rstrip('/') / 'index.html'
    if index.is_file():
        return index
    return None


def normalize_href(href: str, page: str) -> str | None:
    """Return a site path for an internal link, or None if it is external."""
    raw = (href or '').strip()
    if not raw or raw.startswith(('#', 'mailto:', 'tel:', 'javascript:', 'data:')):
        return None
    if raw.startswith('//'):
        parsed = urlparse('https:' + raw)
    elif '://' in raw:
        parsed = urlparse(raw)
    else:
        parsed = None
    if parsed is not None:
        host = (parsed.hostname or '').lower()
        if host and host not in HOSTS:
            return None
        path = parsed.path or '/'
    else:
        if raw.startswith('/'):
            path = raw.split('?', 1)[0].split('#', 1)[0]
        else:
            base = page if page.endswith('/') else page.rsplit('/', 1)[0] + '/'
            path = base + raw.split('?', 1)[0].split('#', 1)[0]
    path = unquote(path)
    while '//' in path:
        path = path.replace('//', '/')
    parts = []
    for part in path.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            if parts:
                parts.pop()
            continue
        parts.append(part)
    if path.endswith('/') or not parts:
        return '/' + '/'.join(parts) + ('/' if parts else '')
    # File-like paths stay without a trailing slash. Directory links keep one.
    if '.' in parts[-1]:
        return '/' + '/'.join(parts)
    return '/' + '/'.join(parts) + '/'


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.robots = ''
        self.refresh = False
        self.canonical = ''
        self._stack: list[str] = []
        self._chrome = 0
        self._skip = 0
        self._href: str | None = None
        self._href_zone = 'contextual'

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, void=tag in VOID_TAGS)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, void=True)

    def _start(self, tag, attrs, void):
        attr = {k.lower(): (v or '') for k, v in attrs}
        if tag == 'meta':
            if attr.get('name', '').lower() == 'robots':
                self.robots = attr.get('content', '')
            if attr.get('http-equiv', '').lower() == 'refresh':
                self.refresh = True
        if tag == 'link' and attr.get('rel', '').lower() == 'canonical':
            self.canonical = attr.get('href', '')
        if tag in ('script', 'style'):
            self._skip += 1
        if void:
            return
        cls = attr.get('class', '')
        classes = set(cls.split())
        chrome = (
            tag in CHROME_TAGS
            or 'breadcrumb' in classes
            or 'breadcrumbs' in classes
            or 'site-footer' in classes
            or 'utility' in classes
            or 'tagline' in classes
            or attr.get('role', '').lower() == 'navigation'
        )
        self._stack.append('chrome' if chrome else '')
        if chrome:
            self._chrome += 1
        if tag == 'a' and 'href' in attr and self._skip == 0:
            self._href = attr['href']
            self._href_zone = 'chrome' if self._chrome else 'contextual'

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self._skip:
            self._skip -= 1
        if tag == 'a' and self._href is not None:
            self.links.append((self._href, self._href_zone))
            self._href = None
        if tag in VOID_TAGS:
            return
        if self._stack:
            flag = self._stack.pop()
            if flag == 'chrome' and self._chrome:
                self._chrome -= 1

    def handle_data(self, data):
        return


def is_redirect_stub(canonical: str, page: str, text: str) -> bool:
    if not canonical:
        return False
    target = normalize_href(canonical, page)
    if not target or target == page:
        return False
    visible = re.sub(r'<script\b.*?</script>', ' ', text, flags=re.I | re.S)
    visible = re.sub(r'<style\b.*?</style>', ' ', visible, flags=re.I | re.S)
    visible = re.sub(r'<[^>]+>', ' ', visible)
    visible = re.sub(r'\s+', ' ', visible).strip()
    return len(visible) < 80


def iter_html(root: Path):
    for path in root.rglob('*.html'):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            continue
        yield path


def sitemap_targets(root: Path) -> set[str]:
    found = set()
    for name in SITEMAP_NAMES:
        path = root / name
        if not path.is_file():
            continue
        for loc in re.findall(r'<loc>\s*([^<]+?)\s*</loc>', path.read_text(encoding='utf-8')):
            url = normalize_href(loc.strip(), '/')
            if url:
                found.add(url)
    return found


def analyze(root: Path) -> dict:
    root = root.resolve()
    pages = {}
    skipped = []
    for path in sorted(iter_html(root)):
        relative = path.relative_to(root)
        url = page_url(relative)
        text = path.read_text(encoding='utf-8', errors='replace')
        parser = PageParser()
        try:
            parser.feed(text)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            skipped.append({'url': url, 'reason': f'unparsed: {exc}'})
            continue
        reason = None
        if relative.as_posix() == '404.html' or url == '/404.html':
            reason = '404'
        elif 'noindex' in parser.robots.lower():
            reason = 'noindex'
        elif parser.refresh:
            reason = 'redirect'
        elif is_redirect_stub(parser.canonical, url, text):
            reason = 'redirect'
        if reason:
            skipped.append({'url': url, 'reason': reason})
            continue
        contextual = []
        chrome = []
        broken = []
        for href, zone in parser.links:
            target = normalize_href(href, url)
            if not target or target == url:
                continue
            bucket = contextual if zone == 'contextual' else chrome
            bucket.append(target)
            if file_for_url(root, target) is None and not target.startswith('/#'):
                broken.append(target)
        pages[url] = {
            'contextual_out': contextual,
            'chrome_out': chrome,
            'broken': broken,
        }

    indexable = set(pages)
    sitemap = {url for url in sitemap_targets(root) if url in indexable}
    inbound = {url: set() for url in indexable}
    chrome_inbound = {url: set() for url in indexable}
    sitemap_only = {url: url in sitemap for url in indexable}
    contextual_edges = 0
    for source, info in pages.items():
        for target in info['contextual_out']:
            if target in indexable:
                contextual_edges += 1
                inbound[target].add(source)
        for target in info['chrome_out']:
            if target in indexable:
                chrome_inbound[target].add(source)

    rows = []
    for url in sorted(indexable):
        info = pages[url]
        out_pages = {t for t in info['contextual_out'] if t in indexable}
        rows.append({
            'url': url,
            'inbound_contextual_pages': len(inbound[url]),
            'outbound_contextual_links': len(info['contextual_out']),
            'outbound_contextual_pages': len(out_pages),
            'inbound_chrome_pages': len(chrome_inbound[url]),
            'in_sitemap': sitemap_only[url],
            'orphan': len(inbound[url]) == 0,
            'dead_end': len(out_pages) == 0,
            'broken': sorted(set(info['broken'])),
        })
    orphans = [r['url'] for r in rows if r['orphan']]
    dead = [r['url'] for r in rows if r['dead_end']]
    inbound_values = [r['inbound_contextual_pages'] for r in rows]
    average = (sum(inbound_values) / len(inbound_values)) if inbound_values else 0.0
    broken = sorted({(r['url'], b) for r in rows for b in r['broken']})
    return {
        'pages': len(rows),
        'orphans': orphans,
        'dead_ends': dead,
        'contextual_links': contextual_edges,
        'average_inbound': average,
        'rows': rows,
        'skipped': skipped,
        'broken': broken,
        'sitemap_pages': len(sitemap),
    }


def write_report(report: dict, stem: Path) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    csv_path = stem.with_suffix('.csv')
    md_path = stem.with_suffix('.md')
    with csv_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            'url', 'inbound_contextual_pages', 'outbound_contextual_links',
            'outbound_contextual_pages', 'inbound_chrome_pages', 'in_sitemap',
            'orphan', 'dead_end',
        ])
        writer.writeheader()
        for row in report['rows']:
            writer.writerow({k: row[k] for k in writer.fieldnames})
    lines = [
        '# Internal link graph',
        '',
        f'- Indexable pages: {report["pages"]}',
        f'- Orphans (no inbound contextual link, excluding nav, footer, and sitemap): {len(report["orphans"])}',
        f'- Dead ends (no outbound contextual link to another indexable page): {len(report["dead_ends"])}',
        f'- Contextual internal links: {report["contextual_links"]}',
        f'- Average inbound contextual pages per page: {report["average_inbound"]:.2f}',
        f'- Skipped (noindex, 404, or redirect): {len(report["skipped"])}',
        '',
        'Inbound counts are unique source pages. A repeated link on the same page counts once toward inbound, and each anchor counts toward contextual internal links.',
        '',
        '## Orphans',
        '',
    ]
    if report['orphans']:
        lines.extend(f'- `{url}`' for url in report['orphans'])
    else:
        lines.append('- None')
    lines.extend(['', '## Dead ends', ''])
    if report['dead_ends']:
        lines.extend(f'- `{url}`' for url in report['dead_ends'])
    else:
        lines.append('- None')
    lines.extend(['', '## Inbound contextual pages', '', '| Page | Inbound | Outbound links |', '| --- | ---: | ---: |'])
    for row in sorted(report['rows'], key=lambda r: (r['inbound_contextual_pages'], r['url'])):
        lines.append(
            f'| `{row["url"]}` | {row["inbound_contextual_pages"]} | {row["outbound_contextual_links"]} |'
        )
    lines.append('')
    md_path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Report the Full Court Buckets internal link graph.')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path, required=True, help='Report path without extension, or a .md/.csv path.')
    args = parser.parse_args()
    stem = args.out
    if stem.suffix in {'.md', '.csv'}:
        stem = stem.with_suffix('')
    report = analyze(args.root)
    write_report(report, stem)
    print(
        f'pages={report["pages"]} orphans={len(report["orphans"])} '
        f'dead_ends={len(report["dead_ends"])} contextual_links={report["contextual_links"]} '
        f'avg_inbound={report["average_inbound"]:.2f}'
    )


if __name__ == '__main__':
    main()

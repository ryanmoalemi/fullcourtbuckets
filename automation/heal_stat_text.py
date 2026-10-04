#!/usr/bin/env python3
"""Regenerate player FAQ, meta, and schema text that disagrees with the stats.

A mismatch is repaired from the same player data as the tables, then checked again.
If the repair still disagrees, the last published HTML for that page stays in place
and a GitHub issue labeled needs-fix names the page and both values. Other pages
are not blocked. Outside GitHub Actions the issue is printed, not filed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

import build_players as players

BASE = 'https://fullcourtbuckets.com'
# Tests replace this with a recorder. Production uses _default_opener.
issue_opener = None

_TITLE_RE = re.compile(r'(<title>)(.*?)(</title>)', re.I | re.S)
_OG_TITLE_RE = re.compile(r'(<meta property="og:title" content=")(.*?)(")')
_DESC_RE = re.compile(r'(<meta name="description" content=")(.*?)(")')
_OG_DESC_RE = re.compile(r'(<meta property="og:description" content=")(.*?)(")')
_FAQ_SECTION_RE = re.compile(r'<section class="section" id="faq">.*?</section>', re.S)
_FAQ_ITEM_RE = re.compile(r'<div class="faq-item"><h3>(.*?)</h3><p>(.*?)</p></div>', re.S)
_SCHEMA_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_REFRESH_RE = re.compile(r'http-equiv=["\']refresh["\']', re.I)
_SOURCES = '<details class="sources'


class HealResult:
    def __init__(self, action: str, html: str, mismatches: list[str]):
        self.action = action
        self.html = html
        self.mismatches = mismatches


def is_stat_text_failure(exc: BaseException) -> bool:
    """True for FAQ, meta, and schema disagreements. Other build errors stay fatal."""
    if not isinstance(exc, players.BuildError):
        return False
    text = str(exc)
    return any(marker in text for marker in ('FAQ', 'mentions playoffs', 'meta description', 'JSON-LD', 'WebPage name'))


def needs_fix_issue(slug: str, mismatches: list[str]) -> dict:
    url = f'{BASE}/wnba/{slug}/'
    lines = [line for line in mismatches if line] or ['The page text still disagrees with the stats data.']
    body = (
        f'Page: {url}\n\n'
        'The FAQ, meta description, or JSON-LD on this page still disagrees with the stats data '
        'after an automatic repair. Only this page was left on its last published copy. '
        'The rest of the site build was not blocked.\n\n'
        'Mismatched values:\n'
        + '\n'.join(f'- {line}' for line in lines)
        + '\n'
    )
    return {
        'slug': slug,
        'label': 'needs-fix',
        'title': f'needs-fix: /wnba/{slug}/ stats text does not match the tables',
        'body': body,
        'mismatches': lines,
    }


def file_needs_fix_issues(items: list[dict]) -> None:
    """Open or comment on one needs-fix issue per page. A filing failure does not fail the build."""
    if not items:
        return
    opener = issue_opener or _default_opener
    for item in items:
        try:
            opener(item)
        except Exception as exc:
            print(f'Could not open needs-fix issue for /wnba/{item.get("slug")}/: {exc}')


def _default_opener(item: dict) -> None:
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        _open_github_issue(item)
        return
    print(f'needs-fix (not filed outside GitHub Actions): {item["title"]}')
    for line in item.get('mismatches') or []:
        print(f'  {line}')


def _run_gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def _open_github_issue(item: dict) -> None:
    slug = item['slug']
    _run_gh([
        'gh', 'label', 'create', 'needs-fix',
        '--color', 'B60205',
        '--description', 'A page still disagrees with its stats after an automatic repair',
    ])
    listed = _run_gh([
        'gh', 'issue', 'list',
        '--label', 'needs-fix',
        '--state', 'open',
        '--limit', '100',
        '--json', 'number,title',
        '--search', f'/wnba/{slug}/ in:title',
    ])
    if listed.returncode != 0:
        raise RuntimeError(listed.stderr.strip() or 'gh issue list failed')
    needle = f'/wnba/{slug}/'
    existing = next(
        (row for row in json.loads(listed.stdout or '[]') if needle in str(row.get('title') or '')),
        None,
    )
    if existing:
        comment = _run_gh(['gh', 'issue', 'comment', str(existing['number']), '--body', item['body']])
        if comment.returncode != 0:
            raise RuntimeError(comment.stderr.strip() or 'gh issue comment failed')
        print(f'Updated needs-fix issue #{existing["number"]} for /wnba/{slug}/.')
        return
    created = _run_gh([
        'gh', 'issue', 'create',
        '--title', item['title'],
        '--body', item['body'],
        '--label', 'needs-fix',
    ])
    if created.returncode != 0:
        raise RuntimeError(created.stderr.strip() or 'gh issue create failed')
    print(f'Opened needs-fix issue for /wnba/{slug}/.')


def _unescape(value: str) -> str:
    return players.html.unescape(re.sub(r'\s+', ' ', value or '')).strip()


def _first(pattern: re.Pattern, html: str) -> str:
    match = pattern.search(html)
    return match.group(2) if match else ''


def _load_schema(html: str):
    match = _SCHEMA_RE.search(html)
    if not match:
        return None, 'missing script'
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None, 'invalid JSON'
    if not isinstance(data, dict):
        return None, 'JSON is not an object'
    return data, ''


def _graph(schema) -> list:
    if not isinstance(schema, dict):
        return []
    graph = schema.get('@graph')
    return graph if isinstance(graph, list) else []


def _webpage_name(schema) -> str:
    for node in _graph(schema):
        if isinstance(node, dict) and node.get('@type') == 'WebPage':
            return str(node.get('name') or '')
    return ''


def _schema_faq_pairs(schema) -> list[tuple[str, str]]:
    pairs = []
    for node in _graph(schema):
        if not isinstance(node, dict) or node.get('@type') != 'FAQPage':
            continue
        for item in node.get('mainEntity') or []:
            if not isinstance(item, dict):
                continue
            answer = item.get('acceptedAnswer') or {}
            text = answer.get('text') if isinstance(answer, dict) else ''
            pairs.append((str(item.get('name') or ''), str(text or '')))
    return pairs


def _visible_faq(html: str) -> list[tuple[str, str]]:
    section = _FAQ_SECTION_RE.search(html)
    if not section:
        return []
    return [(_unescape(q), _unescape(a)) for q, a in _FAQ_ITEM_RE.findall(section.group(0))]


def _pair_diff(slug: str, visible, expected) -> str:
    if len(visible) != len(expected):
        return (
            f'{slug} FAQ does not match the stats data: '
            f'page has {len(visible)} answers; stats data has {len(expected)}.'
        )
    for (_question, page_answer), (_expected_question, data_answer) in zip(visible, expected):
        if page_answer != data_answer or _question != _expected_question:
            return (
                f'{slug} FAQ answer does not match the stats data: '
                f'page says "{players._faq_quote(page_answer)}"; '
                f'stats data says "{players._faq_quote(data_answer)}".'
            )
    return f'{slug} FAQ does not match the stats data.'


def stat_text_mismatches(profile, html: str, root) -> list[str]:
    """Page text that disagrees with the player data. Empty means the page can publish."""
    slug = profile.get('slug') or 'player'
    name = players.player_name(profile) or 'This player'
    problems = []
    expected_title = players.player_title(name)
    title = _unescape(_first(_TITLE_RE, html))
    og_title = _unescape(_first(_OG_TITLE_RE, html))
    if title != expected_title:
        problems.append(
            f'{slug} title does not match the player data: '
            f'page says "{players._faq_quote(title)}"; stats data says "{players._faq_quote(expected_title)}".'
        )
    if og_title != expected_title:
        problems.append(
            f'{slug} og:title does not match the player data: '
            f'page says "{players._faq_quote(og_title)}"; stats data says "{players._faq_quote(expected_title)}".'
        )
    try:
        expected_desc = players.player_description(profile)
    except players.BuildError as exc:
        problems.append(str(exc))
        expected_desc = None
    if expected_desc is not None:
        meta = _unescape(_first(_DESC_RE, html))
        og_desc = _unescape(_first(_OG_DESC_RE, html))
        if meta != expected_desc:
            problems.append(
                f'{slug} meta description does not match the stats data: '
                f'page says "{players._faq_quote(meta)}"; stats data says "{players._faq_quote(expected_desc)}".'
            )
        if og_desc != expected_desc:
            problems.append(
                f'{slug} og:description does not match the stats data: '
                f'page says "{players._faq_quote(og_desc)}"; stats data says "{players._faq_quote(expected_desc)}".'
            )
    schema, schema_error = _load_schema(html)
    if schema_error:
        problems.append(f'{slug} JSON-LD could not be read: {schema_error}.')
        schema_pairs = None
    else:
        schema_pairs = _schema_faq_pairs(schema)
        webpage_name = _webpage_name(schema)
        if webpage_name != expected_title or webpage_name != title:
            problems.append(
                f'{slug} JSON-LD WebPage name does not match the title: '
                f'schema says "{players._faq_quote(webpage_name)}"; '
                f'title says "{players._faq_quote(title)}"; '
                f'stats data says "{players._faq_quote(expected_title)}".'
            )
    visible = _visible_faq(html)
    try:
        expected_pairs = players.faq_answer_pairs(profile, root)
    except players.BuildError as exc:
        message = str(exc)
        if message not in problems:
            problems.append(message)
        if visible:
            try:
                players.assert_faq_matches_tables(profile, visible)
            except players.BuildError as visible_exc:
                visible_message = str(visible_exc)
                if visible_message not in problems:
                    problems.append(visible_message)
        return problems
    if visible != expected_pairs:
        problems.append(_pair_diff(slug, visible, expected_pairs))
    if schema_pairs is not None and schema_pairs != expected_pairs:
        problems.append(
            f'{slug} JSON-LD FAQ does not match the stats data: '
            f'schema says "{players._faq_quote(schema_pairs[0][1] if schema_pairs else "")}"; '
            f'stats data says "{players._faq_quote(expected_pairs[0][1] if expected_pairs else "")}".'
        )
    return problems


def _fill(pattern: re.Pattern, html: str, value: str, label: str) -> str:
    updated, count = pattern.subn(lambda match: match.group(1) + players.esc(value) + match.group(3), html, count=1)
    if count != 1:
        raise players.BuildError(f'{label} was not updated.')
    return updated


def _replace_faq(html: str, block: str) -> str:
    if block:
        if _FAQ_SECTION_RE.search(html):
            return _FAQ_SECTION_RE.sub(lambda _match: block, html, count=1)
        if _SOURCES in html:
            return html.replace(_SOURCES, block + _SOURCES, 1)
        raise players.BuildError('FAQ section was not updated.')
    return _FAQ_SECTION_RE.sub('', html, count=1)


def _dump_schema(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def _replace_schema(html: str, entity, title: str) -> str:
    def replacer(match):
        data = json.loads(match.group(1))
        graph = data.get('@graph')
        if not isinstance(graph, list):
            raise players.BuildError('JSON-LD WebPage name was not updated.')
        found = False
        for node in graph:
            if isinstance(node, dict) and node.get('@type') == 'WebPage':
                node['name'] = title
                found = True
        if not found:
            raise players.BuildError('JSON-LD WebPage name was not updated.')
        kept = [node for node in graph if not (isinstance(node, dict) and node.get('@type') == 'FAQPage')]
        if entity:
            kept.append(entity)
        data['@graph'] = kept
        return '<script type="application/ld+json">' + _dump_schema(data) + '</script>'

    try:
        updated, count = _SCHEMA_RE.subn(replacer, html, count=1)
    except json.JSONDecodeError as exc:
        raise players.BuildError('JSON-LD could not be read.') from exc
    if count != 1:
        raise players.BuildError('JSON-LD WebPage name was not updated.')
    return updated


def rewrite_stat_text(profile, html: str, root) -> str:
    """Replace FAQ, meta description, and schema text from the player data."""
    name = players.player_name(profile) or 'This player'
    title = players.player_title(name)
    description = players.player_description(profile)
    block, entity = players.faq_section(profile, root)
    html = _fill(_TITLE_RE, html, title, 'title')
    html = _fill(_OG_TITLE_RE, html, title, 'og:title')
    html = _fill(_DESC_RE, html, description, 'meta description')
    html = _fill(_OG_DESC_RE, html, description, 'og:description')
    html = _replace_faq(html, block)
    html = _replace_schema(html, entity, title)
    return html


def heal_page(profile, html: str, root, previous: str | None = None) -> HealResult:
    """Regenerate mismatched text. If it still fails, keep the previous published HTML."""
    root = Path(root)
    mismatches = stat_text_mismatches(profile, html, root)
    if not mismatches:
        return HealResult('ok', html, [])
    try:
        rewritten = rewrite_stat_text(profile, html, root)
    except players.BuildError as exc:
        kept = previous if previous else html
        notes = list(mismatches)
        message = str(exc)
        if message not in notes:
            notes.append(message)
        return HealResult('kept', kept, notes)
    again = stat_text_mismatches(profile, rewritten, root)
    if not again:
        return HealResult('fixed', rewritten, mismatches)
    kept = previous if previous else html
    return HealResult('kept', kept, again)


def heal_published_players(root: Path) -> int:
    """Repair published player pages in place. Exit 0 even when a page must be held."""
    root = Path(root)
    index = json.loads((root / 'data/wnba/players-index.json').read_text(encoding='utf-8'))
    fixed = 0
    held = []
    for entry in index.get('players') or []:
        slug = entry.get('slug') or ''
        path = root / 'wnba' / slug / 'index.html'
        profile_path = root / 'data/wnba/players' / f'{slug}.json'
        if not path.is_file() or not profile_path.is_file():
            continue
        html = path.read_text(encoding='utf-8')
        if _REFRESH_RE.search(html):
            continue
        try:
            profile = json.loads(profile_path.read_text(encoding='utf-8'))
            outcome = heal_page(profile, html, root, previous=html)
        except Exception as exc:
            print(f'Kept last published /wnba/{slug}/: {exc}')
            held.append(needs_fix_issue(slug, [str(exc)]))
            continue
        if outcome.action == 'fixed' and outcome.html != html:
            path.write_text(outcome.html, encoding='utf-8')
            fixed += 1
            print(f'Regenerated FAQ, meta, and schema for /wnba/{slug}/.')
        elif outcome.action == 'kept':
            print(f'Kept last published /wnba/{slug}/ and flagged it.')
            held.append(needs_fix_issue(slug, outcome.mismatches))
    file_needs_fix_issues(held)
    summary = f'Stat text check: {fixed} pages regenerated, {len(held)} kept and flagged.'
    print(summary)
    step = os.environ.get('GITHUB_STEP_SUMMARY')
    if step:
        with open(step, 'a', encoding='utf-8') as handle:
            handle.write(summary + '\n')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Regenerate player FAQ, meta, and schema text that disagrees with the stats.')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    return heal_published_players(args.root)


if __name__ == '__main__':
    raise SystemExit(main())

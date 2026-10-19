"""Never credit ESPN for game stats (Ryan's standing rule).

Rewrites ESPN game/box score/play-by-play/scoreboard/recap links: to our own
game page when data/fcb-game-pages.json has one, otherwise the link and its
citation wrapper are dropped. ESPN story/press-release links stay.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAT_HREF = r'https?://(?:www\.)?espn\.com/wnba/(?:game|boxscore|playbyplay|scoreboard|recap)[^"]*'
STAT_RE = re.compile(STAT_HREF)
A_RE = re.compile(r'<a\b[^>]*href="(' + STAT_HREF + r')"[^>]*>(.*?)</a>', re.S)
GID_RE = re.compile(r'gameId[/=](\d+)')


def game_pages() -> dict:
    try:
        return json.loads((ROOT / 'data' / 'fcb-game-pages.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _label(text: str) -> str:
    text = re.sub(r'^\s*ESPN(?:\'s)?\s+', '', text).strip()
    return text if text and text.upper() != 'ESPN' else 'play-by-play'


def clean(html: str, pages: dict | None = None) -> str:
    pages = game_pages() if pages is None else pages

    def own(m):
        gid = GID_RE.search(m.group(1))
        url = pages.get(gid.group(1)) if gid else None
        return f'<a href="{url}">{_label(m.group(2))}</a>' if url else None

    # 1. Swap to our page where we have one.
    html = A_RE.sub(lambda m: own(m) or m.group(0), html)
    # 2. Whole source paragraphs made only of ESPN links.
    def para(m):
        body = m.group(2)
        if not STAT_RE.search(body):
            return m.group(0)
        rest = A_RE.sub('', body)
        rest = re.sub(r'<[^>]+>|[\s,.;:()&amp]|Box score|Sources?|and|G\d|Game \d( box)?', '', rest)
        return '' if not rest.strip() else m.group(0)
    html = re.sub(r'<p( class="(?:box-score|source-note|stat-caption)")?>(.*?)</p>', para, html, flags=re.S)
    html = re.sub(r'<p>(Sources?:.*?)</p>', lambda m: '' if not re.sub(r'<a\b[^>]*>.*?</a>|[\s,.;:()]|Sources?|and', '', A_RE.sub('', m.group(1))) else m.group(0), html, flags=re.S)
    # 3. Parenthetical citations: " (<a>..</a>, <a>..</a>)" -> ''.
    html = re.sub(r'\s?\((?:\s*(?:<a\b[^>]*href="' + STAT_HREF + r'"[^>]*>.*?</a>)\s*,?\s*)+\)', '', html, flags=re.S)
    # 4. Anything left: keep the words, drop the link and the ESPN credit.
    html = A_RE.sub(lambda m: m.group(2), html)
    html = html.replace('<span class="sr-only">ESPN box score. ', '<span class="sr-only">')
    html = html.replace('Source: box score. ', '')
    html = re.sub(r'<p class="box-score">(?:\s*(?:Box score|Game page|Play-by-play): ESPN\.)+\s*</p>', '', html)
    html = re.sub(r'<p class="box-score">Box scores?:[^<]*\(ESPN\)\.</p>', '', html)
    html = re.sub(r' ESPN (?:Game \d|semifinal|finals?|series) page\.', '', html)
    html = html.replace("ESPN's play-by-play", 'the play-by-play').replace('the ESPN play-by-play', 'the play-by-play')
    return html


def main() -> int:
    changed = []
    for p in ROOT.rglob('*.html'):
        if '.git' in p.parts:
            continue
        text = p.read_text(encoding='utf-8')
        if not STAT_RE.search(text):
            continue
        new = clean(text)
        if new != text:
            p.write_text(new, encoding='utf-8')
            changed.append(p.relative_to(ROOT).as_posix())
    print('\n'.join(sorted(changed)))
    print(len(changed), 'pages changed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Unique, descriptive <title> and meta description on every FCB page.

Ranges: title 45-65 characters (aim 50-60), description 130-160 (aim 140-155).
Explicit wording for hand-made pages and articles lives in data/seo-meta.json,
keyed by site path ("/news/slug/"). Generated families (player, team, owner and
play-by-play pages) get their wording from the rules below, which the builders
also call. Run after every page build, before social_meta.py and search_index.py:

    python automation/seo_meta.py            # rewrite pages
    python automation/seo_meta.py --check    # report problems, exit 1 if any
"""
from __future__ import annotations

import html as htmlmod
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES = ROOT / 'data' / 'seo-meta.json'
SITE = 'Full Court Buckets'
SUFFIX = f' | {SITE}'
TITLE_MIN, TITLE_MAX = 45, 65
DESC_MIN, DESC_MAX = 130, 160
SKIP_DIRS = {'.git', '.github', 'node_modules', 'automation', 'data'}

TITLE_RE = re.compile(r'<title>(.*?)</title>', re.S)
DESC_RE = re.compile(r'(<meta name="description" content=")([^"]*)(">)')
REDIRECT_RE = re.compile(r'http-equiv="?refresh|location\.replace', re.I)


def title_ok(t: str) -> bool:
    return TITLE_MIN <= len(t) <= TITLE_MAX


def desc_ok(d: str) -> bool:
    return DESC_MIN <= len(d) <= DESC_MAX


def fit_title(*candidates: str) -> str:
    """First candidate in range, trying each with and without the site suffix."""
    tries = []
    for c in candidates:
        c = re.sub(r'\s+', ' ', c).strip()
        tries += [c + SUFFIX, c] if not c.endswith(SITE) else [c]
    for t in tries:
        if title_ok(t):
            return t
    return min(tries, key=lambda t: abs(len(t) - 58))


PADS = (
    ' Updated after every game on Full Court Buckets.',
    ' Stats, records and recent games on Full Court Buckets.',
    ' From Full Court Buckets.',
    ' Read more on Full Court Buckets.',
)


def fit_description(text: str, pads: tuple[str, ...] = PADS) -> str:
    """Trim whole sentences when long; add one closing sentence when short."""
    d = re.sub(r'\s+', ' ', text or '').strip()
    if len(d) > DESC_MAX:
        parts = re.split(r'(?<=[.!?])\s+', d)
        while len(parts) > 1 and len(' '.join(parts)) > DESC_MAX:
            parts.pop()
        d = ' '.join(parts)
        if len(d) > DESC_MAX:
            d = d[:DESC_MAX - 1].rsplit(' ', 1)[0].rstrip(' ,;:') + '.'
    if len(d) < DESC_MIN:
        if d and d[-1] not in '.!?':
            d += '.'
        for pad in pads:
            if desc_ok(d + pad):
                return d + pad
        for a in pads:
            for b in pads:
                if a != b and desc_ok(d + a + b):
                    return d + a + b
        for pad in pads + PADS:  # very short text: keep adding closing sentences
            if len(d + pad) <= DESC_MAX and pad.strip() not in d:
                d += pad
            if len(d) >= DESC_MIN:
                break
    return d


# ---- family rules (builders call these too) ----

def player_title(name: str) -> str:
    return fit_title(f'{name} WNBA stats and profile', f'{name} WNBA stats, profile and game logs', f'{name}: WNBA stats')


def player_description(text: str) -> str:
    return fit_description(text, (' Updated after every game on Full Court Buckets.',
                                  ' Profile, team and stats on Full Court Buckets.',
                                  ' Updated by Full Court Buckets.'))


def team_title(team: str) -> str:
    return fit_title(f'{team} 2026 roster and record', f'{team} roster, record and stats', f'{team} 2026 roster and season record')


def team_description(text: str) -> str:
    return fit_description(text, (' See each player with stats and links to full profiles.',
                                  ' See each player with links to full profiles.',
                                  ' Every player has a profile.'))


def owner_title(person: str, team: str) -> str:
    return fit_title(f'{person}: {team} ownership timeline', f'{person}: {team} ownership record and timeline',
                     f'{person}, {team} owner')


def pbp_title(n: int) -> str:
    return fit_title(f'Dream vs. Valkyries play-by-play, 2026 WNBA Finals Game {n}')


def pbp_description(text: str) -> str:
    text = text.replace('search, filter by player, team, play type, quarter, runs and clutch time, cite any play, download CSV or JSON.',
                        'search by player, team, quarter, runs and clutch time, and download CSV or JSON.')
    return fit_description(text, (' Search and filter every play by player or quarter.', ' Search every play.'))


def _plain(s: str) -> str:
    return htmlmod.unescape(s).strip()


def family_meta(rel: str, title: str, desc: str):
    m = re.fullmatch(r'/wnba/finals/\d{4}/game-(\d+)/play-by-play/', rel)
    if m:
        return pbp_title(int(m.group(1))), pbp_description(desc)
    m = re.fullmatch(r'/wnba/teams/([a-z0-9-]+)/', rel)
    if m:
        team = re.sub(r'\s+(Roster|2026 roster and record|roster, record and stats|2026 roster and season record)(\s*\|.*)?$', '', title).strip()
        return team_title(team), team_description(desc)
    m = re.fullmatch(r'/wnba/owners/([a-z0-9-]+)/', rel)
    if m and ':' in title:
        person, rest = title.split(':', 1)
        team = re.sub(r'\s+(owner(ship)?\b.*)$', '', rest.split('|')[0]).strip()
        return owner_title(person.strip(), team), fit_description(desc)
    m = re.fullmatch(r'/wnba/([a-z0-9-]+)/', rel)
    if m:
        pm = re.match(r'^(.+?)(?: WNBA [Ss]tats.*|: WNBA stats.*| \| Full Court Buckets)$', title)
        if pm and 'WNBA' in title and m.group(1) not in {'teams', 'owners', 'couples', 'where-to-watch', 'viewership-attendance', 'finals'}:
            return player_title(pm.group(1).strip()), player_description(desc)
    return None


def load_overrides(root: Path = ROOT) -> dict:
    p = root / 'data' / 'seo-meta.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}


def pages(root: Path = ROOT):
    for p in sorted(root.rglob('index.html')):
        rel = p.relative_to(root)
        if rel.parts[0] in SKIP_DIRS:
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        if REDIRECT_RE.search(text):
            continue
        yield p, '/' + rel.as_posix().removesuffix('index.html'), text


def apply_text(text: str, rel: str, overrides: dict) -> str:
    tm = TITLE_RE.search(text)
    dm = DESC_RE.search(text)
    title = _plain(tm.group(1)) if tm else ''
    desc = _plain(dm.group(2)) if dm else ''
    o = overrides.get(rel)
    if o:
        new_t, new_d = o.get('title', title), o.get('description', desc)
    else:
        fam = family_meta(rel, title, desc)
        if fam:
            new_t, new_d = fam
        else:
            # Any other page (new articles too): keep in-range wording, otherwise
            # drop or add the site name and trim or extend the description.
            base = title.removesuffix(SUFFIX).strip()
            new_t = title if title_ok(title) or not base else fit_title(base)
            new_d = desc if (desc_ok(desc) or not desc) else fit_description(desc)
    if tm and new_t != title:
        text = text[:tm.start(1)] + htmlmod.escape(new_t, quote=False) + text[tm.end(1):]
    if new_d != desc:
        esc = htmlmod.escape(new_d, quote=True)
        dm = DESC_RE.search(text)
        if dm:
            text = text[:dm.start(2)] + esc + text[dm.end(2):]
        elif '</title>' in text:
            text = text.replace('</title>', f'</title>\n<meta name="description" content="{esc}">', 1)
    return text


def audit(root: Path = ROOT) -> list[str]:
    problems, seen_t, seen_d = [], {}, {}
    for p, rel, text in pages(root):
        tm, dm = TITLE_RE.search(text), DESC_RE.search(text)
        t = _plain(tm.group(1)) if tm else ''
        d = _plain(dm.group(2)) if dm else ''
        if not t:
            problems.append(f'{rel}: missing title')
        elif not title_ok(t):
            problems.append(f'{rel}: title is {len(t)} characters: {t}')
        if not d:
            problems.append(f'{rel}: missing meta description')
        elif not desc_ok(d):
            problems.append(f'{rel}: description is {len(d)} characters')
        if t and t in seen_t:
            problems.append(f'{rel}: title duplicates {seen_t[t]}')
        if d and d in seen_d:
            problems.append(f'{rel}: description duplicates {seen_d[d]}')
        seen_t.setdefault(t, rel)
        seen_d.setdefault(d, rel)
    return problems


def run(root: Path = ROOT) -> int:
    overrides = load_overrides(root)
    changed = 0
    for p, rel, text in pages(root):
        new = apply_text(text, rel, overrides)
        if new != text:
            p.write_text(new, encoding='utf-8')
            changed += 1
    return changed


def apply_file(path: Path, root: Path = ROOT) -> None:
    """For builders that write one page outside the main build (live play-by-play)."""
    rel = '/' + path.relative_to(root).as_posix().removesuffix('index.html')
    text = path.read_text(encoding='utf-8')
    new = apply_text(text, rel, load_overrides(root))
    if new != text:
        path.write_text(new, encoding='utf-8')


if __name__ == '__main__':
    if '--check' in sys.argv:
        probs = audit()
        print('\n'.join(probs) or 'All page titles and descriptions are unique and in range.')
        sys.exit(1 if probs else 0)
    print(f'seo_meta: {run()} pages updated')

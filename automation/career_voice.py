"""Sportswriter sentences for inactive players.

Every team and year comes from the season rows. Draft, college, and Olympic
appearance come from career-extras.json. A medal is included only when
career-honors.json has a source for that same Games.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import career_prose as cp
import career_summary as cs

_ORDINAL_WORDS = {
    1: 'first',
    2: 'second',
    3: 'third',
    4: 'fourth',
    5: 'fifth',
    6: 'sixth',
    7: 'seventh',
    8: 'eighth',
    9: 'ninth',
    10: 'tenth',
}
_BANNED = (
    'competed for',
    'suited up',
    'recorded',
    'during the regular season',
)
_SHE_RE = re.compile(r'\bShe\b')
_HER_RE = re.compile(r'\bHer\b')


def _ordinal_word(number: int) -> str:
    return _ORDINAL_WORDS.get(number, cs._ordinal(number))


def honors_for(root: Path | None, slug: str) -> list[dict]:
    if root is None or not slug:
        return []
    path = Path(root) / 'data' / 'wnba' / 'career-honors.json'
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    block = data.get(slug) if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return []
    found = []
    for row in block.get('olympics') or []:
        if not isinstance(row, dict):
            continue
        medal = str(row.get('medal') or '').strip().lower()
        source = str(row.get('source') or '').strip()
        nation = str(row.get('nation') or '').strip()
        city = str(row.get('city') or '').strip()
        year = row.get('year')
        if medal not in {'gold', 'silver', 'bronze'}:
            continue
        if not source or not nation or not city or not isinstance(year, int):
            continue
        found.append({
            'medal': medal,
            'source': source,
            'nation': nation,
            'city': city,
            'year': year,
        })
    return found


def _medal_event(events: list[dict], medals: list[dict]) -> dict | None:
    for medal in medals:
        for event in events:
            if event['year'] == medal['year'] and event['nation'] == medal['nation']:
                return {**medal, 'city': event['city']}
    return None


def _stat_clause(row: dict) -> str:
    pts = cs._num(row.get('pts'))
    if pts is None:
        return ''
    reb = cs._num(row.get('reb'))
    ast = cs._num(row.get('ast'))
    games = cs._games(row.get('games_played'))
    others = []
    if reb and float(reb) >= 2:
        others.append(f'{reb} rebounds')
    if ast and float(ast) >= 2:
        others.append(f'{ast} assists')
    if float(pts) == 0:
        listed = 'did not score' if not others else cp._join(others) + ' and did not score'
    else:
        listed = cp._join([f'{pts} points'] + others)
    if not games:
        return listed
    if games == '1' or listed == 'did not score':
        noun = 'game' if games == '1' else 'games'
        return f'{listed} in {games} {noun}'
    return f'{listed} over {games} games'


def _draft_sentence(name: str, draft: dict, college: str, variant: int, lead: bool) -> str:
    subject = name if lead else 'She'
    obj = name if lead else 'her'
    team = str(draft['team'])
    year = int(draft['year'])
    word = _ordinal_word(int(draft['overall']))
    if college:
        frames = (
            f'The {team} took {obj} {word} overall out of {college} in {year}.',
            f'In {year}, the {team} drafted {obj} {word} overall out of {college}.',
            f'{subject} came out of {college} and went {word} overall to the {team} in the {year} draft.',
            f'{subject} was the {word} overall pick in the {year} draft, taken by the {team} out of {college}.',
            f'Out of {college}, {subject} went {word} overall to the {team} in the {year} draft.',
            f'The {team} drafted {obj} {word} overall in the {year} draft out of {college}.',
            f'{subject} left {college} for the {year} draft, and the {team} took her {word} overall.',
            f'In the {year} draft, the {team} selected {obj} {word} overall out of {college}.',
            f'The {team} selected {obj} {word} overall in {year} after her time at {college}.',
            f'{subject} went from {college} to the {team} as the {word} overall pick in the {year} draft.',
            f'After {college}, {subject} went {word} overall in the {year} draft to the {team}.',
            f'{subject} was drafted {word} overall by the {team} in the {year} draft, out of {college}.',
            f'From {college}, the {team} drafted {obj} {word} overall in the {year} draft.',
            f'{subject} entered the {year} draft out of {college}, and the {team} took her {word} overall.',
            f'The {team} made {obj} the {word} overall pick in the {year} draft out of {college}.',
            f'{subject} joined the {team} as the {word} overall pick in the {year} draft after {college}.',
        )
    else:
        frames = (
            f'The {team} took {obj} {word} overall in the {year} draft.',
            f'In {year}, the {team} drafted {obj} {word} overall.',
            f'{subject} went {word} overall to the {team} in the {year} draft.',
            f'{subject} was the {word} overall pick in the {year} draft, taken by the {team}.',
            f'The {team} drafted {obj} {word} overall in the {year} draft.',
            f'In the {year} draft, the {team} selected {obj} {word} overall.',
            f'{subject} was drafted {word} overall by the {team} in the {year} draft.',
            f'The {team} selected {obj} {word} overall in the {year} draft.',
        )
    return frames[variant % len(frames)]


def _olympic_sentence(name: str, events: list[dict], medal: dict | None, variant: int, lead: bool) -> str:
    subject = name if lead else 'She'
    if medal:
        nation = cp._nation(medal['nation'])
        city = medal['city']
        year = medal['year']
        metal = medal['medal']
        frames = (
            f'{subject} won Olympic {metal} with {nation} at {city} in {year}.',
            f'At {city} in {year}, {subject} won Olympic {metal} with {nation}.',
            f'{subject} won {metal} with {nation} at the {year} Olympics in {city}.',
            f'In {year}, {subject} won Olympic {metal} with {nation} in {city}.',
        )
        return frames[variant % len(frames)]
    if len({item['nation'] for item in events}) == 1:
        nation = cp._nation(events[0]['nation'])
        bits = [f"{item['city']} in {item['year']}" for item in events]
        listed = cp._join(bits)
        if len(events) == 1:
            city = events[0]['city']
            year = events[0]['year']
            frames = (
                f'{subject} played for {nation} at the {year} Olympics in {city}.',
                f'{subject} represented {nation} at the Olympics in {city} in {year}.',
                f'In {year}, {subject} played for {nation} at the Olympics in {city}.',
                f'{subject} was on the {nation} Olympic team in {city} in {year}.',
                f'{subject} played Olympic basketball for {nation} in {city} in {year}.',
                f'At the {year} Olympics, {subject} played for {nation} in {city}.',
            )
        else:
            frames = (
                f'{subject} played for {nation} at the Olympics in {listed}.',
                f'{subject} represented {nation} at the Olympics in {listed}.',
                f'{subject} was on the {nation} Olympic team in {listed}.',
                f'For {nation}, {subject} played at the Olympics in {listed}.',
                f'{subject} played Olympic basketball for {nation} in {listed}.',
                f'In {listed}, {subject} played for {nation} at the Olympics.',
            )
        return frames[variant % len(frames)]
    listed = cp._stops(events)
    return f'{subject} played Olympic basketball for {listed}.'


def _same_summer(sentence: str, team: str) -> str:
    if not team or not sentence.endswith('.'):
        return sentence
    return sentence[:-1] + f', the same summer she played for the {team}.'


def _scoring_sentence(name: str, row: dict, playoffs: bool, variant: int, lead: bool, multi: bool) -> str:
    clause = _stat_clause(row)
    if not clause:
        return ''
    subject = name if lead else 'She'
    team = cs._team(row)
    year = int(row['season'])
    phrase = f'the {team} in {year}'
    quiet = 'did not score' in clause
    if playoffs:
        if quiet:
            frames = (
                f'{subject} {clause} in the playoffs with {phrase}.',
                f'With {phrase}, {subject} {clause} in the playoffs.',
                f'In the playoffs with {phrase}, {subject} {clause}.',
                f'With {phrase} in the playoffs, {subject} {clause}.',
            )
        else:
            frames = (
                f'{subject} averaged {clause} in the playoffs with {phrase}.',
                f'With {phrase}, {subject} averaged {clause} in the playoffs.',
                f'In the playoffs with {phrase}, {subject} averaged {clause}.',
                f'Her playoff averages with {phrase} were {clause}.',
            )
            if 'in 1 game' in clause:
                frames = frames[:3]
        return frames[variant % len(frames)]
    if quiet:
        frames = (
            f'{subject} {clause} with {phrase}.',
            f'With {phrase}, {subject} {clause}.',
            f'In {year}, {subject} {clause} for the {team}.',
            f'For the {team} in {year}, {subject} {clause}.',
        )
        return frames[variant % len(frames)]
    frames = [
        f'{subject} averaged {clause} with {phrase}.',
        f'With {phrase}, {subject} averaged {clause}.',
        f'In {year}, {subject} averaged {clause} for the {team}.',
        f'{subject} averaged {clause} for the {team} in {year}.',
        f'For the {team} in {year}, {subject} averaged {clause}.',
        f'{subject} put up {clause} with {phrase}.',
        f'With {phrase}, {subject} put up {clause}.',
        f'{subject} averaged {clause} while playing for {phrase}.',
    ]
    if multi:
        frames.extend((
            f'Her best WNBA season came with {phrase}, when she averaged {clause}.',
            f'{subject} was at her best with {phrase}, averaging {clause}.',
            f'{subject} peaked with {phrase}, averaging {clause}.',
            f'Her strongest WNBA season with {phrase} was {clause}.',
        ))
    else:
        frames.extend((
            f'In that {year} season, {subject} averaged {clause} for the {team}.',
            f'{subject} averaged {clause} in her season with {phrase}.',
            f'On the {team} in {year}, {subject} averaged {clause}.',
            f'{subject} turned in {clause} with {phrase}.',
        ))
    text = frames[variant % len(frames)]
    if lead and text.startswith('Her '):
        text = f"{name}'s " + text[4:]
    return text


def _team_sentence(name: str, phrases: list[str], variant: int, lead: bool) -> str:
    if not phrases:
        return ''
    subject = name if lead else 'She'
    listed = cp._join(phrases)
    frames = (
        f'{subject} played for {listed}.',
        f'{subject} later played for {listed}.',
        f'Later, {subject} played for {listed}.',
        f'{subject} also played for {listed}.',
        f'After that, {subject} played for {listed}.',
        f'In the WNBA, {subject} played for {listed}.',
        f'{subject} then played for {listed}.',
        f'From there, {subject} played for {listed}.',
        f'{subject} spent those WNBA seasons with {listed}.',
        f'{subject} played WNBA basketball for {listed}.',
        f'{subject} played her WNBA games for {listed}.',
        f'{subject} played her WNBA seasons for {listed}.',
    )
    text = frames[variant % len(frames)]
    if lead and text.startswith(('Later, ', 'After that, ', 'From there, ')):
        text = f'{name} played for {listed}.'
    return text


def _college_sentence(name: str, college: str, variant: int, lead: bool) -> str:
    subject = name if lead else 'She'
    frames = (
        f'{subject} played college basketball at {college}.',
        f'Before the WNBA, {subject} played at {college}.',
        f'{subject} came out of {college}.',
        f'In college, {subject} played at {college}.',
        f'{subject} played at {college} before the WNBA.',
        f'{subject} went from {college} to the WNBA.',
        f'{subject} played at {college} in college.',
        f'{subject} arrived from {college}.',
    )
    return frames[variant % len(frames)]


def _team_for_year(rows: list[dict], year: int) -> str:
    teams = []
    for row in rows:
        if row.get('season') == year:
            team = cs._team(row)
            if team and team not in teams:
                teams.append(team)
    if len(teams) == 1:
        return teams[0]
    return ''


def _notable_playoff(regular: dict | None, playoff: dict | None) -> bool:
    if not playoff or regular is None:
        return False
    games = playoff.get('games_played')
    if not isinstance(games, (int, float)) or isinstance(games, bool) or games < 3:
        return False
    if float(playoff['pts']) >= float(regular['pts']) + 2:
        return True
    po_ast = cs._num(playoff.get('ast'))
    reg_ast = cs._num(regular.get('ast'))
    return bool(po_ast and reg_ast and float(playoff['ast']) >= float(regular['ast']) + 1)


def _fix_case(sentence: str) -> str:
    if sentence.startswith('She ') or sentence.startswith('Her '):
        return sentence
    sentence = _SHE_RE.sub('she', sentence)
    # Keep a possessive "Her" only at the start. Mid-sentence "Her" is "her".
    sentence = _HER_RE.sub('her', sentence)
    return sentence


def _drop_redundant_list(found: list[str], phrases: list[str]) -> list[str]:
    if not phrases or len(found) < 2:
        return found
    kept = []
    dropped = False
    for sentence in found:
        others_cover = False
        if not dropped and cp._covers(sentence, phrases):
            others = ' '.join(item for item in found if item is not sentence)
            stat = any(token in sentence for token in ('averaged', 'points', 'draft', 'Olympic', 'pick', 'overall', 'college'))
            if cp._covers(others, phrases) and not stat:
                dropped = True
                continue
        kept.append(sentence)
        if others_cover:
            pass
    return kept


def sentences(profile: dict, extra: dict, root: Path | None = None) -> list[str]:
    name = cs.player_name(profile)
    if not name:
        return []
    slug = str(profile.get('slug') or '')
    position = cs.POSITIONS.get(str((profile.get('player') or {}).get('position') or '').strip(), '')
    rank = cp._rank(root, slug)
    regular = cs._rows(profile, 2)
    playoffs = cs._rows(profile, 3)
    phrases = cp.span_phrases(profile)
    best_reg = cs._best(regular)
    best_po = cs._best(playoffs)
    draft = cp._draft(extra if isinstance(extra, dict) else {})
    college = cp._college(profile, extra if isinstance(extra, dict) else {})
    events = cp._olympics(extra if isinstance(extra, dict) else {})
    medal = _medal_event(events, honors_for(root, slug))
    extra = extra if isinstance(extra, dict) else {}
    multi = len({row['season'] for row in regular}) >= 2

    if not phrases and best_reg is None and best_po is None and not draft and not events:
        return [cp._empty_sentence(name, position)]

    scoring_row = best_reg or best_po
    scoring_playoffs = best_reg is None and best_po is not None

    if medal:
        lead_kind = 'olympics'
    elif draft and int(draft['overall']) <= 3:
        lead_kind = 'draft'
    elif events:
        lead_kind = 'olympics'
    elif scoring_row is not None and not scoring_playoffs and float(scoring_row['pts']) >= 18:
        lead_kind = 'scoring'
    elif draft and int(draft['overall']) <= 10:
        lead_kind = 'draft'
    elif scoring_row is not None:
        lead_kind = 'scoring'
    elif draft:
        lead_kind = 'draft'
    else:
        lead_kind = 'teams'

    def build(kind: str, lead: bool) -> str:
        if kind == 'olympics':
            text = _olympic_sentence(name, events, medal, rank + 3, lead) if events else ''
            if text and lead and len(events) == 1:
                text = _same_summer(text, _team_for_year(regular, events[0]['year']))
            elif text and lead and medal:
                text = _same_summer(text, _team_for_year(regular, medal['year']))
            return text
        if kind == 'draft':
            return _draft_sentence(name, draft, college, rank + 7, lead) if draft else ''
        if kind == 'scoring':
            row = best_po if scoring_playoffs else scoring_row
            return _scoring_sentence(name, row, scoring_playoffs, rank, lead, multi) if row is not None else ''
        if kind == 'teams':
            return _team_sentence(name, phrases, rank + 5, lead) if phrases else ''
        if kind == 'college':
            if not college or draft:
                return ''
            return _college_sentence(name, college, rank + 11, lead)
        return ''

    order = [lead_kind]
    for kind in ('teams', 'draft', 'scoring', 'olympics', 'college'):
        if kind not in order:
            order.append(kind)
    rest = [kind for kind in order if kind != lead_kind]
    shift = rank % max(1, len(rest))
    rest = rest[shift:] + rest[:shift]
    order = [lead_kind] + rest

    found = []
    for kind in order:
        if len(found) >= 4:
            break
        text = build(kind, lead=(len(found) == 0))
        if not text:
            continue
        blob = ' '.join(found)
        if kind == 'teams' and cp._covers(blob, phrases):
            continue
        if kind == 'college' and college and college in blob:
            continue
        if kind == 'draft' and draft and str(draft['year']) in blob and _ordinal_word(int(draft['overall'])) in blob:
            continue
        if kind == 'scoring' and scoring_row is not None:
            pts = cs._num(scoring_row.get('pts'))
            if pts and pts in blob and f"the {cs._team(scoring_row)} in {scoring_row['season']}" in blob:
                continue
        found.append(text)

    if _notable_playoff(best_reg, best_po) and len(found) < 4:
        playoff_text = _scoring_sentence(name, best_po, True, rank + 4, lead=False, multi=False)
        if playoff_text and playoff_text not in found:
            found.append(playoff_text)

    found = _drop_redundant_list(found, phrases)
    blob = ' '.join(found)
    if phrases and not cp._covers(blob, phrases):
        team_text = _team_sentence(name, phrases, rank + 5, lead=not found)
        if len(found) >= 4:
            found[-1] = team_text
        else:
            found.append(team_text)

    if found and name not in found[0]:
        first = found[0]
        if first.startswith('She '):
            found[0] = name + first[3:]
        elif first.startswith('Her '):
            found[0] = f"{name}'s " + first[4:]
        else:
            found[0] = f'{name} {first[0].lower()}{first[1:]}'

    cleaned = []
    for sentence in found:
        sentence = _fix_case(re.sub(r'\s+', ' ', sentence).strip())
        if sentence and sentence not in cleaned:
            cleaned.append(sentence)
    blob = ' '.join(cleaned)
    if name not in cleaned[0]:
        raise ValueError(f'Lead sentence omitted the player name for {slug}')
    for later in cleaned[1:]:
        if name in later:
            raise ValueError(f'Later sentence repeated the full name for {slug}')
    if cs.META_RE.search(blob):
        raise ValueError(f'Meta wording in career copy for {slug}: {cs.META_RE.search(blob).group(0)}')
    folded = blob.casefold()
    for banned in _BANNED:
        if banned in folded:
            raise ValueError(f'Filler wording in {slug}: {banned}')
    for marker in cs.MARKERS:
        if marker in folded:
            raise ValueError(f'Unverified-claim marker in {slug}: {marker}')
    for sentence in cleaned:
        if not sentence.startswith(('She ', 'Her ')) and (_SHE_RE.search(sentence) or _HER_RE.search(sentence)):
            raise ValueError(f'Capital pronoun mid-sentence for {slug}: {sentence}')
    return cleaned[:4]

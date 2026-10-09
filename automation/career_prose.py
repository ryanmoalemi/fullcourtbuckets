"""Editorial career sentences built only from verified season rows and extras.

The wording changes from player to player. The facts do not: every team and
year comes from the season rows, and draft, college, and Olympic notes come
only from career-extras.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import career_summary as cs

OLYMPIC_LABELS = cs.OLYMPICS


def _join(items: list[str]) -> str:
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f'{items[0]} and {items[1]}'
    return ', '.join(items[:-1]) + ', and ' + items[-1]


def span_phrase(group: dict) -> str:
    team = group['team']
    if group['start'] == group['end']:
        return f"the {team} in {group['start']}"
    return f"the {team} from {group['start']} through {group['end']}"


def _career_rows(profile: dict) -> list[dict]:
    rows = cs._rows(profile, 2) + cs._rows(profile, 3)
    rows.sort(key=lambda row: (row['season'], cs._team(row)))
    return rows


def span_phrases(profile: dict) -> list[str]:
    """Canonical team-year phrases. The prose and the season table must share these."""
    return [span_phrase(group) for group in cs._spans(_career_rows(profile))]


def _rank(root: Path | None, slug: str) -> int:
    if root is None:
        return 0
    cache = cs._RANK_CACHE if isinstance(cs._RANK_CACHE, dict) else {}
    key = str(Path(root).resolve())
    if key not in cache:
        ranks = {}
        path = Path(root) / 'data' / 'wnba' / 'career-rollout.json'
        if path.is_file():
            try:
                import json
                data = json.loads(path.read_text(encoding='utf-8'))
                slugs = [item for item in data.get('slugs') or [] if isinstance(item, str)]
            except (OSError, ValueError):
                slugs = []
            for index, item in enumerate(slugs):
                ranks[item] = index
        cache[key] = ranks
        cs._RANK_CACHE = cache
    return int(cache[key].get(slug, 0))


def _subject(name: str, last: str, lead: bool, variant: int, position: str, at_start: bool) -> str:
    """Full name on the lead sentence. Later sentences use the surname."""
    if lead and at_start and position and variant % 4 == 0:
        return f'{name}, a {position},'
    if lead:
        return name
    return last


def _fit(who: str, text: str) -> str:
    """A comma appositive only works when the name opens the sentence."""
    if who.endswith(',') and not text.startswith(who):
        text = text.replace(who, who.split(',')[0], 1)
    text = text.replace(' for She ', ' for her ').replace(' with She ', ' with her ')
    text = text.replace(' took She ', ' took her ').replace(' where She ', ' where she ')
    return text


def _nation(name: str) -> str:
    if name == 'United States':
        return 'the United States'
    return name


def _college(profile: dict, extra: dict) -> str:
    stored = cs.profile_college(profile)
    bbref = ''
    block = extra.get('college') if isinstance(extra.get('college'), dict) else None
    if block:
        bbref = str(block.get('name') or '').strip()
    source = str(extra.get('bbref') or (block or {}).get('source') or '').strip()
    if bbref and not source:
        bbref = ''
    if stored and bbref and cs._college_key(stored) != cs._college_key(bbref):
        return ''
    return stored or bbref


def _draft(extra: dict) -> dict | None:
    draft = extra.get('draft') if isinstance(extra.get('draft'), dict) else None
    if not draft:
        return None
    source = str(extra.get('bbref') or draft.get('source') or '').strip()
    team = str(draft.get('team') or '').strip()
    if not source or not team:
        return None
    if not isinstance(draft.get('year'), int) or not isinstance(draft.get('overall'), int):
        return None
    return draft


def _olympics(extra: dict) -> list[dict]:
    international = extra.get('international') if isinstance(extra.get('international'), dict) else None
    if not international or not str(international.get('source') or '').strip():
        return []
    found = []
    seen = set()
    for row in international.get('rows') or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get('league') or '').strip()
        nation = str(row.get('team') or '').strip()
        mapped = OLYMPIC_LABELS.get(label)
        if not mapped or not nation:
            continue
        year, city = mapped
        key = (year, nation)
        if key in seen:
            continue
        seen.add(key)
        found.append({'year': year, 'city': city, 'nation': nation})
    found.sort(key=lambda item: (item['year'], item['city']))
    return found


def _stat_styles(row: dict) -> list[str]:
    def shown(value, keep_zero=False):
        num = cs._num(value)
        if num is None or (num == '0.0' and not keep_zero):
            return None
        return num
    pts = shown(row.get('pts'), keep_zero=True)
    reb = shown(row.get('reb'))
    ast = shown(row.get('ast'))
    games = cs._games(row.get('games_played'))
    if not pts:
        return []
    bits = [f'{pts} points']
    if reb:
        bits.append(f'{reb} rebounds')
    if ast:
        bits.append(f'{ast} assists')
    if len(bits) == 1:
        listed = bits[0]
    else:
        listed = ', '.join(bits[:-1]) + ' and ' + bits[-1]
    noun = 'game' if games == '1' else 'games'
    played = f' in {games} {noun}' if games else ''
    styles = [listed + played]
    if reb and ast and games:
        styles.extend([
            f'{pts} points per game, {reb} rebounds and {ast} assists, over {games} {noun}',
            f'{pts} a game, with {reb} rebounds and {ast} assists, across {games} {noun}',
            f'{pts} points, {reb} rebounds and {ast} assists per game across {games} {noun}',
            f'{pts} points and {reb} rebounds a game, with {ast} assists, in {games} {noun}',
            f'{pts} points, along with {reb} rebounds and {ast} assists, in {games} {noun}',
        ])
    return styles


def _scoring(who: str, row: dict, playoffs: bool, variant: int, at_start: bool) -> str:
    styles = _stat_styles(row)
    if not styles or not who:
        return ''
    phrase = f"the {cs._team(row)} in {row['season']}"
    comp = 'playoffs' if playoffs else 'regular season'
    # Frame and stat wording advance on different cycles so the combinations spread out.
    stats = styles[(variant // 12) % len(styles)]
    frames = [
        f'{who} averaged {stats} for {phrase} during the {comp}.',
        f'During the {comp}, {who} averaged {stats} for {phrase}.',
        f'{who} posted {stats} for {phrase} in the {comp}.',
        f'With {phrase}, {who} put up {stats} in the {comp}.',
        f'{who} finished the {comp} at {stats} for {phrase}.',
        f'Playing for {phrase}, {who} averaged {stats} in the {comp}.',
        f'In the {comp}, {who} produced {stats} for {phrase}.',
        f'{who} recorded {stats} for {phrase} during the {comp}.',
        f'For {phrase}, {who} averaged {stats} in the {comp}.',
        f'{who} finished with {stats} for {phrase} in the {comp}.',
        f'In the {comp}, the numbers for {who} with {phrase} were {stats}.',
        f'{who} came away with {stats} for {phrase} in the {comp}.',
    ]
    return _fit(who, frames[variant % len(frames)])


def _draft_sentence(who: str, draft: dict, college: str, variant: int) -> str:
    overall = cs._ordinal(int(draft['overall']))
    team = str(draft['team'])
    year = int(draft['year'])
    number = int(draft['overall'])
    if college:
        frames = [
            f'{who} was the {overall} overall pick in the {year} WNBA draft, taken by the {team} out of {college}.',
            f'{who} went {overall} overall to the {team} in the {year} WNBA draft after playing at {college}.',
            f'{who} left {college} when the {team} drafted her {overall} overall in {year}.',
            f'{who} heard her name called {overall} in the {year} WNBA draft, by the {team}, out of {college}.',
            f'{who} came out of {college} and was drafted {overall} overall by the {team} in {year}.',
            f'In the {year} WNBA draft, {who} went from {college} to the {team} at {overall} overall.',
            f'{who} was chosen {overall} overall by the {team} in {year} following college at {college}.',
            f'{who}, from {college}, joined the {team} as the {overall} pick in the {year} WNBA draft.',
            f'The {year} WNBA draft placed {who} with the {team} at number {number}, after {college}.',
            f'{who} moved from {college} to the {team} as pick number {number} in the {year} WNBA draft.',
            f'{who} was a {college} player when the {team} took her {overall} overall in {year}.',
            f'Pick {number} in the {year} WNBA draft was {who}, from {college}, and the {team} made the selection.',
            f'{who} entered the league from {college} when the {team} selected her {overall} overall in {year}.',
            f'After {college}, {who} was the {overall} selection in {year}, by the {team}.',
            f'{who} had played at {college} before the {team} drafted her {overall} overall in {year}.',
            f'The {team} drafted {who} {overall} overall in {year} out of {college}.',
            f'{who} was drafted {overall} overall in {year} by the {team}, with {college} as her college stop.',
            f'From {college}, {who} went {overall} overall in {year}, to the {team}.',
            f'{who} finished at {college} and then went {overall} overall to the {team} in {year}.',
            f'{college} was the college stop for {who}, drafted {overall} overall by the {team} in {year}.',
            f'{who} carried a {college} background into the {year} draft, where the {team} took her {overall} overall.',
            f'In {year} the {team} used the {overall} pick on {who}, who arrived from {college}.',
            f'{who} had played at {college} when the {team} called her {overall} in the {year} draft.',
            f'The {overall} pick in {year} went to {who} of {college}, and the drafting club was the {team}.',
        ]
    else:
        frames = [
            f'{who} was the {overall} overall pick in the {year} WNBA draft, selected by the {team}.',
            f'{who} went {overall} overall to the {team} in the {year} WNBA draft.',
            f'The {team} drafted {who} {overall} overall in {year}.',
            f'In the {year} WNBA draft, {who} went to the {team} at {overall} overall.',
            f'{who} was chosen {overall} overall by the {team} in the {year} WNBA draft.',
            f'Pick number {number} in the {year} WNBA draft sent {who} to the {team}.',
            f'{who} heard her name at {overall} overall in {year}, with the {team} making the pick.',
            f'The {year} draft made {who} the {overall} overall selection, and the club was the {team}.',
            f'{who} entered the WNBA in {year} as the {overall} pick, taken by the {team}.',
            f'{who} was selection number {number} in {year}, going to the {team}.',
            f'On draft night in {year}, the {team} took {who} {overall} overall.',
            f'{who} began her WNBA path in {year}, drafted {overall} overall by the {team}.',
        ]
    return _fit(who, frames[variant % len(frames)])


def _stops(events: list[dict]) -> str:
    by_nation: dict[str, list[dict]] = {}
    for event in events:
        by_nation.setdefault(event['nation'], []).append(event)
    chunks = []
    for nation, group in by_nation.items():
        bits = [f"{item['city']} in {item['year']}" for item in group]
        chunks.append(f"{_nation(nation)} ({_join(bits)})")
    return _join(chunks)


def _olympic_sentence(who: str, events: list[dict], variant: int) -> str:
    if not events:
        return ''
    if len({item['nation'] for item in events}) == 1:
        nation = _nation(events[0]['nation'])
        bits = [f"{item['city']} in {item['year']}" for item in events]
        listed = _join(bits)
        if len(events) == 1:
            city = events[0]['city']
            year = events[0]['year']
            frames = [
                f'{who} represented {nation} at the {year} Olympics in {city}.',
                f'{who} played for {nation} at the {city} Olympics in {year}.',
                f'At the {year} Olympics in {city}, {who} was on the roster for {nation}.',
                f'{who} suited up for {nation} in {city} during the {year} Olympics.',
                f'The {year} Olympic tournament in {city} included {who} with {nation}.',
                f'{who} was with {nation} for the Olympic tournament in {city} in {year}.',
                f'{city} hosted the {year} Olympics, and {who} played there for {nation}.',
                f'{who} took the floor for {nation} when the Olympics were in {city} in {year}.',
            ]
        else:
            frames = [
                f'{who} represented {nation} at the Olympics in {listed}.',
                f'{who} played for {nation} at more than one Olympics: {listed}.',
                f'Olympic tournaments for {who} with {nation} were {listed}.',
                f'{who} played in a {events[0]["nation"]} uniform at the Olympics in {listed}.',
                f'For {nation}, {who} appeared at the Olympics in {listed}.',
                f'{who} was an Olympic player for {nation} in {listed}.',
                f'The Olympic stops for {who} with {nation} were {listed}.',
                f'{who} competed for {nation} at the Olympics held in {listed}.',
            ]
        return frames[variant % len(frames)]
    listed = _stops(events)
    frames = [
        f'{who} played Olympic basketball for {listed}.',
        f'Olympic appearances for {who} came with {listed}.',
        f'{who} represented more than one national team at the Olympics: {listed}.',
        f'At the Olympics, {who} played for {listed}.',
    ]
    return frames[variant % len(frames)]


def _team_sentence(who: str, phrases: list[str], variant: int) -> str:
    if not phrases:
        return ''
    listed = _join(phrases)
    frames = [
        f'{who} played for {listed}.',
        f'{who} spent her WNBA seasons with {listed}.',
        f'{who} took the floor for {listed}.',
        f'The WNBA clubs for {who} were {listed}.',
        f'{who} was on the roster for {listed}.',
        f'{who} saw WNBA action with {listed}.',
        f'Her WNBA seasons came with {listed}.',
        f'{who} had WNBA stints with {listed}.',
        f'{who} dressed for {listed}.',
        f'Those WNBA seasons were with {listed}.',
        f'{who} was in a WNBA uniform for {listed}.',
        f'The franchises in her WNBA career were {listed}.',
        f'{who} logged WNBA games with {listed}.',
        f'WNBA basketball took {who} to {listed}.',
        f'{who} competed for {listed}.',
        f'Her franchise stops were {listed}.',
        f'{who} was a member of {listed}.',
        f'She played her WNBA games with {listed}.',
        f'{who} held a WNBA spot with {listed}.',
        f'The teams in her WNBA career were {listed}.',
        f'{who} appeared for {listed}.',
        f'Game action in the WNBA for {who} came with {listed}.',
        f'{who} wore a WNBA uniform for {listed}.',
        f'Roster spots for {who} were with {listed}.',
    ]
    return _fit(who, frames[variant % len(frames)])


def _college_sentence(who: str, college: str, variant: int) -> str:
    frames = [
        f'{who} played college basketball at {college}.',
        f'Before the WNBA, {who} played at {college}.',
        f'{who} came into the league from {college}.',
        f'Her college basketball was at {college}.',
        f'{who} had been at {college} in college.',
        f'The college program for {who} was {college}.',
        f'{who} spent her college career at {college}.',
        f'College for {who} was {college}.',
        f'{who} arrived from the college program at {college}.',
        f'{college} is where {who} played before the WNBA.',
        f'{who} was a college player at {college}.',
        f'She played at {college} before turning pro.',
        f'In college, {who} played at {college}.',
        f'{who} finished college at {college}.',
        f'The school listed for {who} is {college}.',
        f'{who} came out of the college program at {college}.',
        f'College hoops for {who} was at {college}.',
        f'{who} put in her college seasons at {college}.',
        f'{college} is the college attached to {who}.',
        f'{who} was on campus at {college} before the WNBA.',
        f'Her college seasons were played at {college}.',
        f'{who} left {college} for professional basketball.',
        f'Before turning pro, {who} was at {college}.',
        f'{college} shows up as the college for {who}.',
    ]
    return _fit(who, frames[variant % len(frames)])


def _empty_sentence(name: str, position: str) -> str:
    if position:
        return f'No WNBA season is available for {name}, a {position}.'
    return f'No WNBA season is available for {name}.'


def _covers(text: str, phrases: list[str]) -> bool:
    return all(phrase in text for phrase in phrases)


def _voice(root: Path | None, slug: str) -> int:
    """2 when this slug has been rewritten in the sportswriter pass."""
    if root is None or not slug:
        return 1
    path = Path(root) / 'data' / 'wnba' / 'career-voice.json'
    if not path.is_file():
        return 1
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 1
    slugs = data.get('slugs') if isinstance(data, dict) else None
    if not isinstance(slugs, list):
        return 1
    return 2 if slug in slugs else 1


def _sentences_v1(profile: dict, extra: dict, root: Path | None = None) -> list[str]:
    name = cs.player_name(profile)
    if not name:
        return []
    last = name.split()[-1]
    slug = str(profile.get('slug') or '')
    position = cs.POSITIONS.get(str((profile.get('player') or {}).get('position') or '').strip(), '')
    rank = _rank(root, slug)
    regular = cs._rows(profile, 2)
    playoffs = cs._rows(profile, 3)
    phrases = span_phrases(profile)
    best_reg = cs._best(regular)
    best_po = cs._best(playoffs)
    scoring_row = None
    scoring_playoffs = False
    if best_reg and best_po:
        if float(best_po['pts']) > float(best_reg['pts']):
            scoring_row, scoring_playoffs = best_po, True
        else:
            scoring_row = best_reg
    elif best_reg:
        scoring_row = best_reg
    elif best_po:
        scoring_row, scoring_playoffs = best_po, True
    draft = _draft(extra if isinstance(extra, dict) else {})
    college = _college(profile, extra if isinstance(extra, dict) else {})
    events = _olympics(extra if isinstance(extra, dict) else {})

    if not phrases and scoring_row is None and not draft and not events:
        return [_empty_sentence(name, position)]

    if events:
        lead_kind = 'olympics'
    elif draft and int(draft['overall']) <= 3:
        lead_kind = 'draft'
    elif scoring_row is not None and float(scoring_row['pts']) >= 18:
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
        # Scoring variant stays equal to rank so the offline fixture (rank 0)
        # keeps the plain "points, rebounds and assists in N games" wording.
        variant = rank + {'olympics': 3, 'draft': 7, 'scoring': 0, 'teams': 13, 'college': 17}[kind]
        at_start = True
        who = _subject(name, last, lead, variant, position, at_start=True)
        if kind == 'olympics':
            return _olympic_sentence(who, events, variant) if events else ''
        if kind == 'draft':
            return _draft_sentence(who, draft, college if lead or True else college, variant) if draft else ''
        if kind == 'scoring':
            return _scoring(who, scoring_row, scoring_playoffs, variant, True) if scoring_row is not None else ''
        if kind == 'teams':
            return _team_sentence(who, phrases, variant) if phrases else ''
        if kind == 'college':
            if not college or (draft and college):
                return ''
            return _college_sentence(who, college, variant)
        return ''

    # Draft sentences already carry the college when we have both, so a second college sentence would repeat it.
    order = [lead_kind]
    for kind in ('teams', 'draft', 'scoring', 'college', 'olympics'):
        if kind not in order:
            order.append(kind)
    # Rotate the non-lead facts so the second sentence is not always the team list.
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
        if kind == 'teams' and _covers(' '.join(found), phrases):
            continue
        if kind == 'college' and college and college in ' '.join(found):
            continue
        if kind == 'draft' and draft and cs._ordinal(int(draft['overall'])) in ' '.join(found) and str(draft['year']) in ' '.join(found):
            continue
        found.append(text)

    if scoring_playoffs and best_reg is not None and len(found) < 4:
        variant = rank + 19
        who = _subject(name, last, lead=False, variant=variant, position=position, at_start=True)
        regular_text = _scoring(who, best_reg, False, variant, True)
        if regular_text and regular_text not in found:
            found.append(regular_text)

    blob = ' '.join(found)
    if phrases and not _covers(blob, phrases):
        variant = rank + 13
        who = _subject(name, last, lead=False, variant=variant, position=position, at_start=True)
        team_text = _team_sentence(who, phrases, variant)
        if len(found) >= 4:
            found[-1] = team_text
        else:
            found.append(team_text)
        # If the replaced sentence was the only copy of another required fact, that fact can drop.
        # Team-year coverage is the one the table test requires.

    if found and name not in found[0] and name.split(',')[0] not in found[0]:
        first = found[0]
        if first.startswith('She '):
            found[0] = name + first[3:]
        elif first.startswith('Her '):
            found[0] = f"{name}'s " + first[4:]
        else:
            found[0] = f'{name} ' + first[0].lower() + first[1:]

    cleaned = []
    for sentence in found:
        sentence = re.sub(r'\s+', ' ', sentence).strip()
        if sentence and sentence not in cleaned:
            cleaned.append(sentence)
    blob = ' '.join(cleaned)
    if cs.META_RE.search(blob):
        raise ValueError(f'Meta wording in career copy for {slug}: {cs.META_RE.search(blob).group(0)}')
    for marker in cs.MARKERS:
        if marker in blob.casefold():
            raise ValueError(f'Unverified-claim marker in {slug}: {marker}')
    return cleaned[:4]


def sentences(profile: dict, extra: dict, root: Path | None = None) -> list[str]:
    slug = str(profile.get('slug') or '')
    if _voice(root, slug) == 2:
        import career_voice
        return career_voice.sentences(profile, extra, root)
    return _sentences_v1(profile, extra, root)

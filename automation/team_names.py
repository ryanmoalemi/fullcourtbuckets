"""Display names for expansion teams whose provider record omits the city.

Page addresses are city-team slugs: /wnba/teams/portland-fire/ and
/wnba/teams/toronto-tempo/. The short paths stay as redirect stubs.
"""
from __future__ import annotations

# Provider ids. Abbreviations POR and TOR are Portland and Toronto.
CORRECTIONS = {
    31: {'full_name': 'Portland Fire', 'name': 'Fire', 'city': 'Portland', 'slug': 'portland-fire'},
    30: {'full_name': 'Toronto Tempo', 'name': 'Tempo', 'city': 'Toronto', 'slug': 'toronto-tempo'},
}

# Former short addresses. GitHub Pages has no server redirects, so the builder
# keeps an HTML stub at each of these slugs.
LEGACY_SLUGS = {
    31: 'fire',
    30: 'tempo',
}


def correction_for(team: dict | None) -> dict | None:
    if not isinstance(team, dict):
        return None
    raw = team.get('id')
    if isinstance(raw, bool):
        return None
    try:
        team_id = int(raw)
    except (TypeError, ValueError):
        return None
    return CORRECTIONS.get(team_id)


def apply(team):
    """Return the team record with the public full name and city filled in."""
    spec = correction_for(team)
    if not spec:
        return team
    updated = dict(team)
    updated['full_name'] = spec['full_name']
    updated['name'] = spec['name']
    if not str(updated.get('city') or '').strip():
        updated['city'] = spec['city']
    return updated


def public_name(name: str) -> str:
    text = str(name or '').strip()
    for spec in CORRECTIONS.values():
        if text in (spec['name'], spec['full_name']):
            return spec['full_name']
    return text


def pinned_slug(team_id: int) -> str | None:
    spec = CORRECTIONS.get(team_id)
    return spec['slug'] if spec else None


def legacy_slug(team_id: int) -> str | None:
    slug = LEGACY_SLUGS.get(team_id)
    return slug or None

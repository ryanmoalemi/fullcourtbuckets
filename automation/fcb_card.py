"""Shared summary card for one team or one player.

The classes live in automation/site_nav.css, so every page that loads
/assets/site-nav.css can use them. Article photos stay 16:9. Headshots stay circles.
"""


def card_open(extra: str = '') -> str:
    classes = 'fcb-card'
    if extra:
        classes += ' ' + extra.strip()
    return f'<article class="{classes}">'


def card_close() -> str:
    return '</article>'


def stat_tile(value: str, label: str, extra: str = '') -> str:
    classes = 'stat-tile'
    if extra:
        classes += ' ' + extra.strip()
    return f'<div class="{classes}"><b>{value}</b><span>{label}</span></div>'


def stat_tiles(inner: str) -> str:
    return f'<div class="stat-tiles">{inner}</div>'


def card_credit(inner: str) -> str:
    return f'<p class="card-credit">{inner}</p>'


def section_note(inner: str) -> str:
    return f'<p class="section-note table-note">{inner}</p>'

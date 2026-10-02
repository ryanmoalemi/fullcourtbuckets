#!/usr/bin/env python3
"""Ryan Moalemi's Angel Reese card page, rendered from data/reese-cards.json.

Edit the JSON to add a card or change a price. Then run:

    python automation/build_reese_cards.py

A full player build also refreshes this page. Do not hand-edit the HTML.
"""
from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from pathlib import Path

import site_nav
import internal_links as links
from analytics import GA4_TAG

ROUTE = '/authors/ryan-moalemi/ryans-angel-reese-cards/'
RELATIVE = 'authors/ryan-moalemi/ryans-angel-reese-cards/index.html'
DATA_FILE = Path('data/reese-cards.json')
BASE = 'https://fullcourtbuckets.com'
COLLECTION_TITLE = "Ryan's Angel Reese cards"
PAGE_TITLE = f"{COLLECTION_TITLE} | Full Court Buckets"
PAGE_DESCRIPTION = (
    "Ryan Moalemi's Angel Reese cards: PSA 10 slabs, the eBay totals he paid, "
    "and current values from recent sold comps."
)
PLAYER_CALLOUT = (
    '<p class="reese-cards-link"><a class="inline-link" '
    f'href="{ROUTE}">See Ryan\'s Angel Reese cards</a></p>'
)
PHOTO_CREDIT = 'Photo: eBay seller listing of this card'
HERO = {
    'src': '/images/reese-cards/angel-reese-hero.webp',
    'width': 1364,
    'height': 1400,
    'alt': 'Angel Reese of the Chicago Sky at Target Center on September 1, 2024',
    'photographer': 'John McClellan',
    'photographer_url': 'https://www.flickr.com/photos/johnmac612/53963493287/',
    'license': 'CC BY-SA 2.0',
    'license_url': 'https://creativecommons.org/licenses/by-sa/2.0/',
    'source_name': 'Wikimedia Commons',
    'source_url': 'https://commons.wikimedia.org/wiki/File:Angel_Reese_September_2024_(2)_(cropped).jpg',
    'changes': 'Resized for the web.',
}
ADSENSE_TAG = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    '?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'
)
SHORT_MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
LONG_MONTHS = (
    'January February March April May June July August September October November December'
).split()
URL_RE = re.compile(r'https://[^\s<>"]+')
CENT = Decimal('0.01')
TENTH = Decimal('0.1')


def esc(value) -> str:
    return escape('' if value is None else str(value), quote=True)


def data_path(root: Path) -> Path:
    return root / DATA_FILE


def load_collection(root: Path) -> dict | None:
    path = data_path(root)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('cards'), list):
        raise ValueError(f'{DATA_FILE.as_posix()} needs an object with a cards list.')
    return data


def money_amount(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def is_valued(card: dict) -> bool:
    value = card.get('current_value')
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def paid_amount(card: dict) -> Decimal:
    return money_amount(card['price_paid_total'])


def value_amount(card: dict) -> Decimal | None:
    if not is_valued(card):
        return None
    return money_amount(card['current_value'])


def card_change(card: dict) -> Decimal | None:
    value = value_amount(card)
    if value is None:
        return None
    return (value - paid_amount(card)).quantize(CENT, rounding=ROUND_HALF_UP)


def card_percent(card: dict) -> Decimal | None:
    change = card_change(card)
    paid = paid_amount(card)
    if change is None or paid == 0:
        return None
    return (change / paid * Decimal(100)).quantize(TENTH, rounding=ROUND_HALF_UP)


def card_ratio(card: dict) -> Decimal | None:
    change = card_change(card)
    paid = paid_amount(card)
    if change is None or paid == 0:
        return None
    return change / paid


def direction(card: dict) -> str:
    change = card_change(card)
    if change is None:
        return 'unknown'
    if change > 0:
        return 'up'
    if change < 0:
        return 'down'
    return 'flat'


def format_money(amount: Decimal) -> str:
    sign = '-' if amount < 0 else ''
    return f'{sign}${abs(amount):,.2f}'


def format_signed_money(amount: Decimal) -> str:
    if amount > 0:
        return '+' + format_money(amount)
    return format_money(amount)


def format_percent(amount: Decimal) -> str:
    quant = amount.quantize(TENTH, rounding=ROUND_HALF_UP)
    if quant > 0:
        return f'+{quant}%'
    return f'{quant}%'


def _parts(iso: str) -> tuple[int, int, int]:
    year, month, day = (int(part) for part in str(iso)[:10].split('-'))
    return year, month, day


def short_date(iso: str) -> str:
    year, month, day = _parts(iso)
    return f'{SHORT_MONTHS[month - 1]} {day}, {year}'


def long_date(iso: str) -> str:
    year, month, day = _parts(iso)
    return f'{LONG_MONTHS[month - 1]} {day}, {year}'


def month_day(iso: str) -> str:
    _year, month, day = _parts(iso)
    return f'{LONG_MONTHS[month - 1]} {day}'


def value_as_of(root: Path) -> str:
    data = load_collection(root)
    if not data:
        return ''
    days = [str(data.get('updated') or '')[:10]]
    for card in data['cards']:
        checked = str(card.get('value_checked') or '')[:10]
        if len(checked) == 10:
            days.append(checked)
    days = [day for day in days if len(day) == 10]
    return max(days) if days else ''


def card_title(card: dict) -> str:
    return f"{card['year']} {card['set']} #{card['card_number']} {card['parallel']}"


def photo_src(photo) -> str:
    if isinstance(photo, str):
        return photo
    if isinstance(photo, dict):
        return str(photo.get('src') or photo.get('file') or '')
    return ''


def photo_attr(photo, key: str, default: int) -> int:
    if isinstance(photo, dict) and isinstance(photo.get(key), int):
        return photo[key]
    return default


def summarize(data: dict) -> dict:
    cards = data['cards']
    valued = [card for card in cards if is_valued(card)]
    unknown = [card for card in cards if not is_valued(card)]
    paid = sum((paid_amount(card) for card in valued), Decimal('0.00'))
    current = sum((value_amount(card) for card in valued), Decimal('0.00'))
    change = (current - paid).quantize(CENT, rounding=ROUND_HALF_UP)
    percent = None
    if paid != 0 and valued:
        percent = (change / paid * Decimal(100)).quantize(TENTH, rounding=ROUND_HALF_UP)
    return {
        'count': len(cards),
        'valued_count': len(valued),
        'unknown': unknown,
        'paid': paid,
        'current': current,
        'change': change,
        'percent': percent,
        'up': sum(1 for card in valued if direction(card) == 'up'),
        'down': sum(1 for card in valued if direction(card) == 'down'),
        'flat': sum(1 for card in valued if direction(card) == 'flat'),
    }


def _external(url: str, label: str) -> str:
    return f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(label)}</a>'


def linkify(text: str) -> str:
    parts = []
    last = 0
    for match in URL_RE.finditer(text or ''):
        parts.append(esc(text[last:match.start()]))
        url = match.group(0).rstrip('.,)')
        trailing = match.group(0)[len(url):]
        parts.append(_external(url, url))
        parts.append(esc(trailing))
        last = match.end()
    parts.append(esc((text or '')[last:]))
    return ''.join(parts)


def _badge(card: dict) -> str:
    if not is_valued(card):
        return '<span class="badge unknown">Value unknown*</span>'
    way = direction(card)
    change = card_change(card)
    percent = card_percent(card)
    label = f'{format_signed_money(change)} ({format_percent(percent)})'
    return f'<span class="badge {way}">{esc(label)}</span>'


def _money_row(label: str, amount) -> str:
    return f'<div><dt>{esc(label)}</dt><dd>{esc(format_money(money_amount(amount)))}</dd></div>'


def _detail(card: dict, as_of: str) -> str:
    photos = card.get('photo') or {}
    front = photos.get('front')
    back = photos.get('back')
    images = []
    for side, photo in (('front', front), ('back', back)):
        src = photo_src(photo)
        if not src:
            continue
        images.append(
            f'<figure><img src="{esc(src)}" alt="{esc(card_title(card) + ", " + side + " of the slab")}" '
            f'width="{photo_attr(photo, "width", 750)}" height="{photo_attr(photo, "height", 1000)}">'
            f'<figcaption>{esc(side.title())}</figcaption></figure>'
        )
    photo_class = 'detail-photos solo' if len(images) == 1 else 'detail-photos'
    serial = card.get('serial_number')
    serial_html = f'<p>Serial {esc(serial)}</p>' if serial else ''
    cert = str(card.get('psa_cert') or '')
    comps = card.get('value_comps') or []
    if comps:
        rows = []
        for comp in comps:
            rows.append(
                '<li><span>' + esc(long_date(comp['date'])) + '</span> '
                '<b>' + esc(format_money(money_amount(comp['price']))) + '</b> '
                '<span>' + esc(comp.get('venue') or '') + '</span> '
                + _external(comp['url'], 'Sale record') + '</li>'
            )
        comp_html = '<ul class="comps">' + ''.join(rows) + '</ul>'
    else:
        comp_html = '<p>No verified sold comps.</p>'
    value = value_amount(card)
    if value is None:
        value_html = '<p class="value-line"><b>Value unknown*</b></p>'
    else:
        value_html = (
            f'<p class="value-line"><b>{esc(format_money(value))}</b> {_badge(card)}</p>'
        )
    source = str(card.get('current_value_source') or '').strip()
    source_html = f'<p>{linkify(source)}</p>' if source else ''
    return f'''<article class="detail" id="{esc(card["id"])}" data-detail="{esc(card["id"])}" hidden>
<div class="{photo_class}">{''.join(images)}</div>
<p class="photo-credit">{esc(PHOTO_CREDIT)}</p>
<div class="detail-copy">
<p class="eyebrow">{esc(card.get("grade") or "PSA 10")}</p>
<h2>{esc(card_title(card))}</h2>
{serial_html}
<p>Bought {esc(long_date(card["purchase_date"]))} on {esc(card.get("source") or "eBay")}.</p>
<h3>Cost</h3>
<dl class="cost">
{_money_row("Item", card["item_price"])}
{_money_row("Shipping", card["shipping"])}
{_money_row("Tax", card["tax"])}
{_money_row("Total paid", card["price_paid_total"])}
</dl>
<h3>Value on {esc(short_date(as_of))}</h3>
{value_html}
{source_html}
<p>PSA cert <a href="https://www.psacard.com/cert/{esc(cert)}" target="_blank" rel="noopener">{esc(cert)}</a></p>
<h3>Sold comps</h3>
{comp_html}
<h3>Value notes</h3>
<div class="notes">{linkify(card.get("value_notes") or "")}</div>
<p class="context">Player page: <a href="/wnba/angel-reese/">Angel Reese</a>.</p>
</div>
</article>'''


def _tile(card: dict, index: int) -> str:
    front = photo_src((card.get('photo') or {}).get('front'))
    photo = (card.get('photo') or {}).get('front')
    serial = card.get('serial_number')
    serial_bit = f' / {serial}' if serial else ''
    value = value_amount(card)
    value_html = 'Value unknown*' if value is None else format_money(value)
    ratio = card_ratio(card)
    gain = '' if ratio is None else format(ratio, 'f')
    current = '' if value is None else format(value, 'f')
    return f'''<button type="button" class="tile" data-id="{esc(card["id"])}" data-index="{index}" data-date="{esc(card["purchase_date"])}" data-gain="{esc(gain)}" data-value="{esc(current)}" data-paid="{esc(format(paid_amount(card), "f"))}" data-year="{esc(card["year"])}" data-direction="{direction(card)}">
<img src="{esc(front)}" alt="{esc(card_title(card) + " slab")}" width="{photo_attr(photo, "width", 750)}" height="{photo_attr(photo, "height", 1000)}">
<span class="photo-credit">{esc(PHOTO_CREDIT)}</span>
<span class="tile-copy">
<strong>{esc(card["year"])} {esc(card["set"])}</strong>
<span class="meta">#{esc(card["card_number"])} {esc(card["parallel"])}{esc(serial_bit)}</span>
<span class="grade">{esc(card.get("grade") or "PSA 10")}</span>
<span class="bought">Bought {esc(long_date(card["purchase_date"]))}</span>
<span class="figures"><span>Paid <b>{esc(format_money(paid_amount(card)))}</b></span><span>Value <b>{esc(value_html)}</b></span></span>
{_badge(card)}
</span>
</button>'''


def _unknown_note(summary: dict) -> str:
    unknown = summary['unknown']
    if not unknown:
        return ''
    bits = [
        f'{card_title(card)} ({format_money(paid_amount(card))})'
        for card in unknown
    ]
    noun = 'card' if len(unknown) == 1 else 'cards'
    verb = 'is' if len(unknown) == 1 else 'are'
    return (
        f'* {len(unknown)} {noun} with no verified sale {verb} left out of paid, value, and change: '
        + '; '.join(bits) + '.'
    )


def _chart(cards: list[dict]) -> str:
    valued = [card for card in cards if is_valued(card)]
    if not valued:
        return ''
    peak = max(max(paid_amount(card), value_amount(card)) for card in valued)
    if peak <= 0:
        return ''
    rows = []
    for card in sorted(valued, key=lambda item: item['purchase_date']):
        paid = paid_amount(card)
        current = value_amount(card)
        paid_width = (paid / peak * Decimal(100)).quantize(TENTH, rounding=ROUND_HALF_UP)
        value_width = (current / peak * Decimal(100)).quantize(TENTH, rounding=ROUND_HALF_UP)
        rows.append(
            '<li>'
            f'<p>{esc(month_day(card["purchase_date"]))} · {esc(card["parallel"])} #{esc(card["card_number"])}</p>'
            '<div class="bar-row"><span>Paid</span>'
            f'<span class="track"><span class="fill paid" style="width:{paid_width}%"></span></span>'
            f'<b>{esc(format_money(paid))}</b></div>'
            '<div class="bar-row"><span>Value</span>'
            f'<span class="track"><span class="fill value" style="width:{value_width}%"></span></span>'
            f'<b>{esc(format_money(current))}</b></div>'
            '</li>'
        )
    return (
        '<section class="panel" id="paid-vs-value">'
        '<h2>Paid vs value</h2>'
        '<p class="lede">Each pair is the eBay total next to the current value, in purchase order. '
        'This is one snapshot, not a price history.</p>'
        f'<ul class="chart">{"".join(rows)}</ul></section>'
    )


def _move_label(card: dict, low: bool) -> str:
    change = card_change(card) or Decimal('0')
    if low:
        if change < 0:
            return 'Largest dollar drop'
        if change > 0:
            return 'Smallest dollar gain'
        return 'Flat'
    if change > 0:
        return 'Largest dollar gain'
    if change < 0:
        return 'Smallest dollar drop'
    return 'Flat'


def _movers(cards: list[dict], summary: dict) -> str:
    valued = [card for card in cards if card_change(card) is not None]
    if not valued:
        return ''
    low_dollars = min(valued, key=card_change)
    high_dollars = max(valued, key=card_change)
    low_percent = min(valued, key=card_percent)
    percent_label = 'Largest percent drop' if (card_percent(low_percent) or 0) < 0 else 'Smallest percent gain'
    parts = ['<p class="lede">No valued card is up.</p>'] if summary['up'] == 0 else []
    parts.append(
        '<ul class="movers">'
        f'<li><span>{esc(_move_label(low_dollars, True))}</span><b>{esc(card_title(low_dollars))}</b>{_badge(low_dollars)}</li>'
        f'<li><span>{esc(percent_label)}</span><b>{esc(card_title(low_percent))}</b>{_badge(low_percent)}</li>'
        f'<li><span>{esc(_move_label(high_dollars, False))}</span><b>{esc(card_title(high_dollars))}</b>{_badge(high_dollars)}</li>'
        '</ul>'
    )
    return '<section class="panel" id="movers"><h2>How the cards have moved</h2>' + ''.join(parts) + '</section>'


def _timeline(cards: list[dict]) -> str:
    if not cards:
        return ''
    dates = sorted({card['purchase_date'] for card in cards})
    first, last = dates[0], dates[-1]
    if first[:4] == last[:4]:
        heading = f'{month_day(first)} to {month_day(last)}, {first[:4]}'
    else:
        heading = f'{long_date(first)} to {long_date(last)}'
    groups = []
    for day in dates:
        bought = [card for card in cards if card['purchase_date'] == day]
        items = ''.join(
            f'<li><button type="button" data-id="{esc(card["id"])}">{esc(card_title(card))}</button></li>'
            for card in bought
        )
        groups.append(f'<li class="when"><time datetime="{esc(day)}">{esc(month_day(day))}</time><ul>{items}</ul></li>')
    return (
        '<section class="panel" id="timeline"><h2>Purchase timeline</h2>'
        f'<p class="lede">{esc(heading)}</p><ol class="timeline">{"".join(groups)}</ol></section>'
    )


def _faq(as_of: str) -> tuple[str, list[dict]]:
    checked = short_date(as_of) if as_of else 'the date in the data file'
    items = [
        (
            'Where do the values come from?',
            'Each value is the median of the sold comps listed on that card. '
            f'Those comps were checked on {checked}.',
        ),
        (
            'What is included in the price paid?',
            'The eBay order total: the item, shipping, and tax. The detail view lists those three amounts.',
        ),
        (
            'Why does a card say value unknown?',
            'No verified sale was found for that exact card number, parallel, and grade. '
            'That card is left out of the paid, value, and change totals.',
        ),
    ]
    html_items = ''.join(
        f'<details><summary>{esc(question)}</summary><p>{esc(answer)}</p></details>'
        for question, answer in items
    )
    entities = [
        {
            '@type': 'Question',
            'name': question,
            'acceptedAnswer': {'@type': 'Answer', 'text': answer},
        }
        for question, answer in items
    ]
    section = '<section class="panel" id="faq"><h2>Questions</h2>' + html_items + '</section>'
    return section, entities


def _schema(data: dict, summary: dict, as_of: str, faq_entities: list[dict]) -> str:
    canonical = BASE + ROUTE
    crumbs = {
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': 'Ryan Moalemi', 'item': links.AUTHOR_URL},
            {'@type': 'ListItem', 'position': 3, 'name': COLLECTION_TITLE, 'item': canonical},
        ],
    }
    listing = []
    for index, card in enumerate(data['cards'], start=1):
        listing.append({
            '@type': 'ListItem',
            'position': index,
            'name': card_title(card),
            'url': canonical + '#' + card['id'],
        })
    graph = [
        {
            '@type': 'WebPage',
            'name': PAGE_TITLE,
            'description': PAGE_DESCRIPTION,
            'url': canonical,
            'dateModified': as_of,
            'author': {'@type': 'Person', 'name': 'Ryan Moalemi', 'url': links.AUTHOR_URL},
            'about': {'@type': 'Person', 'name': 'Angel Reese', 'url': BASE + '/wnba/angel-reese/'},
        },
        crumbs,
        {'@type': 'ItemList', 'numberOfItems': summary['count'], 'itemListElement': listing},
        {'@type': 'FAQPage', 'mainEntity': faq_entities},
    ]
    payload = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False)
    return payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def _hero() -> str:
    credit = (
        f'Photo: {_external(HERO["photographer_url"], HERO["photographer"])}, '
        f'{_external(HERO["license_url"], HERO["license"])}, via '
        f'{_external(HERO["source_url"], HERO["source_name"])}. {esc(HERO["changes"])}'
    )
    return f'''<section class="hero" aria-labelledby="collection-title">
<img class="hero-photo" src="{esc(HERO["src"])}" alt="{esc(HERO["alt"])}" width="{HERO["width"]}" height="{HERO["height"]}">
<div class="hero-shade" aria-hidden="true"></div>
<div class="hero-copy">
<p class="hero-kicker">Personal collection</p>
<h1 id="collection-title"><span class="owner-word">{esc("Ryan's")}</span><span>Angel Reese</span><span class="cards-word">cards</span></h1>
<p class="hero-line">Ryan's collection of Angel Reese cards</p>
<p class="hero-credit">{credit}</p>
</div>
</section>'''


def _stats(summary: dict, as_of: str) -> str:
    mark = '*' if summary['unknown'] else ''
    percent = '' if summary['percent'] is None else format_percent(summary['percent'])
    change_class = 'flat'
    if summary['change'] < 0:
        change_class = 'down'
    elif summary['change'] > 0:
        change_class = 'up'
    note = esc(_unknown_note(summary))
    note_html = f'<p class="asterisk-note">{note}</p>' if note else ''
    return f'''<section class="panel stats-panel" id="summary">
<p class="as-of">Values as of {esc(short_date(as_of))}</p>
<ul class="stats">
<li><b>{summary["count"]}</b><span>Cards</span></li>
<li><b>{esc(format_money(summary["paid"]))}</b><span>Paid{mark}</span></li>
<li><b>{esc(format_money(summary["current"]))}</b><span>Value{mark}</span></li>
<li class="{change_class}"><b>{esc(format_signed_money(summary["change"]))}</b><em>{esc(percent)}</em><span>Change{mark}</span></li>
<li><b>{summary["up"]}</b><span>Up</span></li>
<li><b>{summary["down"]}</b><span>Down</span></li>
</ul>
{note_html}
</section>'''


def _controls(cards: list[dict]) -> str:
    years = sorted({str(card.get('year') or '') for card in cards if card.get('year')})
    options = ''.join(f'<option value="{esc(year)}">{esc(year)}</option>' for year in years)
    return f'''<div class="controls">
<div class="control-row" role="group" aria-label="Sort cards">
<button type="button" data-sort="date" aria-pressed="true">Date bought</button>
<button type="button" data-sort="gain" aria-pressed="false">Gain %</button>
<button type="button" data-sort="value" aria-pressed="false">Value</button>
<button type="button" data-sort="paid" aria-pressed="false">Price paid</button>
</div>
<div class="control-row filters">
<label>Show <select id="card-filter"><option value="all">All cards</option><option value="up">Up</option><option value="down">Down</option><option value="unknown">Value unknown</option></select></label>
<label>Year <select id="year-filter"><option value="all">All years</option>{options}</select></label>
<div role="group" aria-label="Layout">
<button type="button" data-layout="grid" aria-pressed="true">Grid</button>
<button type="button" data-layout="list" aria-pressed="false">List</button>
</div>
</div>
</div>'''


def render_body(data: dict) -> str:
    cards = list(data['cards'])
    as_of = str(data.get('updated') or '')[:10]
    checked = [str(card.get('value_checked') or '')[:10] for card in cards]
    checked.append(as_of)
    checked = [day for day in checked if len(day) == 10]
    as_of = max(checked) if checked else as_of
    summary = summarize(data)
    ordered = sorted(enumerate(cards), key=lambda pair: (pair[1]['purchase_date'], -pair[0]), reverse=True)
    tiles = ''.join(_tile(card, index) for index, card in ordered)
    details = ''.join(_detail(card, as_of) for card in cards)
    faq_html, faq_entities = _faq(as_of)
    star = '*' if summary['unknown'] else ''
    intro = f'''<section class="intro">
<p>I think Angel Reese is a transcendent talent, the kind of player who rises above her generation.</p>
<p>I really like the positive impact she is having on women's sports. So many young girls look up to her.</p>
<p>I got into sports writing after watching her play.</p>
<p><a href="/wnba/angel-reese/">Angel Reese</a> has a player page on this site.</p>
</section>'''
    method = (
        '<section class="panel method" id="method"><h2>How the numbers work</h2>'
        '<p>Values are medians of recent sold prices from the sources listed on each card. '
        'Ryan paid the eBay order total, including shipping and tax. '
        'The values get updated over time. '
        f'A card with no verified sale is marked Value unknown{star} and left out of the paid, value, and change totals.</p>'
        '</section>'
    )
    return f'''<div class="crumb-bar"><div class="shell"><nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a><span aria-hidden="true">/</span><a href="/authors/ryan-moalemi/">Ryan Moalemi</a><span aria-hidden="true">/</span><span>{esc(COLLECTION_TITLE)}</span></nav></div></div>
{_hero()}
<main class="shell" id="content">
{intro}
{_stats(summary, as_of)}
{_chart(cards)}
{_movers(cards, summary)}
<section class="panel" id="collection">
<h2>The cards</h2>
{_controls(cards)}
<div class="cards" id="card-grid">{tiles}</div>
<p id="card-empty" class="lede" hidden>No cards match.</p>
</section>
{_timeline(cards)}
{method}
{faq_html}
</main>
<dialog id="card-dialog" aria-label="Card detail">
<div class="dialog-bar"><button type="button" class="dialog-close" data-close>Close</button></div>
{details}
</dialog>
<script type="application/json" id="reese-meta">{json.dumps({"count": summary["count"], "as_of": as_of})}</script>
''' + '<script>' + PAGE_JS + '</script>' + _schema_comment(data, summary, as_of, faq_entities)


def _schema_comment(data, summary, as_of, faq_entities) -> str:
    """Schema is emitted in the head. This keeps the body free of a second copy."""
    return ''


PAGE_JS = r'''
(function () {
  var grid = document.getElementById('card-grid');
  var dialog = document.getElementById('card-dialog');
  var empty = document.getElementById('card-empty');
  if (!grid || !dialog) return;
  var tiles = Array.prototype.slice.call(grid.querySelectorAll('.tile'));
  var sortKey = 'date';
  var show = 'all';
  var year = 'all';

  function numberOrNull(tile, name) {
    var raw = tile.getAttribute(name);
    if (raw === null || raw === '') return null;
    var value = Number(raw);
    return isFinite(value) ? value : null;
  }

  function compare(a, b) {
    if (sortKey === 'date') {
      var byDate = b.getAttribute('data-date').localeCompare(a.getAttribute('data-date'));
      if (byDate) return byDate;
      return Number(a.getAttribute('data-index')) - Number(b.getAttribute('data-index'));
    }
    var left = numberOrNull(a, 'data-' + sortKey);
    var right = numberOrNull(b, 'data-' + sortKey);
    if (left === null && right === null) return 0;
    if (left === null) return 1;
    if (right === null) return -1;
    if (left === right) return Number(a.getAttribute('data-index')) - Number(b.getAttribute('data-index'));
    return right - left;
  }

  function apply() {
    var visible = 0;
    tiles.slice().sort(compare).forEach(function (tile) {
      var direction = tile.getAttribute('data-direction');
      var tileYear = tile.getAttribute('data-year');
      var hide = (show !== 'all' && direction !== show) || (year !== 'all' && tileYear !== year);
      tile.hidden = hide;
      if (!hide) visible += 1;
      grid.appendChild(tile);
    });
    if (empty) empty.hidden = visible !== 0;
  }

  function openCard(id) {
    var found = false;
    Array.prototype.forEach.call(dialog.querySelectorAll('[data-detail]'), function (panel) {
      var match = panel.getAttribute('data-detail') === id;
      panel.hidden = !match;
      if (match) found = true;
    });
    if (!found) return;
    if (!dialog.open) dialog.showModal();
    if (history.replaceState) history.replaceState(null, '', '#' + id);
  }

  grid.addEventListener('click', function (event) {
    var tile = event.target.closest('.tile');
    if (!tile) return;
    openCard(tile.getAttribute('data-id'));
  });
  document.getElementById('timeline').addEventListener('click', function (event) {
    var button = event.target.closest('button[data-id]');
    if (!button) return;
    openCard(button.getAttribute('data-id'));
  });
  dialog.querySelector('[data-close]').addEventListener('click', function () {
    dialog.close();
  });
  dialog.addEventListener('click', function (event) {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', function () {
    if (location.hash && history.replaceState) history.replaceState(null, '', location.pathname + location.search);
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-sort]'), function (button) {
    button.addEventListener('click', function () {
      sortKey = button.getAttribute('data-sort');
      Array.prototype.forEach.call(document.querySelectorAll('[data-sort]'), function (other) {
        other.setAttribute('aria-pressed', other === button ? 'true' : 'false');
      });
      apply();
    });
  });
  document.getElementById('card-filter').addEventListener('change', function (event) {
    show = event.target.value;
    apply();
  });
  document.getElementById('year-filter').addEventListener('change', function (event) {
    year = event.target.value;
    apply();
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-layout]'), function (button) {
    button.addEventListener('click', function () {
      var layout = button.getAttribute('data-layout');
      grid.classList.toggle('is-list', layout === 'list');
      Array.prototype.forEach.call(document.querySelectorAll('[data-layout]'), function (other) {
        other.setAttribute('aria-pressed', other === button ? 'true' : 'false');
      });
    });
  });
  var hash = location.hash.replace(/^#/, '');
  if (hash) openCard(hash);
  apply();
})();
'''


CSS = r'''
:root{color-scheme:dark}
body{margin:0;background:#07060a;color:#f6f1e8;font:16px/1.55 Inter,system-ui,sans-serif}
img{max-width:100%;height:auto}
button,select{font:inherit;color:inherit}
a{color:#f0c36a}
.shell{width:min(1120px,94vw);margin:0 auto}
header{border-bottom:1px solid #2b2930;background:#07060a}
header .shell{display:flex;align-items:center;gap:24px;min-height:84px}
header img{width:220px;height:auto}
.crumb-bar{background:#07060a;border-bottom:1px solid #241f2a}
.breadcrumbs{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:12px 0;color:#b7b0a6;font-size:13px;font-weight:700}
.breadcrumbs a{color:#f6f1e8;text-decoration:underline}
.hero{position:relative;min-height:92vh;min-height:100svh;display:flex;align-items:flex-end;overflow:hidden;background:#07060a}
.hero-photo{position:absolute;top:0;left:50%;height:100%;width:auto;max-width:none;transform:translateX(-50%);object-fit:cover}
.hero-shade{position:absolute;inset:auto 0 0 0;height:62%;background:linear-gradient(180deg,rgba(7,6,10,0) 0%,rgba(7,6,10,.55) 28%,rgba(7,6,10,.94) 70%,#07060a 100%)}
.hero-copy{position:relative;z-index:1;width:min(1120px,94vw);margin:0 auto;padding:0 0 28px}
.hero-kicker{margin:0 0 8px;color:#f0c36a;font:700 13px/1 Inter,sans-serif;letter-spacing:.16em;text-transform:uppercase}
.hero h1{margin:0;font:900 clamp(4.4rem,13vw,8.8rem)/.82 "Barlow Condensed",Impact,sans-serif;letter-spacing:-.02em;text-transform:uppercase}
.hero h1 span{display:block}
.hero h1 .owner-word{font-size:.38em;letter-spacing:.04em;color:#f6f1e8}
.hero h1 .cards-word{color:#f0c36a}
.hero-line{margin:14px 0 0;font:700 clamp(1.15rem,2.4vw,1.7rem)/1.25 "Barlow Condensed",sans-serif;letter-spacing:.02em}
.hero-credit{margin:14px 0 0;max-width:40rem;color:#d9d1c6;font-size:13px}
.hero-credit a{color:#fff}
main{padding:8px 0 72px}
.intro{max-width:40rem;margin:28px 0}
.intro p{margin:0 0 14px;font-size:18px;line-height:1.55}
.panel{margin:28px 0}
.panel h2,.detail-copy h2{margin:0 0 10px;font:800 clamp(1.8rem,3vw,2.4rem)/1 "Barlow Condensed",sans-serif;letter-spacing:.01em;text-transform:uppercase}
.lede,.as-of{color:#c9c1b6}
.as-of{margin:0 0 12px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;font-size:13px;color:#f0c36a}
.stats{list-style:none;display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin:0;padding:0}
.stats li{background:#14121a;border:1px solid #3a3328;padding:14px 12px;min-height:92px}
.stats b{display:block;font:800 clamp(1.4rem,2.4vw,2rem)/1 "Barlow Condensed",sans-serif}
.stats em{display:block;margin-top:4px;font-style:normal;font-weight:800}
.stats span{display:block;margin-top:8px;color:#b7b0a6;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
.stats .down b,.stats .down em,.badge.down{color:#ff8d9a}
.stats .up b,.stats .up em,.badge.up{color:#7dffa8}
.badge{display:inline-flex;align-items:center;margin-top:10px;padding:4px 8px;border-radius:999px;font-size:13px;font-weight:800;background:#241820}
.badge.up{background:#10281c}
.badge.down{background:#2c1218}
.badge.unknown,.badge.flat{background:#2a2830;color:#ddd6cc}
.asterisk-note{color:#c9c1b6;font-size:14px}
.chart,.movers,.timeline{list-style:none;margin:0;padding:0}
.chart>li,.movers>li{padding:12px 0;border-top:1px solid #2b2733}
.bar-row{display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:10px;align-items:center;margin-top:6px}
.track{display:block;height:10px;background:#241f2a;border-radius:999px;overflow:hidden}
.fill{display:block;height:100%}
.fill.paid{background:#8d7344}
.fill.value{background:#f0c36a}
.controls{display:flex;flex-direction:column;gap:10px;margin:14px 0 18px}
.control-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.control-row button,.control-row select{background:#14121a;border:1px solid #3a3328;padding:10px 12px;min-height:44px}
.control-row button[aria-pressed="true"]{background:#f0c36a;color:#1a1408;border-color:#f0c36a}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}
.tile{display:flex;flex-direction:column;text-align:left;background:#120f16;border:1px solid #3a3328;padding:0;cursor:pointer;width:100%}
.tile img{width:100%;background:#09080c;aspect-ratio:3/4;object-fit:contain}
.tile .photo-credit,.detail .photo-credit{margin:0;padding:8px 12px 0;color:#9c958b;font-size:12px}
.tile-copy{display:flex;flex-direction:column;gap:4px;padding:8px 12px 14px}
.tile-copy strong{font:800 22px/1.05 "Barlow Condensed",sans-serif;letter-spacing:.01em;text-transform:uppercase}
.tile-copy .meta,.tile-copy .bought{color:#d5cdc2}
.grade{color:#f0c36a;font-weight:800;letter-spacing:.04em;text-transform:uppercase;font-size:13px}
.figures{display:flex;justify-content:space-between;gap:8px;margin-top:6px}
.cards.is-list{grid-template-columns:1fr}
.cards.is-list .tile{display:grid;grid-template-columns:148px minmax(0,1fr);grid-template-areas:"photo credit" "photo copy"}
.cards.is-list .tile img{grid-area:photo;height:100%;aspect-ratio:auto;max-height:220px}
.cards.is-list .photo-credit{grid-area:credit}
.cards.is-list .tile-copy{grid-area:copy}
.timeline{border-left:2px solid #f0c36a;margin-left:8px;padding-left:18px}
.when{margin:0 0 18px}
.when time{font:800 20px/1 "Barlow Condensed",sans-serif;letter-spacing:.04em;text-transform:uppercase}
.when ul{list-style:none;margin:8px 0 0;padding:0}
.when button{background:none;border:0;padding:6px 0;color:#f6f1e8;text-decoration:underline;cursor:pointer;text-align:left}
.method{background:#14121a;border:1px solid #3a3328;padding:18px}
.method p{margin:0}
details{border-top:1px solid #2b2733;padding:10px 0}
summary{cursor:pointer;font-weight:800;min-height:44px;display:flex;align-items:center}
dialog{width:min(980px,calc(100vw - 24px));max-height:calc(100vh - 24px);margin:auto;padding:0 0 24px;background:#100e14;color:#f6f1e8;border:1px solid #3a3328}
dialog::backdrop{background:rgba(0,0,0,.78)}
.dialog-bar{position:sticky;top:0;display:flex;justify-content:flex-end;padding:10px;background:#100e14;z-index:2}
.dialog-close{background:#f0c36a;color:#1a1408;border:0;min-height:44px;padding:0 16px;font-weight:800;cursor:pointer}
.detail{padding:0 18px 8px}
.detail-photos{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.detail-photos.solo{grid-template-columns:minmax(0,460px)}
.detail figure{margin:0}
.detail figcaption{color:#9c958b;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.detail img{width:100%;background:#09080c}
.detail .eyebrow{margin:0;color:#f0c36a;font-weight:800;letter-spacing:.08em;text-transform:uppercase;font-size:13px}
.cost{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 12px}
.cost div{background:#191621;padding:8px}
.cost dt{color:#b7b0a6;font-size:12px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}
.cost dd{margin:4px 0 0;font:800 22px/1 "Barlow Condensed",sans-serif}
.comps{list-style:none;margin:0;padding:0}
.comps li{display:flex;flex-wrap:wrap;gap:8px 14px;padding:8px 0;border-top:1px solid #2b2733}
.notes{color:#e7e0d6}
.value-line{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.value-line b{font:800 32px/1 "Barlow Condensed",sans-serif}
@media(max-width:800px){
.hero{min-height:78vh}
.hero h1{font-size:clamp(3.4rem,18vw,5.2rem)}
.stats{grid-template-columns:repeat(2,minmax(0,1fr))}
.cost{grid-template-columns:1fr 1fr}
.detail-photos,.detail-photos.solo{grid-template-columns:1fr}
.cards.is-list .tile{grid-template-columns:96px minmax(0,1fr)}
dialog{width:100vw;max-width:100vw;height:100vh;max-height:100vh;margin:0;border:0}
}
'''


def _head(schema: str) -> str:
    canonical = BASE + ROUTE
    hero_url = BASE + HERO['src']
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
{GA4_TAG}
{ADSENSE_TAG}
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(PAGE_TITLE)}</title>
<meta name="description" content="{esc(PAGE_DESCRIPTION)}">
<meta name="author" content="Ryan Moalemi">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="/favicon.svg">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(PAGE_TITLE)}">
<meta property="og:description" content="{esc(PAGE_DESCRIPTION)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{hero_url}">
<meta property="og:site_name" content="Full Court Buckets">
<meta name="theme-color" content="#07060a">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800;900&amp;family=Inter:wght@400;600;700;800&amp;display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/site-nav.css">
<script type="application/ld+json">{schema}</script>
<style>
{CSS}
</style>
</head>
<body>
<header><div class="shell"><a href="/"><img src="/logo.png" alt="Full Court Buckets"></a><nav aria-label="Main"><a href="/">Home</a></nav></div></header>
'''


def render_page(root: Path, menu: list | None = None) -> str | None:
    data = load_collection(root)
    if data is None:
        return None
    if '\u2014' in json.dumps(data):
        raise ValueError('Card data contains an em dash. Keep the copy plain.')
    summary = summarize(data)
    as_of = value_as_of(root)
    _faq_html, faq_entities = _faq(as_of)
    body = render_body(data)
    html_text = _head(_schema(data, summary, as_of, faq_entities)) + body + '\n</body>\n</html>\n'
    if '\u2014' in html_text:
        raise ValueError('Generated card page contains an em dash.')
    if menu is None:
        menu = site_nav.build_menu(root)
    return site_nav.install(html_text, ROUTE, menu)


def author_teaser(root: Path) -> str:
    data = load_collection(root)
    if not data:
        return ''
    count = len(data['cards'])
    noun = 'card' if count == 1 else 'cards'
    image = '/images/reese-cards/reese-2024-rookie-royalty-kaboom-5-front.webp'
    alt = '2024 Panini Rookie Royalty WNBA Kaboom Angel Reese PSA 10 slab'
    return (
        f'<a class="collection-teaser" href="{ROUTE}">'
        f'<img src="{image}" alt="{esc(alt)}" width="657" height="1000">'
        f'<span><b>{esc(COLLECTION_TITLE)}</b>'
        f'<p>{count} Angel Reese {noun} in Ryan\'s collection, with what he paid and the latest values.</p>'
        '</span></a>'
    )


def ensure_player_callout(root: Path) -> None:
    page = root / 'wnba' / 'angel-reese' / 'index.html'
    if not page.is_file() or not data_path(root).is_file():
        return
    text = page.read_text(encoding='utf-8')
    if ROUTE in text:
        return
    needle = '<div class="overview-strip">'
    if needle not in text:
        raise ValueError('Angel Reese page has no overview strip to attach the card link.')
    page.write_text(text.replace(needle, PLAYER_CALLOUT + needle, 1), encoding='utf-8')


def ensure_sitemaps(root: Path) -> None:
    day = value_as_of(root)
    if not day:
        return
    loc = BASE + ROUTE
    block = f'  <url>\n    <loc>{loc}</loc>\n    <lastmod>{day}</lastmod>\n  </url>'
    for name in ('sitemap.xml', 'pages-sitemap.xml'):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        pattern = re.compile(
            rf'  <url>\n    <loc>{re.escape(loc)}</loc>\n    <lastmod>[^<]*</lastmod>\n  </url>'
        )
        if pattern.search(text):
            text = pattern.sub(block, text, count=1)
        else:
            anchor = f'<loc>{BASE}/authors/ryan-moalemi/</loc>'
            index = text.find(anchor)
            if index == -1:
                raise ValueError(f'{name} is missing the author URL, so the card page was not added.')
            end = text.find('</url>', index)
            insert_at = end + len('</url>')
            text = text[:insert_at] + '\n' + block + text[insert_at:]
        path.write_text(text, encoding='utf-8')


def publish(root: Path) -> str:
    menu = site_nav.build_menu(root)
    html_text = render_page(root, menu)
    if not html_text:
        raise SystemExit(f'Missing {DATA_FILE.as_posix()}')
    path = root / RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding='utf-8')
    author_path = root / links.AUTHOR_PAGE
    if author_path.is_file():
        articles = links.load_articles(root)
        author_html = site_nav.install(links.render_author_page(articles, root), links.AUTHOR_PATH, menu)
        author_path.write_text(author_html, encoding='utf-8')
    ensure_player_callout(root)
    ensure_sitemaps(root)
    return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description='Render the Angel Reese card collection page.')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(publish(args.root))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Ryan Moalemi's Angel Reese card page, rendered from data/reese-cards.json.

Live auctions he is bidding on live in data/reese-bids.json. Edit that file
to add a card, move a bid, or close an auction (status won or lost, plus
final_price and result). Then run:

    python automation/build_reese_cards.py

A full player build also refreshes this page. Do not hand-edit the HTML.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import site_nav
import internal_links as links
from analytics import GA4_TAG

ROUTE = '/authors/ryan-moalemi/ryans-angel-reese-cards/'
RELATIVE = 'authors/ryan-moalemi/ryans-angel-reese-cards/index.html'
DATA_FILE = Path('data/reese-cards.json')
BIDS_FILE = Path('data/reese-bids.json')
PT = ZoneInfo('America/Los_Angeles')
BID_TYPES = {'auction', 'buy_it_now'}
BID_STATUSES = {'live', 'won', 'lost'}
BASE = 'https://fullcourtbuckets.com'
COLLECTION_TITLE = "Ryan's Angel Reese card collection"
PAGE_TITLE = f"{COLLECTION_TITLE} | Full Court Buckets"
PAGE_DESCRIPTION = (
    "Ryan Moalemi's Angel Reese cards: the totals he paid, raw cards and slabs, "
    "and current values from recent sold comps."
)
# First-person tribute. Curly apostrophes are intentional. The player-page
# link under these paragraphs is separate and stays put.
INTRO_PARAGRAPHS = (
    "Angel Reese is a national treasure. I started watching the WNBA because of her, "
    "and I\u2019ve been a fan ever since. She\u2019s tough, positive, funny, and completely fearless. "
    "She actually reminds me a lot of my mom, who\u2019s an athlete too (professional ice skater).",
    "Angel is having a real moment, but what I like most is what she represents beyond basketball. "
    "A whole generation of young girls looks up to her, and she brings a lot of energy, personality, "
    "and positivity to women\u2019s sports.",
    "Collecting her cards is fun, but for me they also represent something bigger. "
    "I like owning little pieces from what feels like a defining era for women\u2019s sports, "
    "and getting to watch it happen in real time.",
)
PLAYER_CALLOUT = (
    '<p class="reese-cards-link"><a class="inline-link" '
    f'href="{ROUTE}">{COLLECTION_TITLE}</a></p>'
)
PHOTO_CREDIT = 'Photo: eBay seller listing of this card'


def photo_credit(card: dict) -> str:
    credit = str(card.get('photo_credit') or '').strip()
    return credit or PHOTO_CREDIT


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


def prices_as_of(data: dict) -> str:
    """Latest check date among cards that have a numeric value."""
    days = []
    for card in data.get('cards') or []:
        if not is_valued(card):
            continue
        checked = str(card.get('value_checked') or '')[:10]
        if len(checked) == 10:
            days.append(checked)
    if not days:
        updated = str(data.get('updated') or '')[:10]
        return updated if len(updated) == 10 else ''
    return max(days)


def value_as_of(root: Path) -> str:
    data = load_collection(root)
    if not data:
        return ''
    return prices_as_of(data)


def load_bids(root: Path) -> dict | None:
    path = root / BIDS_FILE
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('bids'), list):
        raise ValueError(f'{BIDS_FILE.as_posix()} needs an object with a bids list.')
    for entry in data['bids']:
        _check_bid(entry)
    if '\u2014' in json.dumps(data):
        raise ValueError('Bid data contains an em dash. Keep the copy plain.')
    return data


def _check_bid(entry: dict) -> None:
    required = (
        'id', 'platform', 'url', 'card', 'grade', 'serial', 'type',
        'as_of', 'estimate_low', 'estimate_high', 'status', 'take', 'image',
    )
    missing = [key for key in required if entry.get(key) in (None, '')]
    if missing:
        raise ValueError(f"Bid {entry.get('id') or '?'} is missing {', '.join(missing)}.")
    if entry['type'] not in BID_TYPES:
        raise ValueError(f"Bid {entry['id']} type must be auction or buy_it_now.")
    if str(entry['status']).lower() not in BID_STATUSES:
        raise ValueError(f"Bid {entry['id']} status must be live, won, or lost.")
    if money_amount(entry['estimate_low']) > money_amount(entry['estimate_high']):
        raise ValueError(f"Bid {entry['id']} estimate_low is above estimate_high.")
    if entry['type'] == 'auction' and entry.get('current_bid') is None and entry.get('final_price') is None:
        raise ValueError(f"Bid {entry['id']} needs current_bid or final_price.")
    image = entry['image']
    if not isinstance(image, dict) or not image.get('src') or not image.get('alt'):
        raise ValueError(f"Bid {entry['id']} needs an image src and alt.")


def page_stamp(root: Path) -> str:
    """Sitemap and schema date. Follows a collection edit even when prices did not move."""
    data = load_collection(root) or {}
    days = [value_as_of(root), str(data.get('updated') or '')[:10]]
    bids = load_bids(root) or {}
    days.append(str(bids.get('as_of') or '')[:10])
    days = [day for day in days if len(day) == 10]
    return max(days) if days else ''


def card_checked(card: dict, fallback: str) -> str:
    checked = str(card.get('value_checked') or '')[:10]
    return checked if len(checked) == 10 else fallback


def card_title(card: dict) -> str:
    return f"{card['year']} {card['set']} #{card['card_number']} {card['parallel']}"


def photo_kind(card: dict) -> str:
    grade = str(card.get('grade') or '').strip().lower()
    if grade in ('', 'raw', 'ungraded'):
        return 'card'
    return 'slab'


def counts_in_paid(card: dict) -> bool:
    if card.get('include_in_paid') is True:
        return True
    return is_valued(card)


def value_label(card: dict) -> str:
    return str(card.get('value_label') or '').strip()


def serial_meta(card: dict) -> str:
    serial = card.get('serial_number')
    if not serial:
        return ''
    text = str(serial)
    if text.startswith('/'):
        return f' {text}'
    return f' / {text}'


def serial_html(card: dict) -> str:
    serial = card.get('serial_number')
    if not serial:
        return ''
    text = str(serial)
    if text.startswith('/'):
        return f'<p>Numbered {esc(text)}</p>'
    return f'<p>Serial {esc(text)}</p>'


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
    paid_cards = [card for card in cards if counts_in_paid(card)]
    paid = sum((paid_amount(card) for card in paid_cards), Decimal('0.00'))
    valued_paid = sum((paid_amount(card) for card in valued), Decimal('0.00'))
    current = sum((value_amount(card) for card in valued), Decimal('0.00'))
    change = (current - valued_paid).quantize(CENT, rounding=ROUND_HALF_UP)
    percent = None
    if valued_paid != 0 and valued:
        percent = (change / valued_paid * Decimal(100)).quantize(TENTH, rounding=ROUND_HALF_UP)
    return {
        'count': len(cards),
        'valued_count': len(valued),
        'unknown': unknown,
        'paid_unpriced': [card for card in unknown if counts_in_paid(card)],
        'fully_excluded': [card for card in unknown if not counts_in_paid(card)],
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


def _listing_link(url: str, label: str) -> str:
    """Marketplace listing. nofollow because these are paid third-party auctions."""
    return f'<a href="{esc(url)}" target="_blank" rel="noopener nofollow">{esc(label)}</a>'


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
        if value_label(card):
            return ''
        return '<span class="badge unknown">Value unknown*</span>'
    way = direction(card)
    change = card_change(card)
    percent = card_percent(card)
    label = f'{format_signed_money(change)} ({format_percent(percent)})'
    return f'<span class="badge {way}">{esc(label)}</span>'


def _money_row(label: str, amount) -> str:
    return f'<div><dt>{esc(label)}</dt><dd>{esc(format_money(money_amount(amount)))}</dd></div>'


def _has_amount(card: dict, key: str) -> bool:
    return key in card and card.get(key) is not None


def _cost_rows(card: dict) -> str:
    """Render the purchase lines stored on the card. Do not fill in missing lines."""
    rows = []
    if _has_amount(card, 'hammer'):
        rows.append(_money_row('Hammer', card['hammer']))
    elif _has_amount(card, 'item_price'):
        rows.append(_money_row('Item', card['item_price']))
    if _has_amount(card, 'buyers_premium'):
        rows.append(_money_row("Buyer's premium", card['buyers_premium']))
    if _has_amount(card, 'shipping'):
        rows.append(_money_row('Shipping', card['shipping']))
    if _has_amount(card, 'tax'):
        rows.append(_money_row('Tax', card['tax']))
    if _has_amount(card, 'fees'):
        amount = esc(format_money(money_amount(card['fees'])))
        note = str(card.get('fees_note') or '').strip()
        note_html = f'<span class="fee-note">{esc(note)}</span>' if note else ''
        rows.append(f'<div><dt>Fees</dt><dd>{amount}{note_html}</dd></div>')
    rows.append(_money_row('Total paid', card['price_paid_total']))
    return '\n'.join(rows)


def _detail(card: dict, as_of: str) -> str:
    photos = card.get('photo') or {}
    front = photos.get('front')
    back = photos.get('back')
    cert = str(card.get('psa_cert') or '').strip()
    comps = card.get('value_comps') or []
    if comps:
        rows = []
        for comp in comps:
            raw_date = str(comp.get('date') or '').strip()
            when = long_date(raw_date) if len(raw_date) >= 10 else 'Date unknown'
            url = str(comp.get('url') or '').strip()
            link = _external(url, 'Sale record') if url else ''
            rows.append(
                '<li><span>' + esc(when) + '</span> '
                '<b>' + esc(format_money(money_amount(comp['price']))) + '</b> '
                '<span>' + esc(comp.get('venue') or '') + '</span> '
                + link + '</li>'
            )
        comp_html = '<ul class="comps">' + ''.join(rows) + '</ul>'
    else:
        comp_html = '<p>No verified sold comps.</p>'
    value = value_amount(card)
    label = value_label(card)
    if value is None and label:
        value_html = f'<p class="value-line"><b class="unpriced">Value: {esc(label)}</b></p>'
    elif value is None:
        value_html = '<p class="value-line"><b>Value unknown*</b></p>'
    else:
        value_html = (
            f'<p class="value-line"><b>{esc(format_money(value))}</b> {_badge(card)}</p>'
        )
    source = str(card.get('current_value_source') or '').strip()
    source_html = f'<p>{linkify(source)}</p>' if source else ''
    summary = str(card.get('summary') or '').strip()
    summary_html = f'<p>{esc(summary)}</p>' if summary else ''
    cert_html = ''
    if cert:
        cert_html = (
            f'<p>PSA cert <a href="https://www.psacard.com/cert/{esc(cert)}" '
            f'target="_blank" rel="noopener">{esc(cert)}</a></p>'
        )
    kind = photo_kind(card)
    images = []
    for side, photo in (('front', front), ('back', back)):
        src = photo_src(photo)
        if not src:
            continue
        images.append(
            f'<figure><img src="{esc(src)}" alt="{esc(card_title(card) + ", " + side + " of the " + kind)}" '
            f'width="{photo_attr(photo, "width", 750)}" height="{photo_attr(photo, "height", 1000)}" decoding="async" loading="lazy">'
            f'<figcaption>{esc(side.title())}</figcaption></figure>'
        )
    photo_class = 'detail-photos solo' if len(images) == 1 else 'detail-photos'
    checked = card_checked(card, as_of)
    return f'''<article class="detail" id="{esc(card["id"])}" data-detail="{esc(card["id"])}" hidden>
<div class="{photo_class}">{''.join(images)}</div>
<p class="photo-credit">{esc(photo_credit(card))}</p>
<div class="detail-copy">
<p class="eyebrow">{esc(card.get("grade") or "PSA 10")}</p>
<h2>{esc(card_title(card))}</h2>
{serial_html(card)}
{summary_html}
<p>Bought {esc(long_date(card["purchase_date"]))} on {esc(card.get("source") or "eBay")}.</p>
<h3>Cost</h3>
<dl class="cost">
{_cost_rows(card)}
</dl>
<h3>Value on {esc(short_date(checked))}</h3>
{value_html}
{source_html}
{cert_html}
<h3>Sold comps</h3>
{comp_html}
<h3>Value notes</h3>
<div class="notes">{linkify(card.get("value_notes") or "")}</div>
</div>
</article>'''


def _tile_value(card: dict) -> str:
    value = value_amount(card)
    if value is not None:
        return f'<span>Value <b>{esc(format_money(value))}</b></span>'
    label = value_label(card)
    if label:
        return f'<span>Value: {esc(label)}</span>'
    return '<span>Value <b>Value unknown*</b></span>'


def _tile(card: dict, index: int) -> str:
    front = photo_src((card.get('photo') or {}).get('front'))
    photo = (card.get('photo') or {}).get('front')
    value = value_amount(card)
    ratio = card_ratio(card)
    gain = '' if ratio is None else format(ratio, 'f')
    current = '' if value is None else format(value, 'f')
    kind = photo_kind(card)
    return f'''<button type="button" class="tile" data-id="{esc(card["id"])}" data-index="{index}" data-date="{esc(card["purchase_date"])}" data-gain="{esc(gain)}" data-value="{esc(current)}" data-paid="{esc(format(paid_amount(card), "f"))}" data-year="{esc(card["year"])}" data-direction="{direction(card)}">
<img src="{esc(front)}" alt="{esc(card_title(card) + " " + kind)}" width="{photo_attr(photo, "width", 750)}" height="{photo_attr(photo, "height", 1000)}" decoding="async" loading="lazy">
<span class="photo-credit">{esc(photo_credit(card))}</span>
<span class="tile-copy">
<strong>{esc(card["year"])} {esc(card["set"])}</strong>
<span class="meta">#{esc(card["card_number"])} {esc(card["parallel"])}{esc(serial_meta(card))}</span>
<span class="grade">{esc(card.get("grade") or "PSA 10")}</span>
<span class="bought">Bought {esc(long_date(card["purchase_date"]))}</span>
<span class="figures"><span>Paid <b>{esc(format_money(paid_amount(card)))}</b></span>{_tile_value(card)}</span>
{_badge(card)}
</span>
</button>'''


def _listed(cards: list[dict]) -> str:
    return '; '.join(
        f'{card_title(card)} ({format_money(paid_amount(card))})'
        for card in cards
    )


def _unknown_note(summary: dict) -> str:
    parts = []
    priced_out = summary.get('paid_unpriced') or []
    fully = summary.get('fully_excluded') or []
    if priced_out:
        noun = 'card' if len(priced_out) == 1 else 'cards'
        verb = 'is' if len(priced_out) == 1 else 'are'
        pronoun = 'it' if len(priced_out) == 1 else 'them'
        parts.append(
            f'{len(priced_out)} {noun} {verb} in the paid total and left out of value and change, '
            f'because there are not enough sales to price {pronoun} yet: {_listed(priced_out)}.'
        )
    if fully:
        noun = 'card' if len(fully) == 1 else 'cards'
        verb = 'is' if len(fully) == 1 else 'are'
        parts.append(
            f'{len(fully)} {noun} with no verified sale {verb} left out of paid, value, and change: '
            f'{_listed(fully)}.'
        )
    if not parts:
        return ''
    return '* ' + ' '.join(parts)


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
            'The order total. The detail view lists each line stored for that purchase: '
            'the item or the hammer, shipping, tax, and a buyer\'s premium or fees when they were charged.',
        ),
        (
            'Why does a card say value unknown?',
            'No verified sale was found for that exact card number, parallel, and grade. '
            'That card is left out of the paid, value, and change totals.',
        ),
        (
            'Why does a card say not enough sales to price yet?',
            'There are not enough sold copies to set a price. The card stays in the card count and the paid total. '
            'It is left out of value and change, with no up or down badge.',
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
        f'{_external(HERO["source_url"], HERO["source_name"])}. {esc(HERO["changes"])} '
        '(2024, with the Chicago Sky)'
    )
    return f'''<section class="hero" aria-labelledby="collection-title">
<img class="hero-photo" src="{esc(HERO["src"])}" alt="{esc(HERO["alt"])}" width="{HERO["width"]}" height="{HERO["height"]}" decoding="async" fetchpriority="high">
<div class="hero-shade" aria-hidden="true"></div>
<div class="hero-copy">
<p class="hero-kicker">Personal collection</p>
<h1 id="collection-title"><span class="owner-word">{esc("Ryan's")}</span> <span>Angel Reese</span> <span class="cards-word">cards</span></h1>
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


def format_dollars(amount) -> str:
    value = money_amount(amount)
    if value == value.to_integral_value():
        sign = '-' if value < 0 else ''
        return f'{sign}${abs(int(value)):,}'
    return format_money(value)


def _pt(iso: str) -> datetime:
    return datetime.fromisoformat(str(iso)).astimezone(PT)


def format_clock(iso: str) -> str:
    dt = _pt(iso)
    hour = dt.hour % 12 or 12
    ampm = 'a.m.' if dt.hour < 12 else 'p.m.'
    return f'{hour}:{dt.minute:02d} {ampm} PT, {SHORT_MONTHS[dt.month - 1]} {dt.day}, {dt.year}'


def format_deadline(iso: str) -> str:
    dt = _pt(iso)
    hour = dt.hour % 12 or 12
    ampm = 'a.m.' if dt.hour < 12 else 'p.m.'
    return (
        f'{SHORT_MONTHS[dt.month - 1]} {dt.day}, {dt.year}, '
        f'{hour}:{dt.minute:02d} {ampm} PT'
    )


def bid_status(entry: dict) -> tuple[str, str]:
    status = str(entry.get('status') or '').lower()
    if status == 'won':
        return 'Won', 'won'
    if status == 'lost':
        return 'Lost', 'lost'
    if str(entry.get('type') or '').lower() == 'buy_it_now':
        return 'Buy it now', 'bin'
    return 'Live', 'live'


def premium_span(entry: dict) -> str:
    rate = entry.get('premium_rate')
    if not isinstance(rate, (int, float)) or isinstance(rate, bool):
        return ''
    factor = Decimal('1') + Decimal(str(rate))
    low = (money_amount(entry['estimate_low']) * factor).quantize(CENT, rounding=ROUND_HALF_UP)
    high = (money_amount(entry['estimate_high']) * factor).quantize(CENT, rounding=ROUND_HALF_UP)
    percent = (Decimal(str(rate)) * Decimal(100)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return (
        f'About {format_dollars(low)} to {format_dollars(high)} '
        f"with the {percent}% buyer's premium on this listing."
    )


def _bid_comp(comp: dict) -> str:
    bits = [short_date(comp['date']) if comp.get('date') else 'Date unknown']
    if comp.get('price') is not None:
        bits.append(format_dollars(comp['price']))
    if comp.get('grade'):
        bits.append(str(comp['grade']))
    if comp.get('venue'):
        bits.append(str(comp['venue']))
    label = ' · '.join(bits)
    linked = _external(comp['url'], label) if comp.get('url') else esc(label)
    title = f' <span>{esc(comp["card"])}</span>' if comp.get('card') else ''
    note = f' <span>{esc(comp["note"])}</span>' if comp.get('note') else ''
    return f'<li>{linked}{title}{note}</li>'


def _bid_price(entry: dict) -> str:
    if entry.get('final_price') is not None and str(entry.get('status') or '').lower() in {'won', 'lost'}:
        label = 'Final price'
        amount = format_dollars(entry['final_price'])
    else:
        label = 'Asking' if str(entry.get('type') or '') == 'buy_it_now' else 'Current bid'
        amount = format_dollars(entry['current_bid']) if entry.get('current_bid') is not None else 'See listing'
    return f'<div><dt>{label}</dt><dd>{esc(amount)}</dd></div>'


def _bid_ends(entry: dict) -> str:
    ends = entry.get('ends_at')
    title = f' title="{esc(entry["ends_note"])}"' if entry.get('ends_note') else ''
    if entry.get('ends_label'):
        label = esc(entry['ends_label'])
    elif ends:
        label = esc(format_deadline(ends))
    else:
        return f'<div><dt>Ends</dt><dd class="when"{title}>TBA</dd></div>'
    if ends:
        return f'<div><dt>Ends</dt><dd class="when"{title}><time datetime="{esc(str(ends))}">{label}</time></dd></div>'
    return f'<div><dt>Ends</dt><dd class="when"{title}>{label}</dd></div>'


def _bid_meta(entry: dict) -> str:
    bits = [esc(entry['grade']), esc(entry['serial'])]
    if entry.get('cert'):
        cert = esc(str(entry['cert']))
        if entry.get('cert_url'):
            cert = _external(entry['cert_url'], str(entry['cert']))
        hint = f' title="{esc(entry["cert_note"])}"' if entry.get('cert_note') else ''
        bits.append(f'<span{hint}>Cert {cert}</span>')
    if entry.get('pop_short'):
        bits.append(esc(entry['pop_short']))
    if entry.get('lot_short'):
        lot_title = f' title="{esc(entry["lot"])}"' if entry.get('lot') else ''
        bits.append(f'<span{lot_title}>{esc(entry["lot_short"])}</span>')
    return ' · '.join(bits)


def _bid_article(entry: dict) -> str:
    image = entry['image']
    label, kind = bid_status(entry)
    bid_count = entry.get('bids')
    count_title = f' title="{esc(entry["bids_note"])}"' if entry.get('bids_note') else ''
    count_html = (
        f'<div><dt>Bids</dt><dd{count_title}>{esc(bid_count)}</dd></div>'
        if bid_count is not None else ''
    )
    result = f'<p class="bid-meta">{esc(entry["result"])}</p>' if entry.get('result') else ''
    notes = [part for part in (premium_span(entry), entry.get('estimate_line') or '') if part]
    note_html = f'<p class="bid-note">{esc(" ".join(notes))}</p>' if notes else ''
    comps = ''.join(_bid_comp(comp) for comp in entry.get('comps') or [])
    why = f'<p class="bid-why">{esc(entry["estimate_note"])}</p>' if entry.get('estimate_note') else ''
    comps_html = ''
    if comps or why:
        comps_html = (
            '<details class="bid-comps-details"><summary>Comparable sales</summary>'
            f'<ul class="bid-comps">{comps}</ul>{why}</details>'
        )
    credit = entry['image'].get('credit') or f'Image: {entry["platform"]}'
    estimate = (
        f'{esc(format_dollars(entry["estimate_low"]))} to '
        f'{esc(format_dollars(entry["estimate_high"]))}'
    )
    listing = entry['url']
    return f'''<article class="bid" id="{esc(entry["id"])}">
<div class="bid-photo">
<a class="bid-photo-link" href="{esc(listing)}" target="_blank" rel="noopener nofollow"><img src="{esc(image["src"])}" alt="{esc(image["alt"])}" width="{int(image.get("width") or 760)}" height="{int(image.get("height") or 1200)}" decoding="async" loading="eager"></a>
<p class="photo-credit">{esc(credit.split(":", 1)[0])}: {_listing_link(listing, credit.split(":", 1)[-1].strip())}</p>
</div>
<div class="bid-copy">
<div class="bid-top"><span class="status status-{kind}">{esc(label)}</span>{_external(entry["url"], entry["platform"])}</div>
<h3 class="bid-name">{esc(entry["card"])}</h3>
<p class="bid-meta">{_bid_meta(entry)}</p>
{result}
<dl class="bid-stats">
{_bid_price(entry)}
{count_html}
{_bid_ends(entry)}
<div><dt>FCB estimate</dt><dd>{estimate}</dd></div>
</dl>
{note_html}
<p class="bid-take">{esc(entry["take"])}</p>
{comps_html}
</div>
</article>'''


def render_bids(root: Path) -> str:
    data = load_bids(root)
    if not data or not data.get('bids'):
        return ''
    articles = ''.join(_bid_article(entry) for entry in data['bids'])
    checked = format_clock(data['as_of']) if data.get('as_of') else ''
    stamp = f'<p class="as-of">Bids as of {esc(checked)}</p>' if checked else ''
    return f'''<section class="panel" id="bidding">
<h2>Cards I&#x27;m bidding on</h2>
{stamp}
<div class="bids">{articles}</div>
</section>'''


def render_body(data: dict, root: Path | None = None) -> str:
    cards = list(data['cards'])
    as_of = prices_as_of(data)
    summary = summarize(data)
    ordered = sorted(enumerate(cards), key=lambda pair: (pair[1]['purchase_date'], -pair[0]), reverse=True)
    tiles = ''.join(_tile(card, index) for index, card in ordered)
    details = ''.join(_detail(card, as_of) for card in cards)
    faq_html, faq_entities = _faq(as_of)
    star = '*' if summary['unknown'] else ''
    intro_copy = '\n'.join(f'<p>{paragraph}</p>' for paragraph in INTRO_PARAGRAPHS)
    intro = f'''<section class="intro">
{intro_copy}
<p><a href="/wnba/angel-reese/" target="_blank" rel="noopener">Angel Reese</a> has a player page on this site.</p>
</section>'''
    method = (
        '<section class="panel method" id="method"><h2>How the numbers work</h2>'
        '<p>Values are medians of recent sold prices from the sources listed on each card. '
        'Ryan paid the order total. The detail lists shipping, tax, and any buyer\'s premium or fees. '
        'The values get updated over time. '
        f'A card with no verified sale is marked Value unknown{star} and left out of the paid, value, and change totals. '
        'A card that says not enough sales to price yet stays in the paid total and is left out of value and change.</p>'
        '</section>'
    )
    return f'''<div class="crumb-bar"><div class="shell"><nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a><span aria-hidden="true">/</span><a href="/authors/ryan-moalemi/">Ryan Moalemi</a><span aria-hidden="true">/</span><span>{esc(COLLECTION_TITLE)}</span></nav></div></div>
{_hero()}
<main class="shell" id="content">
{intro}
<section class="panel" id="collection">
<h2>The cards</h2>
{_controls(cards)}
<div class="cards" id="card-grid">{tiles}</div>
<p id="card-empty" class="lede" hidden>No cards match.</p>
</section>
{render_bids(root) if root is not None else ''}
{_stats(summary, as_of)}
{_movers(cards, summary)}
{_chart(cards)}
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
    if (event.target.closest('a')) return;
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
.hero{position:relative;display:flex;align-items:flex-end;overflow:hidden;background:#07060a;height:min(72vh,calc(100svh - 13.25rem));max-height:75vh}
.hero-photo{position:absolute;inset:0;width:100%;height:100%;max-width:none;object-fit:cover;object-position:center top}
.hero-shade{position:absolute;inset:auto 0 0 0;height:68%;background:linear-gradient(180deg,rgba(7,6,10,0) 0%,rgba(7,6,10,.55) 28%,rgba(7,6,10,.94) 70%,#07060a 100%)}
.hero-copy{position:relative;z-index:1;width:min(1120px,94vw);margin:0 auto;padding:8px 0 12px}
.hero-kicker{margin:0 0 6px;color:#f0c36a;font:700 13px/1 Inter,sans-serif;letter-spacing:.16em;text-transform:uppercase}
.hero h1{margin:0;font:900 clamp(3.2rem,min(13vw,18vh),8.2rem)/.84 "Barlow Condensed",Impact,sans-serif;letter-spacing:-.02em;text-transform:uppercase}
.hero h1 span{display:block}
.hero h1 .owner-word{font-size:.38em;letter-spacing:.04em;color:#f6f1e8}
.hero h1 .cards-word{color:#f0c36a}
.hero-line{margin:8px 0 0;font:700 clamp(1.05rem,min(2.2vw,3.4vh),1.55rem)/1.2 "Barlow Condensed",sans-serif;letter-spacing:.02em}
.hero-credit{margin:8px 0 0;max-width:40rem;color:#d9d1c6;font-size:13px;line-height:1.35}
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
.figures{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;margin-top:6px}
.value-line b.unpriced{font:700 22px/1.3 Inter,system-ui,sans-serif}
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
.cost .fee-note{display:block;margin-top:6px;color:#b7b0a6;font:600 13px/1.35 Inter,system-ui,sans-serif;letter-spacing:0;text-transform:none}
.comps{list-style:none;margin:0;padding:0}
.comps li{display:flex;flex-wrap:wrap;gap:8px 14px;padding:8px 0;border-top:1px solid #2b2733}
.notes{color:#e7e0d6}
.value-line{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.value-line b{font:800 32px/1 "Barlow Condensed",sans-serif}
.bids{display:flex;flex-direction:column;gap:12px}
.bid{display:grid;grid-template-columns:168px minmax(0,1fr);background:#120f16;border:1px solid #3a3328;min-width:0}
.bid-photo{background:#09080c;min-width:0}
.bid-photo-link{display:block;line-height:0}
.bid-photo img{display:block;width:100%;height:230px;object-fit:contain;background:#09080c}
.bid .photo-credit{margin:0;padding:6px 8px 8px;color:#9c958b;font-size:11px}
.bid-copy{display:flex;flex-direction:column;gap:8px;padding:12px 14px 14px;min-width:0}
.bid-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.bid-top a{font-weight:800}
.status{display:inline-flex;align-items:center;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
.status-live{background:#10281c;color:#7dffa8}
.status-won{background:#10281c;color:#7dffa8}
.status-lost{background:#2c1218;color:#ff8d9a}
.status-bin{background:#2a2416;color:#f0c36a}
.bid-name{margin:0;font:800 clamp(1.15rem,1.6vw,1.45rem)/1.05 "Barlow Condensed",sans-serif;letter-spacing:.01em;text-transform:uppercase}
.bid-meta{margin:0;color:#d5cdc2;font-size:13px}
.bid-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:2px 0 0}
.bid-stats div{background:#191621;padding:7px 8px;min-width:0}
.bid-stats dt{color:#b7b0a6;font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}
.bid-stats dd{margin:3px 0 0;font:800 20px/1.05 "Barlow Condensed",sans-serif}
.bid-stats dd.when{font:700 13px/1.25 Inter,system-ui,sans-serif}
.bid-note{margin:0;color:#b7b0a6;font-size:13px;line-height:1.4}
.bid-take{margin:0}
.bid-comps-details{border-top:1px solid #2b2733;padding:0}
.bid-comps-details summary{min-height:36px;color:#f0c36a;font-size:12px;letter-spacing:.08em;text-transform:uppercase}
.bid-comps{list-style:none;margin:0;padding:0 0 8px}
.bid-comps li{display:flex;flex-direction:column;gap:2px;padding:8px 0;border-top:1px solid #2b2733;font-size:14px}
.bid-why{margin:0 0 8px;color:#c9c1b6;font-size:13px}
@media(max-width:800px){
.hero{height:min(70vh,calc(100svh - 14.75rem));max-height:72vh}
.hero h1{font-size:clamp(2.8rem,min(16vw,9vh),4.6rem)}
.stats{grid-template-columns:repeat(2,minmax(0,1fr))}
.cost{grid-template-columns:1fr 1fr}
.detail-photos,.detail-photos.solo{grid-template-columns:1fr}
.cards.is-list .tile{grid-template-columns:96px minmax(0,1fr)}
.bid{grid-template-columns:112px minmax(0,1fr)}
.bid-photo img{height:168px}
.bid-stats{grid-template-columns:1fr 1fr}
.bid-copy{padding:10px 10px 12px}
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
    stamp = page_stamp(root)
    _faq_html, faq_entities = _faq(as_of)
    body = render_body(data, root)
    html_text = _head(_schema(data, summary, stamp, faq_entities)) + body + '\n</body>\n</html>\n'
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
    if PLAYER_CALLOUT in text:
        return
    existing = re.compile(
        r'<p class="reese-cards-link"><a class="inline-link" href="'
        + re.escape(ROUTE) + r'">.*?</a></p>',
        re.S,
    )
    if existing.search(text):
        page.write_text(existing.sub(PLAYER_CALLOUT, text, count=1), encoding='utf-8')
        return
    needle = '<div class="overview-strip">'
    if needle not in text:
        raise ValueError('Angel Reese page has no overview strip to attach the card link.')
    page.write_text(text.replace(needle, PLAYER_CALLOUT + needle, 1), encoding='utf-8')


def ensure_sitemaps(root: Path) -> None:
    day = page_stamp(root)
    if not day:
        return
    loc = BASE + ROUTE
    block = f'  <url>\n    <loc>{loc}</loc>\n    <lastmod>{day}</lastmod>\n  </url>'
    for name in ('sitemap.xml', 'pages-sitemap.xml'):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        if '</urlset>' not in text:
            continue
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

"""Editorial rules from docs/EDITORIAL_STYLE.md, applied to every /news/ article.

The check blocks a merge when a story breaks one of these rules:

- The H1, og:title, twitter:title, and JSON-LD headline disagree.
- That headline is all caps.
- The article uses a banned filler phrase.
- The copy credits ESPN as the stats source.
- A betting section is missing the 21+ / 1-800-GAMBLER line.
- A preview whose game date has passed has no archive note linking a published recap.

An existing ESPN box-score, game, or play-by-play link can stay. A short label
on that link ("ESPN", "ESPN box score", "ESPN play-by-play") is the link, not
a new stats-source credit. Injury, odds, and news attributions that name ESPN
with a timestamp stay too.
"""
import datetime as dt
import html
import json
import re
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PACIFIC = ZoneInfo('America/Los_Angeles')

# The title tag may be shortened. These four have to be the same headline.
HEADLINE_FIELDS = ('h1', 'og:title', 'twitter:title', 'json-ld')

BANNED_PHRASES = (
    "Here's the wild part",
    'The wild part?',
    'Like really',
    'Game over.',
    'felt like the moment',
    'was nuts',
    'highest verified sale',
    'top verified sale',
)

# "Like really" also covers the comma in "Like, really cold."
BANNED_RES = tuple(
    re.compile(r'Like,?\s+really', re.I) if phrase == 'Like really'
    else re.compile(re.escape(phrase), re.I)
    for phrase in BANNED_PHRASES
)

# Prose that names ESPN as the source of the stats. Tags may sit between the
# words when the credit is split around a link.
_TAG = r'(?:\s*<[^>]+>\s*)*'
ESPN_CREDIT_RES = (
    re.compile(r"per ESPN(?:'s|&#x27;s|&apos;s)? box scores?", re.I),
    re.compile(r'ESPN data', re.I),
    re.compile(r"ESPN(?:'s|&#x27;s|&apos;s) data", re.I),
    re.compile(r'checked against ESPN', re.I),
    re.compile(rf'Source:\s*{_TAG}ESPN\b', re.I),
    re.compile(rf'from the {_TAG}ESPN box score', re.I),
    re.compile(rf'Times are from the {_TAG}ESPN', re.I),
    re.compile(r"game's ESPN box score", re.I),
    re.compile(r'ESPN box scores', re.I),
)

BETTING_SECTION_RE = re.compile(
    r'betting odds|DraftKings|moneyline|Gamble responsibly',
    re.I,
)
ARCHIVE_SENTENCE = (
    'This preview was published before the game. '
    'For the result, read our game recap.'
)
ARCHIVE_RECAPS_PREFIX = (
    'This preview was published before the games. '
    'For the results, read our recaps:'
)
MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11,
    'december': 12, 'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
    'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}
_MONTH = (
    r'January|February|March|April|May|June|July|August|September|October|'
    r'November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec'
)
DATE_RE = re.compile(rf'\b({_MONTH})\.?\s+(\d{{1,2}}),?\s+(20\d{{2}})\b', re.I)
# "Friday, Oct. 9, at 2:04 PM PT" names the game without repeating the year.
DATE_RE_NO_YEAR = re.compile(
    rf'\b({_MONTH})\.?\s+(\d{{1,2}})\b(?!\s*,?\s*20\d{{2}})',
    re.I,
)


def _articles():
    return json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))


def _unescape(value):
    if value is None:
        return None
    text = html.unescape(value).replace('\xa0', ' ').replace('\u2019', "'")
    return re.sub(r'\s+', ' ', text).strip()


def _visible(fragment):
    """Readable text.

    Block tags become spaces so the next paragraph stays a new sentence.
    Inline tags disappear, so "recap</a>." stays "recap."
    """
    text = re.sub(r'<script\b[^>]*>.*?</script>', ' ', fragment, flags=re.S | re.I)
    text = re.sub(r'<style\b[^>]*>.*?</style>', ' ', text, flags=re.S | re.I)
    text = re.sub(
        r'</?(?:p|div|section|article|h[1-6]|li|ul|ol|br|tr|td|th|blockquote|figcaption|figure|nav|header|footer|aside)\b[^>]*>',
        ' ',
        text,
        flags=re.I,
    )
    text = re.sub(r'<br\s*/?>', ' ', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return _unescape(text) or ''


def _is_all_caps(headline):
    letters = [char for char in headline if char.isalpha()]
    return len(letters) >= 2 and all(char.isupper() for char in letters)


def _meta(page, pattern):
    match = re.search(pattern, page)
    return _unescape(match.group(1)) if match else None


def _headlines(page):
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', page, re.S | re.I)
    h1 = _unescape(re.sub(r'<[^>]+>', '', h1_match.group(1))) if h1_match else None
    og = _meta(page, r'<meta\s+property="og:title"\s+content="([^"]*)"')
    twitter = _meta(page, r'<meta\s+name="twitter:title"\s+content="([^"]*)"')
    ld = []
    for block in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', page, re.S
    ):
        data = json.loads(block)
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if 'headline' in node:
                    ld.append(_unescape(str(node['headline'])))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return {'h1': h1, 'og:title': og, 'twitter:title': twitter, 'json-ld': ld}


def _article_html(page):
    match = re.search(r'<article\b[^>]*>(.*)</article>', page, re.S | re.I)
    return match.group(1) if match else page


def _banned_hits(article_html):
    visible = _visible(article_html)
    hits = []
    for phrase, pattern in zip(BANNED_PHRASES, BANNED_RES):
        if pattern.search(visible):
            hits.append(phrase)
    return hits


def _espn_credit_hits(article_html):
    hits = []
    for pattern in ESPN_CREDIT_RES:
        found = pattern.search(article_html)
        if found:
            hits.append(re.sub(r'\s+', ' ', found.group(0)).strip())
    return hits


def _betting_problem(article_html):
    visible = _visible(article_html)
    if not BETTING_SECTION_RE.search(visible):
        return None
    missing = []
    if '21+' not in visible:
        missing.append('21+')
    if '1-800-GAMBLER' not in visible:
        missing.append('1-800-GAMBLER')
    if missing:
        return 'betting section is missing ' + ' and '.join(missing)
    return None


def _parse_date(month, day, year):
    try:
        return dt.date(int(year), MONTHS[month.lower()], int(day))
    except (KeyError, ValueError):
        return None


def _body_dates(article_html, year):
    without_byline = re.sub(
        r'<div class="byline-row">.*?</div>', ' ', article_html, count=1, flags=re.S
    )
    visible = _visible(without_byline)
    found = []
    for match in DATE_RE.finditer(visible):
        parsed = _parse_date(*match.groups())
        if parsed is not None:
            found.append(parsed)
    for match in DATE_RE_NO_YEAR.finditer(visible):
        parsed = _parse_date(match.group(1), match.group(2), year)
        if parsed is not None:
            found.append(parsed)
    return found


def _publish_date(article):
    raw = str(article.get('date') or '')[:10]
    return dt.date.fromisoformat(raw)


def _game_date(article, article_html):
    """Earliest dated day in the body on or after the publish date.

    A preview is written for a game that has not been played, so that day is
    the game date. Photo captions from earlier months stay behind the publish
    date and drop out.
    """
    publish = _publish_date(article)
    candidates = [day for day in _body_dates(article_html, publish.year) if day >= publish]
    return min(candidates) if candidates else None


def _is_preview(article, headlines):
    slug = article['slug'].lower()
    h1 = (headlines.get('h1') or '').lower()
    return 'preview' in slug or 'preview' in h1


def _archive_hrefs(article_html):
    """Links inside the archive note, plus a "game recap" label anywhere in the article."""
    hrefs = []
    for match in re.finditer(r'<p\b[^>]*>.*?</p>', article_html, re.S | re.I):
        block = match.group(0)
        visible = _visible(block)
        if 'This preview was published before the game' not in visible:
            continue
        hrefs.extend(re.findall(r'<a\b[^>]*href="([^"]+)"', block, re.I))
    for match in re.finditer(
        r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', article_html, re.S | re.I
    ):
        label = (_visible(match.group(2)) or '').lower()
        if label == 'game recap':
            hrefs.append(match.group(1))
    return hrefs


def _news_slug(href):
    """Slug from a site path or absolute URL. Empty when it is not a news post."""
    path = href.strip()
    if '://' in path:
        path = path.split('://', 1)[1]
        path = path.split('/', 1)[1] if '/' in path else ''
    parts = path.split('?', 1)[0].split('#', 1)[0].strip('/').split('/')
    if len(parts) >= 2 and parts[0] == 'news' and parts[1]:
        return parts[1]
    return ''


def _metadata_recap_hrefs(article):
    """A recap named on the articles.json entry, when the note's link is not the only source."""
    hrefs = []
    for key in ('recap', 'recapUrl', 'recapSlug'):
        raw = (article or {}).get(key)
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            text = str(value or '').strip()
            if not text:
                continue
            if text.startswith('/') or '://' in text:
                hrefs.append(text)
            else:
                hrefs.append(f'/news/{text.strip("/")}/')
    return hrefs


def _published_recap(slug, published, game_date, preview_slug):
    """A different story that exists on disk and was published on or after the game."""
    if not slug or slug == preview_slug:
        return False
    recap = published.get(slug)
    if recap is None or not (ROOT / 'news' / slug / 'index.html').is_file():
        return False
    return _publish_date(recap) >= game_date


def _pacific_today():
    return dt.datetime.now(PACIFIC).date()


def check_article(article, page, today=None):
    """Return human-readable problems for one article. `today` is Pacific."""
    today = _pacific_today() if today is None else today
    slug = article['slug']
    problems = []
    headlines = _headlines(page)
    values = [
        headlines['h1'],
        headlines['og:title'],
        headlines['twitter:title'],
        *headlines['json-ld'],
    ]
    if any(value is None or value == '' for value in (
        headlines['h1'], headlines['og:title'], headlines['twitter:title']
    )) or not headlines['json-ld']:
        problems.append(
            f'{slug}: headline fields are missing '
            f'(h1={headlines["h1"]!r}, og={headlines["og:title"]!r}, '
            f'twitter={headlines["twitter:title"]!r}, json-ld={headlines["json-ld"]!r})'
        )
    elif len(set(values)) != 1:
        problems.append(
            f'{slug}: H1, og:title, twitter:title, and JSON-LD headline do not match '
            f'(h1={headlines["h1"]!r}, og={headlines["og:title"]!r}, '
            f'twitter={headlines["twitter:title"]!r}, json-ld={headlines["json-ld"]!r})'
        )
    else:
        headline = headlines['h1']
        if _is_all_caps(headline):
            problems.append(f'{slug}: headline is all caps ({headline!r})')

    article_html = _article_html(page)
    for phrase in _banned_hits(article_html):
        problems.append(f'{slug}: banned filler phrase {phrase!r}')
    for credit in _espn_credit_hits(article_html):
        problems.append(f'{slug}: credits ESPN as a stats source ({credit!r})')
    betting = _betting_problem(article_html)
    if betting:
        problems.append(f'{slug}: {betting}')

    if _is_preview(article, headlines):
        game_date = _game_date(article, article_html)
        if game_date is not None and game_date < today:
            visible = _visible(article_html)
            published = {item['slug']: item for item in _articles()}
            hrefs = _archive_hrefs(article_html) + _metadata_recap_hrefs(article)
            linked = [
                href for href in hrefs
                if _published_recap(_news_slug(href), published, game_date, slug)
            ]
            plural = ARCHIVE_RECAPS_PREFIX in visible
            singular = ARCHIVE_SENTENCE in visible
            needed = 2 if plural else 1
            if not (plural or singular) or len(linked) < needed:
                problems.append(
                    f'{slug}: game date {game_date.isoformat()} has passed and the '
                    'preview has no archive note linking a published recap '
                    f'("{ARCHIVE_SENTENCE}" or "{ARCHIVE_RECAPS_PREFIX}" '
                    f'with {needed} recap link(s))'
                )
    return problems


class EditorialStyleTests(unittest.TestCase):
    def test_every_news_article_follows_the_editorial_guide(self):
        problems = []
        for article in _articles():
            page = (ROOT / 'news' / article['slug'] / 'index.html').read_text(encoding='utf-8')
            problems.extend(check_article(article, page))
        self.assertEqual(problems, [], '\n'.join(problems))

    def test_rules_flag_the_guide_examples(self):
        self.assertTrue(_is_all_caps('DREAM BEAT LIBERTY IN GAME 1'))
        self.assertFalse(_is_all_caps("Burton's late three lifts Valkyries"))
        sample = (
            "<p>Here's the wild part: the lead lasted 11 seconds. "
            'The wild part? The lead lasted 11 seconds. '
            'Like, really cold. Game over. That shot felt like the moment. '
            'The fourth quarter was nuts. Her highest verified sale and her '
            'top verified sale are one lot.</p>'
            '<p>per ESPN box score. Source: ESPN data. checked against ESPN box scores.</p>'
            '<p>Game 3 betting odds from DraftKings.</p>'
            '<p>Box score: <a href="https://www.espn.com/wnba/boxscore/_/gameId/1">'
            'ESPN box score</a>.</p>'
        )
        hits = _banned_hits(sample)
        for phrase in BANNED_PHRASES:
            self.assertIn(phrase, hits)
        credits = _espn_credit_hits(sample)
        self.assertTrue(any('per ESPN box score' in credit for credit in credits))
        self.assertTrue(any('ESPN data' in credit for credit in credits))
        self.assertTrue(any('checked against ESPN' in credit for credit in credits))
        self.assertEqual(_espn_credit_hits(
            '<p>Box score: <a href="https://www.espn.com/wnba/boxscore/_/gameId/1">ESPN</a>.</p>'
            '<p>Allisha Gray is out per ESPN\'s injury report, updated at 3:21 PM PT.</p>'
            '<p>DraftKings via ESPN, checked at 2:04 PM PT.</p>'
        ), [])
        self.assertEqual(
            _betting_problem('<p>Game 3 betting odds: DraftKings lines.</p>'),
            'betting section is missing 21+ and 1-800-GAMBLER',
        )
        self.assertIsNone(_betting_problem(
            '<p>Game 3 betting odds: DraftKings. 21+. Gamble responsibly. 1-800-GAMBLER.</p>'
        ))

    def test_passed_preview_without_a_recap_link_is_blocked(self):
        """The Game 3 preview's game date is October 9, 2026.

        On that date the note is not due yet. On October 10 the note has to
        point at both published recaps. The slugs do not have to contain "recap".
        """
        article = next(item for item in _articles() if item['slug'] == 'semis-game-3-preview')
        page = (ROOT / 'news' / article['slug'] / 'index.html').read_text(encoding='utf-8')
        game_day = dt.date(2026, 10, 9)
        self.assertEqual(_game_date(article, _article_html(page)), game_day)
        on_game_day = [
            problem for problem in check_article(article, page, today=game_day)
            if 'archive note' in problem
        ]
        self.assertEqual(on_game_day, [])
        later = check_article(article, page, today=dt.date(2026, 10, 10))
        self.assertFalse(any('archive note' in problem for problem in later), later)
        self.assertIn('/news/dream-sweep-liberty-game-3-semifinals/', page)
        self.assertIn('/news/aces-valkyries-semis-game-3-recap/', page)
        one_link = page.replace(
            '<a href="/news/aces-valkyries-semis-game-3-recap/">Valkyries sweep the Aces</a>',
            'Valkyries sweep the Aces',
            1,
        )
        short = check_article(article, one_link, today=dt.date(2026, 10, 10))
        self.assertTrue(any('archive note' in problem for problem in short), short)
        unlinked = one_link.replace(
            '<a href="/news/dream-sweep-liberty-game-3-semifinals/">Dream sweep the Liberty</a>',
            'Dream sweep the Liberty',
            1,
        )
        missing = check_article(article, unlinked, today=dt.date(2026, 10, 10))
        self.assertTrue(any('archive note' in problem for problem in missing), missing)
        via_metadata = dict(article)
        via_metadata['recap'] = [
            '/news/dream-sweep-liberty-game-3-semifinals/',
            '/news/aces-valkyries-semis-game-3-recap/',
        ]
        from_metadata = check_article(via_metadata, unlinked, today=dt.date(2026, 10, 10))
        self.assertFalse(any('archive note' in problem for problem in from_metadata), from_metadata)

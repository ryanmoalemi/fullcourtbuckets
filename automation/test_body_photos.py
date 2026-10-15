"""In-body /news/ photos are 16:9. Screenshots and charts are not cropped.

The lead, listing cards, and player pages are out of scope. A card photo in a
list article stays on the card rule. apply_body_photos, called from
order_news_lead, is what a new article goes through.
"""
import json
import re
import unittest
from pathlib import Path

import internal_links as links

ROOT = Path(__file__).resolve().parents[1]

# Focal points checked against the source photos. Each one keeps heads in frame.
BODY_FOCALS = {
    'williams-2025.webp': 'center 0%',
    'astier-2026.webp': 'center 7%',
    'valkyries-bench-target-center-2026.webp': 'center 0%',
    'borlase-dream-gateway-2026.webp': 'center 0%',
    'angel-reese-dream-2026.webp': 'center 2%',
    'sabrina-ionescu-liberty-2026.webp': 'center 0%',
    'janelle-salaun-valkyries-2026.webp': 'center 0%',
    'aja-wilson-aces-2024.webp': 'center 0%',
    'moda-center.webp': 'center 20%',
    'coca-cola-coliseum.webp': 'center 0%',
    'caitlin-clark-fever-2026.webp': 'center 0%',
    'han-xu-liberty-barclays-2026.webp': 'center 0%',
    'gabby-williams-valkyries-2026.webp': 'center 20%',
}

BODY_IMG_RULE = (
    '.article figure.body-photo img,'
    '.article figure.portrait.body-photo img,'
    '.article figure.inline-photo.body-photo img'
    '{display:block;width:100%;max-width:100%;height:auto;aspect-ratio:16/9;'
    'object-fit:cover;object-position:center 20%;}'
)
NO_CROP_IMG_RULE = (
    '.article figure.no-crop img{display:block;width:auto;max-width:100%;height:auto;'
    'max-height:720px;margin-left:auto;margin-right:auto;object-fit:contain;}'
)
NO_CROP_MOBILE_RULE = '.article figure.no-crop img{max-height:70vh;}'

FIGURE_RE = re.compile(r'<figure\b[^>]*>.*?</figure>', re.S)
IMG_RE = re.compile(r'<img\b[^>]*>', re.I)


def _articles():
    return json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))


def _classes(figure: str) -> set[str]:
    return links._figure_classes(figure)


def _src_name(img: str) -> str:
    match = re.search(r'\bsrc="([^"]+)"', img)
    if not match:
        return ''
    return match.group(1).rsplit('/', 1)[-1]


class BodyPhotoTests(unittest.TestCase):
    def test_shared_css_crops_body_photos_and_caps_charts(self):
        css = links.LEAD_CSS
        self.assertIn(BODY_IMG_RULE, css)
        self.assertIn(NO_CROP_IMG_RULE, css)
        self.assertIn(NO_CROP_MOBILE_RULE, css)
        self.assertTrue(css.endswith(links._LEAD_BLOCK_END))

    def test_published_stories_follow_the_body_photo_rule(self):
        for article in _articles():
            slug = article['slug']
            html = (ROOT / 'news' / slug / 'index.html').read_text(encoding='utf-8')
            if slug == '2026-wnba-finals-ratings-tracker':
                body = html.split('<article', 1)[1].split('</article>', 1)[0]
                self.assertNotIn('lead-photo', body)
                self.assertNotIn('tracker-matchup', body)
                self.assertNotIn('matchup-1200.webp', body)
                self.assertIn('tracker-compact', body)
                continue
            self.assertIn(BODY_IMG_RULE, html, slug)
            self.assertIn(NO_CROP_IMG_RULE, html, slug)
            self.assertIn(NO_CROP_MOBILE_RULE, html, slug)
            self.assertEqual(len(re.findall(r'<figure\b[^>]*\blead-photo\b', html)), 1, slug)
            for figure in FIGURE_RE.findall(html):
                classes = _classes(figure)
                img = IMG_RE.search(figure)
                if 'lead-photo' in classes:
                    self.assertNotIn('body-photo', classes, slug)
                    self.assertNotIn('no-crop', classes, slug)
                    continue
                if 'card' in classes:
                    self.assertNotIn('body-photo', classes, slug)
                    self.assertNotIn('no-crop', classes, slug)
                    continue
                if img is None:
                    if classes & {'chart', 'stat-board', 'screenshot'}:
                        self.assertIn('no-crop', classes, slug)
                    continue
                name = _src_name(img.group(0))
                if 'no-crop' in classes or classes & {'screenshot', 'chart', 'stat-board'}:
                    self.assertIn('no-crop', classes, f'{slug} {name}')
                    self.assertNotIn('body-photo', classes, f'{slug} {name}')
                    self.assertNotIn('object-fit:cover', img.group(0), f'{slug} {name}')
                    self.assertNotIn('aspect-ratio', img.group(0), f'{slug} {name}')
                    continue
                self.assertIn('body-photo', classes, f'{slug} {name}')
                focal = re.search(r'object-position\s*:\s*([^;"]+)', img.group(0))
                self.assertIsNotNone(focal, f'{slug} {name}')
                raw = re.sub(r'\s+', ' ', focal.group(1).strip().lower())
                self.assertRegex(raw, links._FOCAL_RE, f'{slug} {name}')
                if name in BODY_FOCALS:
                    self.assertEqual(raw, BODY_FOCALS[name], f'{slug} {name}')

    def test_new_article_gets_the_crop_and_leaves_a_screenshot_whole(self):
        bare = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Future Recap</title>
<style>.article h1{margin:0}</style></head>
<body><article class="article"><h1>Future Recap</h1><p class="lead">Later.</p>
<figure><img src="/images/articles/future.webp" alt="A player" width="1200" height="800" loading="lazy"></figure>
<figure class="portrait" style="max-width:420px;margin-left:auto;margin-right:auto"><img src="/images/articles/future-body.webp" alt="A player at the rim" width="1000" height="1500" loading="lazy"></figure>
<figure class="screenshot" style="max-width:420px"><img src="/images/articles/future-phone.webp" alt="A phone screenshot of a post" width="690" height="1536" loading="lazy"></figure>
<figure class="chart"><svg viewBox="0 0 640 360"></svg><figcaption>Series chart</figcaption></figure>
</article></body></html>
'''
        html = links.order_news_lead(bare)
        again = links.order_news_lead(html)
        self.assertEqual(html, again)
        self.assertIn(BODY_IMG_RULE, html)
        self.assertIn(NO_CROP_MOBILE_RULE, html)
        figures = FIGURE_RE.findall(html)
        self.assertEqual(len(figures), 4)
        lead, body, shot, chart = figures
        self.assertIn('lead-photo', _classes(lead))
        self.assertNotIn('body-photo', _classes(lead))
        self.assertEqual(_classes(body), {'portrait', 'body-photo'})
        self.assertNotIn('max-width', body.split('>', 1)[0])
        body_img = IMG_RE.search(body).group(0)
        self.assertIn('object-position:center 20%', body_img)
        self.assertIn('loading="lazy"', body_img)
        self.assertIn('no-crop', _classes(shot))
        self.assertNotIn('body-photo', _classes(shot))
        self.assertIn('max-width:420px', shot.split('>', 1)[0])
        self.assertNotIn('object-position', IMG_RE.search(shot).group(0))
        self.assertIn('no-crop', _classes(chart))
        self.assertNotIn('body-photo', _classes(chart))
        self.assertNotIn('<img', chart)

    def test_a_saved_focal_point_is_kept(self):
        figure = (
            '<figure><img src="/images/articles/future-body.webp" alt="A player" '
            'width="1000" height="1500" style="object-position:center 4%"></figure>'
        )
        html = links.apply_body_photos(f'<article>{figure}</article>')
        img = IMG_RE.search(html).group(0)
        self.assertIn('object-position:center 4%', img)
        forced = links.apply_body_photos(
            f'<article>{figure}</article>',
            focals={'future-body.webp': 'center 0%'},
        )
        self.assertIn('object-position:center 0%', IMG_RE.search(forced).group(0))
        kept = links.apply_body_photos(forced)
        self.assertIn('object-position:center 0%', IMG_RE.search(kept).group(0))

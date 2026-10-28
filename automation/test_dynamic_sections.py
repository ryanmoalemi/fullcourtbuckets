"""Time-sensitive text lives in data-fcb-dynamic sections and stays current."""
import tempfile
import re
import unittest
from pathlib import Path
from unittest import mock

import dynamic_sections as ds

ROOT = Path(__file__).resolve().parents[1]


class RepoIsCurrent(unittest.TestCase):
    def test_no_stale_sections_or_wording(self):
        self.assertEqual(ds.stale_problems(ROOT), [], 'run automation/dynamic_sections.py')

    def test_rendering_is_idempotent(self):
        s = ds.finals_series.series(ROOT)
        for path in ds.html_files(ROOT):
            text = path.read_text(encoding='utf-8')
            if 'data-fcb-dynamic' in text:
                self.assertEqual(ds.render_html(text, ROOT, s), text, f'{path} is stale: run dynamic_sections.py')


class CheckCatchesStaleness(unittest.TestCase):
    def check(self, html: str, latest='2026-10-26'):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / 'x' / 'index.html'
            page.parent.mkdir()
            page.write_text(html, encoding='utf-8')
            with mock.patch.object(ds.finals_series, 'latest_day', return_value=latest):
                return ds.stale_problems(Path(tmp))

    def test_old_marked_section_fails(self):
        html = ('<p data-fcb-dynamic="series-status" data-fcb-source="data/games" '
                'data-fcb-updated="2026-10-24">old</p><!--/fcb-dynamic-->')
        self.assertTrue(self.check(html))

    def test_current_marked_section_passes(self):
        html = ('<p data-fcb-dynamic="series-status" data-fcb-source="data/games" '
                'data-fcb-updated="2026-10-26">Game 6 is Thursday</p><!--/fcb-dynamic-->')
        self.assertEqual(self.check(html), [])

    def test_unmarked_stale_wording_fails(self):
        for text in ('Game 5 is Monday.', 'Finals open Saturday', 'Game 1 · 0 games completed'):
            self.assertTrue(self.check(f'<p>{text}</p>'), text)


if __name__ == '__main__':
    unittest.main()


class TrackerSectionsTests(unittest.TestCase):
    def test_tracker_time_sensitive_lines_are_dynamic(self):
        text = (ROOT / 'news' / '2026-wnba-finals-ratings-tracker' / 'index.html').read_text(encoding='utf-8')
        for kind in ('tracker-updated', 'tracker-scope', 'tracker-schedule', 'tracker-sched-note',
                     'tracker-g6-venue', 'tracker-g6-cell', 'tracker-finals-row'):
            self.assertIn(f'data-fcb-dynamic="{kind}"', text, kind)
        unmarked = ds.SECTION.sub(' ', text)
        self.assertNotRegex(unmarked, r'Updated [A-Z][a-z]+\.? \d+, 20\d\d, PT')
        self.assertNotIn('through Game ', re.sub(r'<script\b.*?</script>', ' ', unmarked, flags=re.S))

"""Ryan's standing rule: live play-by-play pages update every 30 seconds during a game."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
import build_pbp  # noqa: E402


class LivePbpEvery30Seconds(unittest.TestCase):
    def test_builder_default_is_30_seconds(self):
        self.assertEqual(build_pbp.LIVE_UPDATE_SECONDS, 30)
        self.assertIn('30000', build_pbp.LIVE_REFRESH)
        self.assertIn('every 30 seconds', build_pbp.LIVE_NOTE)

    def test_live_pages_reload_and_final_pages_do_not(self):
        page = build_pbp.with_live_refresh('<html><body>x</body></html>')
        self.assertIn('setInterval(', page)
        self.assertIn(',30000)', page)
        self.assertIn('pbp-live-refresh', page)

    def test_loop_polls_and_publishes_every_30_seconds(self):
        loop = (ROOT / 'automation/live_pbp_loop.sh').read_text()
        self.assertIn('POLL=${POLL_SECONDS:-30}', loop)
        self.assertIn('MINPUSH=${MIN_PUSH_SECONDS:-30}', loop)
        wf = (ROOT / '.github/workflows/fcb-live-pbp.yml').read_text()
        self.assertRegex(wf, r"POLL_SECONDS: '30'")
        self.assertRegex(wf, r"MIN_PUSH_SECONDS: '30'")

    def test_no_minute_wording_left_on_pbp_pages(self):
        for page in (ROOT / 'wnba/finals').rglob('play-by-play/index.html'):
            text = page.read_text(encoding='utf-8')
            self.assertNotIn('within about a minute', text, page)
            if 'NOT STARTED' in text:
                self.assertIn('pbp-live-refresh', text, page)


if __name__ == '__main__':
    unittest.main()

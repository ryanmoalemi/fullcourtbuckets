"""Finals database: pagination sits directly under the table, help text below the pagination, on every viewport."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TrackerPagerOrder(unittest.TestCase):
    def test_pager_then_help_text(self):
        for path in ROOT.rglob('index.html'):
            html = path.read_text(encoding='utf-8', errors='ignore')
            if 'id="hdb-pager"' not in html:
                continue
            self.assertLess(html.index('id="hdb-pager"'), html.index('class="hdb-foot'), path)
            # In the phone flex layout the help block must share the pager's order so DOM order applies.
            pager = re.findall(r'\.hdb-pager\{order:(\d+)\}', html)
            foot = re.findall(r'\.hdb-foot\{order:(\d+)\}', html)
            if pager:
                self.assertTrue(foot and int(foot[-1]) >= int(pager[-1]), path)


if __name__ == '__main__':
    unittest.main()

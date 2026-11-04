"""Career-high recap links fire only when the FAQ, box score, and recap agree."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import career_high_recap


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


class CareerHighRecapTests(unittest.TestCase):
    def _root(self, tmp: Path, *, points=18, recap=True, dated=True) -> Path:
        answer = 'JJ Quinerly career high is 18 points, scored against the Phoenix Mercury on July 7, 2025.'
        if not dated:
            answer = 'She averaged a career-high 9.7 points in 2022.'
        _write(tmp / 'data' / 'wnba' / 'faq' / 'jj-quinerly.json', {
            'slug': 'jj-quinerly',
            'player_name': 'JJ Quinerly',
            'items': [{'question': 'What is JJ Quinerly\'s career high?', 'answer': answer}],
        })
        _write(tmp / 'data' / 'games' / '2025-07-07-phx.json', {
            'date': '2025-07-07',
            'espn_game_id': '401000001',
            'players': [{'name': 'JJ Quinerly', 'pts': points, 'did_not_play': False}],
        })
        articles = []
        if recap:
            articles.append({
                'slug': 'mercury-wings-recap',
                'url': '/news/mercury-wings-recap/',
                'gameId': '401000001',
            })
        _write(tmp / 'articles.json', articles)
        return tmp

    def test_link_when_faq_box_score_and_recap_agree(self):
        import tempfile
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(folder))
        self._root(folder)
        note = career_high_recap.note_html('jj-quinerly', folder)
        self.assertIn('18 points on July 7, 2025', note)
        self.assertIn('href="/news/mercury-wings-recap/"', note)
        self.assertIn('career-high-recap', note)
        self.assertNotIn('\u2014', note)

    def test_no_link_when_the_box_score_disagrees(self):
        import tempfile
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(folder))
        self._root(folder, points=12)
        self.assertEqual(career_high_recap.note_html('jj-quinerly', folder), '')

    def test_no_link_for_a_season_average_or_a_game_without_a_recap(self):
        import tempfile
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(folder))
        self._root(folder, dated=False)
        self.assertEqual(career_high_recap.note_html('jj-quinerly', folder), '')
        self._root(folder, recap=False)
        self.assertEqual(career_high_recap.note_html('jj-quinerly', folder), '')

    def test_note_goes_under_the_table(self):
        html = '<section id="stats"><h2>Season</h2><table><tr><td>1</td></tr></table></section>'
        note = '<p class="career-high-recap">Career-high game in our logs: 18 points on July 7, 2025. <a href="/news/x/">Full Court Buckets recap</a>.</p>'
        updated = career_high_recap.insert_note(html, note)
        self.assertLess(updated.find('</table>'), updated.find('career-high-recap'))
        self.assertIn('</section>', updated[updated.find('career-high-recap'):])


if __name__ == '__main__':
    unittest.main()

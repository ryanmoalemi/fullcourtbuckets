import unittest

import publish_articles as pa


class TableTest(unittest.TestCase):
    def test_pipe_table(self):
        md = 'Intro.\n\n| Bonus | 2026 |\n|---|---:|\n| **Champion** | [$60,000](/x/) |\n| MVP | $30,000 |\n\nAfter.'
        out = pa.body_html(md)
        self.assertIn('<div class="table-wrap"><table><thead><tr><th scope="col">Bonus</th>', out)
        self.assertIn('<tbody><tr><td><strong>Champion</strong></td><td><a class="inline-link" href="/x/"', out)
        self.assertEqual(out.count('<tr>'), 3)
        self.assertIn('<p>After.</p>', out)

    def test_no_separator_is_paragraph(self):
        out = pa.body_html('| not a table |')
        self.assertNotIn('<table>', out)
        self.assertIn('<p class="lead">| not a table |</p>', out)

    def test_chart_line_and_inline_headshot(self):
        md = (
            'Lead.\n\n'
            '![Offensive fouls by game](/images/articles/example/chart.webp)\n\n'
            '![Angel Reese](/images/players/angel-reese/portrait.webp) [Angel Reese](/wnba/angel-reese/) had 5.\n'
        )
        out = pa.body_html(md)
        self.assertIn('<p class="lead">Lead.</p>', out)
        self.assertIn('<figure class="chart no-crop">', out)
        self.assertIn('class="player-face"', out)
        self.assertIn('href="/wnba/angel-reese/"', out)
        self.assertNotIn('![', out)


if __name__ == '__main__':
    unittest.main()

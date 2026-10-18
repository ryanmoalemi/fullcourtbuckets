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


if __name__ == '__main__':
    unittest.main()

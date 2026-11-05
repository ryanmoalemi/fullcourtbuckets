"""Same name and doorway is one venue. A different street stays a different bar."""
import unittest

import build_where_to_watch as watch


def row(ident, name, street, city='Arlington', state='VA', verification='source_page', **extra):
    base = {
        'id': ident, 'name': name, 'street': street, 'city': city, 'state': state,
        'country': 'US', 'team_market': 'Washington Mystics', 'verification_type': verification,
        'verification_date': '2026-10-20', 'source_name': 'Venue website',
        'source_url': 'https://example.com/', 'website': 'https://example.com/',
        'phone': '', 'directions': '', 'games_note': '', 'logo': '', 'bar_quote': '',
    }
    base.update(extra)
    return base


class VenueDedupeTests(unittest.TestCase):
    def test_suite_wording_merges_and_keeps_staff_evidence(self):
        rows = watch.load()
        ids = [item['id'] for item in rows]
        self.assertNotIn('conf-westover-taco-arlington', ids)
        self.assertNotIn('conf-heroics-sports-lounge-des-moines', ids)
        westover = next(item for item in rows if item['id'] == 'va-arlington-westover-taco')
        self.assertEqual(westover['verification_type'], 'staff_reply')
        self.assertEqual(westover['phone'], '703-297-3030')
        self.assertIn('DirecTV', westover['games_note'])
        self.assertIn('Suite B', westover['street'])
        heroics = next(item for item in rows if item['id'] == 'ia-dsm-heroics')
        self.assertEqual(heroics['verification_type'], 'staff_reply')
        self.assertIn('Ste 101', heroics['street'])
        self.assertEqual(watch.stats(rows)['venues'], 389)
        self.assertEqual(watch.stats(rows)['confirmed'], 293)

    def test_a_real_second_branch_stays_separate(self):
        merged = watch.dedupe_rows([
            row('a', 'Heroics Sports Lounge', '2005 Ingersoll Ave Ste 101', city='Des Moines', state='IA'),
            row('b', 'Heroics Sports Lounge', '88 Grand Ave', city='Des Moines', state='IA'),
        ])
        self.assertEqual({item['id'] for item in merged}, {'a', 'b'})


if __name__ == '__main__':
    unittest.main()

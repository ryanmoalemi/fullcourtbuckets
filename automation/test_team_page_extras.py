import unittest
from pathlib import Path
import build_players
import team_page_extras as tx

ROOT = Path(__file__).resolve().parents[1]


class TeamPageExtrasTests(unittest.TestCase):
    def test_traded_player_uses_line_with_this_team(self):
        profile = {'season_stats': [
            {'season': 2026, 'season_type': 2, 'team': {'id': 1}, 'pts': 5},
            {'season': 2026, 'season_type': 2, 'team': {'id': 2}, 'pts': 1},
        ]}
        self.assertEqual(build_players._season_line_2026(profile, 2)['pts'], 1)
        self.assertIsNone(build_players._season_line_2026(profile))

    def test_facts_cover_every_team_and_credit_wnba_com(self):
        facts = tx.load_facts(ROOT)
        self.assertGreaterEqual(len(facts.get('teams', facts)), 15)
        self.assertNotIn('ESPN', (ROOT / 'automation/team_page_extras.py').read_text())

    def test_faq_schema_matches_visible_questions(self):
        items = [('Who leads in points?', 'A, 20.0 per game.')]
        node = tx.faq_schema(items, 'https://fullcourtbuckets.com/wnba/teams/x/')
        self.assertEqual(node['@type'], 'FAQPage')
        self.assertEqual(node['mainEntity'][0]['name'], items[0][0])
        html = tx.faq_html(items, '2026-10-27')
        self.assertIn('data-fcb-dynamic="team-faq"', html)
        self.assertIn('Who leads in points?', html)

    def test_built_team_page_puts_roster_first_and_offers_cc0_csv(self):
        slot = {'id': 1611661313, 'slug': 'new-york-liberty', 'full_name': 'New York Liberty',
                'conference': 'Eastern', 'players': [
                    {'id': 1, 'slug': 'anneli-maley', 'name': 'Anneli Maley'},
                    {'id': 2, 'slug': 'breanna-stewart', 'name': 'Breanna Stewart'}]}
        page = build_players.team_page(slot, include_standings=True, menu=[], root=ROOT)
        body = page[page.find('<main'):]
        self.assertLess(body.find('id="roster"'), body.find('id="faq"'))
        self.assertLess(body.find('team-lead'), body.find('id="roster"'))
        self.assertIn('CC0', body)
        self.assertIn('Cite this', body)
        self.assertIn('BreadcrumbList', page)
        self.assertIn('FAQPage', page)
        self.assertIn('class="breadcrumbs"', page)


class TeamPagePhaseTwoTests(unittest.TestCase):
    def test_fallback_avatar_uses_initials(self):
        html = tx.headshot_html(ROOT, 'no-such-player-slug', 'Matilde Villa')
        self.assertIn('roster-face-fallback', html)
        self.assertIn('>MV<', html)

    def test_approved_portrait_is_a_circle_image(self):
        slug, src = next(iter(tx.portraits(ROOT).items()))
        self.assertIn(src, tx.headshot_html(ROOT, slug, 'X'))

    def test_bio_cells_leave_unknowns_blank_and_trim(self):
        self.assertEqual(tx.bio_cells({}), ['', '', '', ''])
        self.assertEqual(tx.bio_cells({'height': '6-4', 'age': 30, 'experience': 'R', 'school': '  ', 'country': 'Australia'}),
                         ['6-4', '30', 'Rookie', 'Australia'])

    def test_franchise_section_credits_wnba_com_and_cites_capacity_source(self):
        html = tx.franchise_html(ROOT, {'full_name': 'New York Liberty', 'slug': 'new-york-liberty'})
        self.assertIn('WNBA.com', html)
        self.assertIn('capacity 17,553 for basketball, per <a href="https://www.barclayscenter.com/about-us"', html)
        self.assertNotIn('ESPN', html)
        self.assertEqual(tx.arena_capacity(None, 'X', {}), (None, {}))
        self.assertEqual(tx.arena_capacity(None, 'X', {'arena_capacity': '19060', 'source': 's'})[0], 19060)

    def test_draft_history_and_schedule_sections(self):
        self.assertEqual(tx.draft_text({'undrafted': True}), 'Undrafted')
        self.assertEqual(tx.draft_text({'year': 2020, 'round': 1, 'pick': 2}), '2020 R1, No. 2')
        self.assertEqual(tx.draft_text({}), '')
        self.assertEqual(tx.draft_text({'year': 2020, 'round': 1, 'pick': 2, 'drafted_by': 'Dallas Wings'}), '2020 R1, No. 2 (Dallas Wings)')
        self.assertEqual(tx.draft_fields({'year': 2020, 'round': 1, 'pick': 2, 'drafted_by': 'Dallas Wings'}), [2020, 1, 2, 'Dallas Wings', 'no'])
        slot = {'full_name': 'New York Liberty', 'slug': 'new-york-liberty'}
        hist = tx.history_html(ROOT, slot)
        self.assertIn('data-fcb-dynamic="team-history"', hist)
        self.assertIn('<td>1997</td>', hist)
        sched = tx.schedule_html(ROOT, slot)
        self.assertIn('data-fcb-dynamic="team-season-schedule"', sched)
        self.assertEqual(tx.schedule_csv(ROOT, slot).count('Regular season'), 44)
        for text in (hist, sched):
            self.assertNotIn('ESPN', text)
            self.assertNotIn('balldontlie', text.casefold())

    def test_playoff_section_is_dynamic_and_absent_for_non_playoff_team(self):
        dream = tx.playoff_html(ROOT, {'full_name': 'Atlanta Dream', 'slug': 'atlanta-dream'})
        self.assertIn('data-fcb-dynamic="team-schedule"', dream)
        self.assertEqual(tx.playoff_html(ROOT, {'full_name': 'Seattle Storm', 'slug': 'seattle-storm'}), '')


if __name__ == '__main__':
    unittest.main()

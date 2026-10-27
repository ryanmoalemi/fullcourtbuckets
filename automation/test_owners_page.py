"""The /wnba/owners/ page is generated from data/wnba/owners/ and follows Rule #1."""
import csv
import json
import re
import unittest
import zipfile
from pathlib import Path

import build_owners as owners
from test_byline_order import byline_problems

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'wnba' / 'owners' / 'index.html'


def visible(html: str) -> str:
    html = re.sub(r'<style\b[^>]*>.*?</style>', '', html, flags=re.S)
    return re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S)


class OwnersPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = owners.load()
        cls.stats = owners.stats(cls.data)
        cls.html = PAGE.read_text(encoding='utf-8')
        cls.rendered = owners.render(cls.data, cls.stats)

    def test_committed_page_matches_the_generator(self):
        import social_meta  # share tags are added after every builder
        norm = lambda h: re.sub(r'\s*</head>', '</head>', social_meta.social_block(h, social_meta.default_image_url(), social_meta.DEFAULT_ALT, 1200, 630))
        self.assertEqual(norm(self.html), norm(self.rendered))

    def test_byline_sits_under_the_h1(self):
        self.assertEqual(byline_problems(self.html, 'owners'), [])
        self.assertEqual(self.html.count('<h1>'), 1)
        self.assertIn(f'<h1>{owners.esc(owners.H1)}</h1>', self.html)

    def test_only_supporting_material_sits_above_the_first_table(self):
        main = self.html.split('</time></div>', 1)[1]
        above = main[:main.find('<table')]
        self.assertIn('class="ow-meta"', above)
        self.assertIn('class="ow-intro"', above)
        self.assertNotIn('class="ow-answer"', above)
        self.assertIn('id="ownership"', above)
        intro = re.sub(r'<[^>]+>', '', re.search(r'<p class="ow-intro">(.*?)</p>', above, re.S).group(1))
        self.assertLessEqual(len(intro), 160, intro)
        for banned in ('<ul', '<ol', '<li', 'ow-finding', 'id="findings"', 'ow-local', 'Mohegan', '<figure', '<img src="/images/articles'):
            self.assertNotIn(banned, above, banned)
        self.assertLess(main.find('id="prices"'), main.find('Mohegan'))
        self.assertLess(main.find('id="prices"'), main.find('ow-local'))

    def test_headline_fields_agree(self):
        ld = [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', self.html, re.S)]
        article = next(x for x in ld if x['@type'] == 'Article')
        self.assertEqual(article['headline'], owners.H1)
        self.assertIn(f'<meta property="og:title" content="{owners.esc(owners.H1)}">', self.html)
        self.assertIn(f'<meta name="twitter:title" content="{owners.esc(owners.H1)}">', self.html)
        self.assertNotIn('FAQPage', self.html)

    def test_dataset_is_cc0_with_every_download(self):
        ld = [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', self.html, re.S)]
        dataset = next(x for x in ld if x['@type'] == 'Dataset')
        self.assertEqual(dataset['license'], 'https://creativecommons.org/publicdomain/zero/1.0/')
        for item in dataset['distribution']:
            name = item['contentUrl'].rsplit('/', 1)[1]
            self.assertTrue((ROOT / 'wnba' / 'owners' / name).is_file() or name.endswith('.json'), name)
        with zipfile.ZipFile(ROOT / 'wnba' / 'owners' / owners.ZIP_NAME) as z:
            for name in owners.COLLECTIONS:
                self.assertIn(f'{name}.csv', z.namelist())

    def test_corrections_go_to_the_existing_address(self):
        self.assertIn('mailto:ryan@fullcourtbuckets.com', self.html)
        self.assertNotIn('corrections@', self.html)

    def test_no_espn_aggregator_or_stats_api_credit(self):
        main = self.html.split('<main', 1)[1].split('</main>', 1)[0]
        text = re.sub(r'<[^>]+>', ' ', visible(main)).lower()
        for banned in ('espn', 'balldontlie', 'oursportscentral', 'wikipedia', 'at least', '{', 'oct xx'):
            self.assertNotIn(banned, text)

    def test_every_row_is_on_the_page_with_its_evidence(self):
        for name, key in (('ownership', 'team_id'), ('transactions', 'transaction_id'), ('facility_projects', 'project_id')):
            for row in self.data[name]:
                if name == 'ownership' and not row['scope'].startswith('active'):
                    continue
                self.assertIn(f'id="{row[key]}"', self.html, row[key])
        for row in self.data['investors']:
            if row['team_scope'] == 'active':
                self.assertIn(f'id="{row["relationship_id"]}"', self.html)
                if row['primary_source_url']:
                    self.assertIn(owners.esc(row['primary_source_url']), self.html)

    def test_estimate_publishers_only_back_estimates(self):
        for row in self.data['ownership'] + self.data['investors']:
            for field in ('controlling_owner_source_url', 'primary_source_url'):
                url = row.get(field) or ''
                for host in ('cnbc.com', 'forbes.com', 'www.sportico.com'):
                    self.assertNotIn(host, url, row)

    def test_counts_come_from_the_data(self):
        active = [r for r in self.data['ownership'] if r['scope'].startswith('active')]
        self.assertIn(f'facility projects for all {len(active)} teams', self.html)
        self.assertIn(f'Investor register: {len(self.data["investors"])} rows', self.html)
        self.assertEqual(self.stats['teams'], 15)

    def test_internal_links_resolve(self):
        for href in set(re.findall(r'href="(/[^"#?]*)', self.html)):
            if href.endswith(('.css', '.js', '.svg', '.png', '.webp', '.xml')):
                continue
            target = ROOT / href.lstrip('/')
            self.assertTrue(target.is_file() or (target / 'index.html').is_file(), href)

    def test_athlete_finding_uses_the_playing_field_and_ids(self):
        rows = [r for r in self.data['investors'] if r['has_professional_playing_experience'] == 'yes'
                and r['counts_toward_active_findings'] == 'yes']
        ids = {r['person_or_entity_id'] for r in rows}
        self.assertIn('Masai Ujiri', {r['investor'] for r in rows})
        self.assertIn(f'FCB has documented {len(ids)} people with professional playing experience', self.html)
        self.assertNotIn('Ginny Gilder', ', '.join(self.stats['athletes']))

    def test_officer_only_form_d_does_not_count_as_control(self):
        for r in self.data['ownership']:
            if 'sec.gov' in r['controlling_owner_source_url'] and 'Form D' in r['owner_claim_as_described']:
                self.assertNotEqual(r['controlling_owner_evidence'], 'sourced', r['team'])

    def test_register_rows_reconcile(self):
        s = self.stats
        self.assertEqual(s['rows_total'], s['relationships'] + s['rows_future'] + s['rows_unnamed'] + s['rows_other_excluded'])

    def test_no_facility_dollar_total_is_published(self):
        self.assertNotIn('$652', self.html)
        self.assertTrue(all(o['eligible_for_usd_total'] == 'no' for o in self.data['facility_financials']))

    def test_every_active_team_has_a_practice_arrangement(self):
        for r in self.data['ownership']:
            if r['scope'].startswith('active'):
                self.assertTrue(r['practice_arrangement'], r['team'])

    def test_listed_as_a_static_sitemap_page(self):
        self.assertIn("('wnba/owners/index.html', '/wnba/owners/')", (ROOT / 'automation' / 'build_players.py').read_text(encoding='utf-8'))

    def test_only_credited_owner_photos_on_page(self):
        """Ryan (Oct 19, 2026): small owner circles allowed, but only openly licensed, credited, self-hosted ones."""
        import csv
        main = self.html.split('<main', 1)[1].split('</main>', 1)[0]
        imgs = re.findall(r'<img\b[^>]*>', main)
        with (ROOT / 'data' / 'wnba' / 'owners' / 'owner_photos.csv').open(encoding='utf-8') as fh:
            photos = {r['image_path']: r for r in csv.DictReader(fh) if r['display'] == 'photo'}
        for tag in imgs:
            if 'ryan-moalemi-photo-byline' in tag:
                continue
            src = re.search(r'src="([^"]+)"', tag).group(1)
            self.assertIn(src, photos, tag)
            row = photos[src]
            self.assertTrue(row['license'] and row['author'] and row['source_url'].startswith('https://commons.wikimedia.org/'), row)
            self.assertRegex(row['license'], r'^(CC BY|CC BY-SA|Public domain|CC0)', row)
            self.assertTrue((ROOT / 'wnba' / 'owners' / src).is_file(), src)
            self.assertIn(row['source_url'], main, f'no credit in Methods for {src}')

    def test_text_above_table_is_short(self):
        """Ryan (Oct 19, 2026): only a data line, one short intro and at most one key fact above the table."""
        import sys
        sys.path.insert(0, str(ROOT / 'automation'))
        import test_data_table_first as dtf
        m = dtf.MARK.search(self.html)
        row = [x for x in dtf.BYLINE_ROW.finditer(self.html) if x.end() <= m.start()][-1]
        between = self.html[row.end():m.start()]
        text = ' '.join(dtf.TAG.sub(' ', between).split())
        self.assertLessEqual(len(text), 300, text)
        self.assertNotIn('ow-answer', between)
        self.assertNotIn('Ownership reviewed', between)


if __name__ == '__main__':
    unittest.main()

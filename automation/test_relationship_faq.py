"""Dating and married FAQs must agree with the Couples list."""
import html
import json
import re
import unittest
from pathlib import Path

import build_couples
import build_players

ROOT = Path(__file__).resolve().parents[1]
FAQ_ITEM = re.compile(r'<div class="faq-item"><h3>(.*?)</h3><p>(.*?)</p></div>', re.S)

ALLISHA_DATING = (
    'Allisha Gray is engaged to Tim Mangum Jr. The engagement was a surprise proposal '
    'at a staged magazine shoot on March 29, 2025.'
)
ALLISHA_MARRIED = 'No. Allisha Gray is not married. She is engaged to Tim Mangum Jr.'


def _faq_json(slug: str) -> dict:
    return json.loads((ROOT / 'data' / 'wnba' / 'faq' / f'{slug}.json').read_text(encoding='utf-8'))


def _schema_faq(page: str) -> dict[str, str]:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', page)
    if not match:
        return {}
    data = json.loads(match.group(1))
    found = {}
    for node in data.get('@graph') or []:
        if isinstance(node, dict) and node.get('@type') == 'FAQPage':
            for item in node.get('mainEntity') or []:
                found[item['name']] = item['acceptedAnswer']['text']
    return found


class RelationshipFaqTests(unittest.TestCase):
    def test_name_period_is_not_followed_by_another_period(self):
        plain = build_couples.note_html(
            {'a': 'Allisha Gray', 'b': 'Tim Mangum Jr.', 'status': 'Engaged'},
            'Tim Mangum Jr.',
            None,
        )
        self.assertEqual(
            plain,
            '<p class="relationship-note">Engaged to Tim Mangum Jr. '
            '<a href="/wnba/couples/#allisha-gray-tim-mangum-jr">Couples page</a>.</p>',
        )
        self.assertNotIn('Jr..', plain)
        linked = build_couples.note_html(
            {'a': 'Pat Player', 'b': 'Sam Suffix Jr.', 'status': 'Married'},
            'Sam Suffix Jr.',
            'sam-suffix',
        )
        self.assertIn('Married to <a href="/wnba/sam-suffix/">Sam Suffix Jr.</a> ', linked)
        self.assertNotIn('Jr..', linked)
        self.assertIn(
            'Dating Bam Adebayo. ',
            build_couples.note_html(
                {'a': 'A', 'b': 'Bam Adebayo', 'status': 'Dating'},
                'Bam Adebayo',
                None,
            ),
        )
        listed = build_couples.sentence('These marriages are confirmed on this page: Alex Example and Tim Mangum Jr.')
        self.assertEqual(listed, 'These marriages are confirmed on this page: Alex Example and Tim Mangum Jr.')
        self.assertNotIn('Jr..', listed)

    def test_denial_contradicts_a_couples_entry(self):
        reason = build_couples.relationship_faq_conflict(
            'Engaged',
            'Tim Mangum Jr.',
            'Who is Allisha Gray dating?',
            'As of late 2026, Allisha Gray has not widely publicized a confirmed dating relationship in major profiles.',
        )
        self.assertIn('Tim Mangum Jr.', reason)
        self.assertIn('engaged', reason)
        married = build_couples.relationship_faq_conflict(
            'Engaged',
            'Tim Mangum Jr.',
            'Is Allisha Gray married?',
            'There is no widely reported public record of Allisha Gray being married as of late 2026.',
        )
        self.assertIn('engaged', married)
        self.assertEqual(
            build_couples.relationship_faq_conflict(
                'Engaged', 'Tim Mangum Jr.', 'Who is Allisha Gray dating?', ALLISHA_DATING,
            ),
            '',
        )
        self.assertEqual(
            build_couples.relationship_faq_conflict(
                'Engaged', 'Tim Mangum Jr.', 'Is Allisha Gray married?', ALLISHA_MARRIED,
            ),
            '',
        )
        self.assertIn(
            'calls an engagement a marriage',
            build_couples.relationship_faq_conflict(
                'Engaged',
                'Tim Mangum Jr.',
                'Is Allisha Gray married?',
                'Yes. Allisha Gray is married to Tim Mangum Jr.',
            ),
        )

    def test_every_couples_player_faq_agrees_with_the_list(self):
        mapped = build_couples.couples_by_slug(ROOT)
        self.assertGreaterEqual(len(mapped), 15)
        problems = []
        for slug, (partner, couple) in sorted(mapped.items()):
            faq_path = ROOT / 'data' / 'wnba' / 'faq' / f'{slug}.json'
            page_path = ROOT / 'wnba' / slug / 'index.html'
            note = build_couples.note_for_slug(ROOT, slug)
            page = page_path.read_text(encoding='utf-8')
            self.assertIn(note, page, slug)
            self.assertNotIn('Jr..', page, slug)
            self.assertNotIn('Sr..', page, slug)
            if not faq_path.is_file():
                continue
            data = _faq_json(slug)
            visible = {html.unescape(q): html.unescape(a) for q, a in FAQ_ITEM.findall(page)}
            schema = _schema_faq(page)
            profile = {'slug': slug}
            pairs = []
            for item in data['items']:
                question = item['question']
                answer = item['answer']
                pairs.append((question, answer))
                reason = build_couples.relationship_faq_conflict(
                    couple.get('status') or '', partner, question, answer,
                )
                if reason:
                    problems.append(f'{slug}: {question}: {reason}')
                if build_couples.relationship_question_kind(question):
                    self.assertEqual(visible.get(question), answer, slug)
                    self.assertEqual(schema.get(question), answer, slug)
                    self.assertNotIn('Jr..', answer, slug)
            build_players.assert_relationship_faq_matches_couples(slug, pairs, ROOT)
        self.assertEqual(problems, [])

    def test_allisha_gray_page_says_engaged_not_married(self):
        profile = json.loads((ROOT / 'data' / 'wnba' / 'players' / 'allisha-gray.json').read_text(encoding='utf-8'))
        _html, entity = build_players.faq_section(profile, ROOT)
        answers = {node['name']: node['acceptedAnswer']['text'] for node in entity['mainEntity']}
        self.assertEqual(answers['Who is Allisha Gray dating?'], ALLISHA_DATING)
        self.assertEqual(answers['Is Allisha Gray married?'], ALLISHA_MARRIED)
        page = (ROOT / 'wnba' / 'allisha-gray' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(ALLISHA_DATING, page)
        self.assertIn(ALLISHA_MARRIED, page)
        self.assertIn('Engaged to Tim Mangum Jr. ', page)
        self.assertNotIn('Jr..', page)
        self.assertNotIn('not widely publicized a confirmed dating relationship', page)
        self.assertNotIn('no widely reported public record of Allisha Gray being married', page)

    def test_players_without_a_couples_entry_keep_their_wording(self):
        mapped = build_couples.couples_by_slug(ROOT)
        self.assertNotIn('angel-reese', mapped)
        self.assertNotIn('aaliyah-edwards', mapped)
        angel = _faq_json('angel-reese')
        angel_dating = next(item['answer'] for item in angel['items'] if item['question'] == 'Who is Angel Reese dating?')
        self.assertIn('Wendell Carter', angel_dating)
        edwards = _faq_json('aaliyah-edwards')
        dating = next(item['answer'] for item in edwards['items'] if item['question'] == 'Who is Aaliyah Edwards dating?')
        married = next(item['answer'] for item in edwards['items'] if item['question'] == 'Is Aaliyah Edwards married?')
        self.assertIn('has not widely publicized a confirmed dating relationship', dating)
        self.assertIn('no widely reported public record', married)
        megan = _faq_json('megan-dileo')
        questions = [item['question'] for item in megan['items']]
        self.assertFalse(any(build_couples.relationship_question_kind(question) for question in questions))

    def test_built_output_has_no_doubled_name_period(self):
        hits = []
        for path in (ROOT / 'wnba').rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'Jr..' in text or 'Sr..' in text:
                hits.append(path.relative_to(ROOT).as_posix())
        for path in (ROOT / 'data' / 'wnba' / 'faq').glob('*.json'):
            text = path.read_text(encoding='utf-8')
            if 'Jr..' in text or 'Sr..' in text:
                hits.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(hits, [])


if __name__ == '__main__':
    unittest.main()

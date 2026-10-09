"""A full build keeps inactive career heroes and does not rewrite other pages."""
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import apply_portraits
import build_players as players
import career_summary
import rollout_player_design

ROOT = Path(__file__).resolve().parents[1]
TOUCHED = set(players.SEARCH_FAQ_SLUGS) | {'aja-wilson', 'janelle-salaun'}
FAQ_SECTION = re.compile(r'<section class="section" id="faq">.*?</section>', re.S)
SCRIPT = re.compile(r'<script\b[^>]*>.*?</script>', re.S)
STYLE = re.compile(r'<style\b[^>]*>.*?</style>', re.S)
TAG = re.compile(r'<[^>]+>')
HERO = re.compile(r'<p class="answer-summary">(.*?)</p>', re.S)
CAREER = re.compile(r'<section class="section" id="career">.*?</section>', re.S)
REFRESH = re.compile(r'http-equiv=["\']refresh["\']', re.I)


def _plain(fragment: str) -> str:
    text = TAG.sub(' ', fragment or '')
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def _non_faq_text(page: str) -> str:
    page = FAQ_SECTION.sub(' ', page)
    page = SCRIPT.sub(' ', page)
    page = STYLE.sub(' ', page)
    return _plain(page)


def _hero(page: str) -> str:
    match = HERO.search(page)
    return _plain(match.group(1)) if match else ''


def _career(page: str) -> str:
    match = CAREER.search(page)
    return _plain(match.group(0)) if match else ''


def _main_html(relative: str) -> str:
    return subprocess.check_output(
        ['git', 'show', f'origin/main:{relative}'],
        cwd=ROOT,
        text=True,
        errors='replace',
    )


def _window(before: str, after: str) -> str:
    import difflib
    matcher = difflib.SequenceMatcher(a=before, b=after)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        return (
            f'{tag}: main {before[max(0, i1 - 50):i2 + 50]!r} '
            f'built {after[max(0, j1 - 50):j2 + 50]!r}'
        )
    return 'lengths differ'


class InactiveHeroBuildTests(unittest.TestCase):
    def test_answer_summary_keeps_the_curated_hero_when_the_root_is_set(self):
        profile = json.loads((ROOT / 'data/wnba/players/abby-bishop.json').read_text(encoding='utf-8'))
        hero = players.answer_summary(profile, career=True, root=ROOT)
        self.assertEqual(hero, career_summary.hero_plain(profile, ROOT))
        self.assertIn('Olympic basketball for Australia in London in 2012', hero)
        self.assertNotIn('during the regular season', hero)
        bare = players.answer_summary(profile, career=True)
        self.assertNotEqual(bare, hero)

    def test_full_build_keeps_inactive_bios_and_other_page_text(self):
        with tempfile.TemporaryDirectory(prefix='fcb-hero-') as folder:
            copy = Path(folder) / 'site'
            shutil.copytree(
                ROOT,
                copy,
                copy_function=os.link,
                ignore=shutil.ignore_patterns('.git', '__pycache__'),
            )
            players.build(copy)
            apply_portraits.apply(copy)
            rollout_player_design.rollout(copy)
            hero_problems = []
            intro_problems = []
            text_problems = []
            inactive = 0
            compared = 0
            for path in sorted((copy / 'wnba').glob('*/index.html')):
                slug = path.parent.name
                if slug in {'teams', 'assets', 'couples'}:
                    continue
                relative = f'wnba/{slug}/index.html'
                built = path.read_text(encoding='utf-8', errors='replace')
                if REFRESH.search(built):
                    continue
                main = _main_html(relative)
                compared += 1
                if 'Inactive player' in built:
                    inactive += 1
                    profile_path = copy / 'data/wnba/players' / f'{slug}.json'
                    if _hero(built) != _hero(main):
                        hero_problems.append(f'{slug}: built {_hero(built)!r}; main {_hero(main)!r}')
                    elif career_summary.released(copy, slug) and profile_path.is_file():
                        profile = json.loads(profile_path.read_text(encoding='utf-8'))
                        expected = career_summary.hero_plain(profile, copy)
                        if _hero(built) != expected:
                            hero_problems.append(f'{slug}: built {_hero(built)!r}; bio {expected!r}')
                    if _career(built) != _career(main):
                        intro_problems.append(f'{slug}: {_window(_career(main), _career(built))}')
                if slug not in TOUCHED and _non_faq_text(built) != _non_faq_text(main):
                    text_problems.append(f'{slug}: {_window(_non_faq_text(main), _non_faq_text(built))}')
            for path in sorted((copy / 'wnba').glob('teams/*/index.html')):
                relative = f'wnba/teams/{path.parent.name}/index.html'
                built = path.read_text(encoding='utf-8', errors='replace')
                main = _main_html(relative)
                if REFRESH.search(built) or REFRESH.search(main):
                    continue
                compared += 1
                if _non_faq_text(built) != _non_faq_text(main):
                    text_problems.append(f'teams/{path.parent.name}: {_window(_non_faq_text(main), _non_faq_text(built))}')
            directory = (copy / 'wnba/index.html').read_text(encoding='utf-8')
            if _non_faq_text(directory) != _non_faq_text(_main_html('wnba/index.html')):
                text_problems.append('wnba/index.html non-FAQ text changed')
        self.assertGreaterEqual(inactive, 300)
        self.assertGreaterEqual(compared, 500)
        self.assertEqual(hero_problems, [])
        self.assertEqual(intro_problems, [])
        self.assertEqual(text_problems, [])

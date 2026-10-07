"""Fail when a tracked file or built page still contains a git conflict marker.

The publisher runs this with the rest of the site tests before it deploys,
and again on the Pages artifact after pages are generated.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from link_graph import iter_html

ROOT = Path(__file__).resolve().parents[1]
OURS = '<' * 7
THEIRS = '>' * 7
SEPARATOR = '=' * 7
BINARY_SUFFIXES = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.ico', '.bmp',
    '.woff', '.woff2', '.ttf', '.otf', '.eot', '.mp4', '.webm', '.pdf',
    '.zip', '.gz', '.br', '.wasm',
}


def is_conflict_marker(line: str) -> bool:
    """True for a conflict start, end, or a line that is only the separator."""
    text = line.strip()
    if len(text) >= len(SEPARATOR) and set(text) == {'='}:
        return True
    return text.startswith(OURS) or text.startswith(THEIRS)


def marker_lines(text: str) -> list[tuple[int, str]]:
    return [
        (number, line)
        for number, line in enumerate(text.splitlines(), 1)
        if is_conflict_marker(line)
    ]


def _tracked_files(root: Path) -> list[Path] | None:
    """Paths git tracks at this checkout, or None when root is not its own repo."""
    try:
        top = subprocess.check_output(
            ['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if Path(top).resolve() != root.resolve():
        return None
    listed = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z'])
    return [root / name.decode() for name in listed.split(b'\0') if name]


def _readable_text(path: Path) -> str | None:
    if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file() or path.is_symlink():
        return None
    data = path.read_bytes()
    if b'\0' in data:
        return None
    return data.decode('utf-8', errors='replace')


def files_to_scan(root: Path) -> list[Path]:
    """Tracked files when root is a git checkout, plus built HTML pages.

    A generated site directory is not a git checkout. Every text file there
    is part of the published build, so those are scanned too.
    """
    root = root.resolve()
    tracked = _tracked_files(root)
    if tracked is None:
        paths = [path for path in root.rglob('*') if path.is_file() and not path.is_symlink()]
    else:
        paths = list(tracked)
        seen = {path.resolve() for path in paths}
        for page in iter_html(root):
            if page.resolve() not in seen:
                paths.append(page)
    return paths


def scan(root: Path) -> list[str]:
    offenders = []
    for path in files_to_scan(root):
        text = _readable_text(path)
        if text is None:
            continue
        for number, line in marker_lines(text):
            relative = path.resolve().relative_to(root.resolve()).as_posix()
            offenders.append(f'{relative}:{number}:{line.strip()}')
    return offenders


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv] or [ROOT]
    offenders = []
    for root in roots:
        offenders.extend(scan(root))
    if offenders:
        print('Git conflict markers are still in the site:', file=sys.stderr)
        print('\n'.join(offenders), file=sys.stderr)
        return 1
    print(f'No git conflict markers under {", ".join(str(root) for root in roots)}.')
    return 0


class NoConflictMarkerTests(unittest.TestCase):
    def test_marker_lines_are_detected_and_ordinary_equals_are_not(self):
        text = '\n'.join([
            'article copy',
            OURS + ' ours',
            'kept',
            SEPARATOR,
            'other',
            THEIRS + ' theirs',
            'width: ' + SEPARATOR + 'px',
            'a row of equals in a sentence ' + SEPARATOR,
        ])
        hits = [line for _, line in marker_lines(text)]
        self.assertEqual(hits, [OURS + ' ours', SEPARATOR, THEIRS + ' theirs'])

    def test_tracked_files_and_built_pages_have_no_conflict_markers(self):
        self.assertEqual(scan(ROOT), [])

    def test_a_built_tree_with_a_marker_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = root / 'news' / 'example' / 'index.html'
            page.parent.mkdir(parents=True)
            page.write_text('</article>\n' + THEIRS + ' deadbeef (note)\n</main>\n', encoding='utf-8')
            (root / 'ok.html').write_text('<p>fine</p>\n', encoding='utf-8')
            offenders = scan(root)
        self.assertEqual(len(offenders), 1)
        self.assertIn('news/example/index.html:2:', offenders[0])

    def test_college_cards_article_keeps_its_copy_without_the_marker(self):
        page = ROOT / 'news' / 'top-10-womens-college-basketball-cards-to-collect-2026' / 'index.html'
        text = page.read_text(encoding='utf-8')
        self.assertNotIn(THEIRS, text)
        self.assertNotIn(OURS, text)
        self.assertIn('How this was made', text)
        self.assertIn('Photo shows an ungraded copy of the same card.', text)
        self.assertIn('Photo shows a graded copy of the same card.', text)

    def test_publisher_rejects_markers_before_deploy(self):
        workflow = (ROOT / '.github' / 'workflows' / 'fcb-wnba.yml').read_text(encoding='utf-8')
        self.assertIn("python -m unittest discover -s automation -p 'test_*.py'", workflow)
        self.assertIn('automation/test_no_conflict_markers.py', workflow)
        self.assertLess(
            workflow.index('automation/test_no_conflict_markers.py'),
            workflow.index('actions/deploy-pages@v4'),
        )
        self.assertLess(
            workflow.rindex('automation/test_no_conflict_markers.py'),
            workflow.index('actions/upload-pages-artifact@v3'),
        )
        gate = (ROOT / '.github' / 'workflows' / 'conflict-markers.yml').read_text(encoding='utf-8')
        self.assertIn('pull_request:', gate)
        self.assertIn('test_no_conflict_markers.py', gate)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

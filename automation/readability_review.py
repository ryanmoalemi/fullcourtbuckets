#!/usr/bin/env python3
"""Readability review for FCB articles with OpenAI + Gemini (docs/READABILITY_REVIEW.md).

Keys come only from the environment (OPENAI_API_KEY, GEMINI_API_KEY). They are
never written anywhere. Run this on the box, not in GitHub Actions.

usage: readability_review.py content/articles/<slug>/article.md [--apply] [--report out.md]
"""
import argparse, collections, json, os, re, sys, urllib.request, urllib.error
from pathlib import Path

OPENAI_MODEL = os.environ.get('FCB_OPENAI_MODEL', 'gpt-5.5')
GEMINI_MODEL = os.environ.get('FCB_GEMINI_MODEL', 'gemini-2.5-pro')
STYLE = Path(__file__).resolve().parents[1] / 'docs' / 'EDITORIAL_STYLE.md'

PROMPT = """You are a copy editor for Full Court Buckets, a WNBA site. Suggest READABILITY edits only.
Allowed: a clearer headline (sentence case, lead with the result or the key number, no clickbait question),
simpler sentences, smoother flow, one or two natural sentences introducing each table, cutting jargon and filler.
Methods/source notes belong in the caption line directly below a table, not in the story text.
Forbidden: changing, adding or removing any number, name, team, quote, date, stat or link; adding any fact,
reaction, motivation or opinion; touching markdown table rows, quoted speech, or link URLs.
Each "original" must be copied EXACTLY (character for character) from the article and be one sentence or a
short passage; "suggested" replaces it. Use original "TITLE" to suggest a new headline. Max 12 edits, only
ones that clearly help.
If you believe something is factually WRONG (a stat, date, name, score, record), do NOT put it in edits. List it
in "factual_flags" instead, with the exact original text, your suggested fix, and why. These are never applied
automatically; a human checks each one against a primary source.
Return JSON {"edits":[{"original":..., "suggested":..., "reason":...}],
"factual_flags":[{"original":..., "suggested":..., "reason":...}]}.
Style guide excerpt:
"""
_ITEM = {"type": "array", "items": {"type": "object", "additionalProperties": False,
    "required": ["original", "suggested", "reason"], "properties": {
        "original": {"type": "string"}, "suggested": {"type": "string"}, "reason": {"type": "string"}}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["edits", "factual_flags"],
          "properties": {"edits": _ITEM, "factual_flags": _ITEM}}
FLAGS = []  # factual corrections proposed by a model: reported, never auto-applied
BANNED = ("Here's the wild part", "The wild part?", "Like really", "Game over.", "felt like the moment", "was nuts")
USAGE = []


def post(url, body, headers):
    req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json', **headers})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def ask_openai(text):
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('OPENAI_API_KEY not set')
    d = post('https://api.openai.com/v1/responses', {
        'model': OPENAI_MODEL, 'input': [{'role': 'system', 'content': PROMPT + style_excerpt()},
                                         {'role': 'user', 'content': text}],
        'text': {'format': {'type': 'json_schema', 'name': 'edits', 'schema': SCHEMA, 'strict': True}}},
        {'Authorization': 'Bearer ' + key})
    u = d.get('usage', {}); USAGE.append(('openai', OPENAI_MODEL, u.get('input_tokens', 0), u.get('output_tokens', 0)))
    out = ''.join(c.get('text', '') for o in d.get('output', []) if o.get('type') == 'message' for c in o['content'])
    j = json.loads(out); FLAGS.extend(dict(f, model='openai') for f in j.get('factual_flags', []))
    return j['edits']


def ask_gemini(text):
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('GEMINI_API_KEY not set')
    d = post(f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent', {
        'systemInstruction': {'parts': [{'text': PROMPT + style_excerpt()}]},
        'contents': [{'role': 'user', 'parts': [{'text': text}]}],
        'generationConfig': {'responseMimeType': 'application/json'}}, {'x-goog-api-key': key})
    u = d.get('usageMetadata', {}); USAGE.append(('gemini', GEMINI_MODEL, u.get('promptTokenCount', 0), u.get('candidatesTokenCount', 0)))
    j = json.loads(d['candidates'][0]['content']['parts'][0]['text'])
    FLAGS.extend(dict(f, model='gemini') for f in j.get('factual_flags', []))
    return j.get('edits', [])


def style_excerpt():
    t = STYLE.read_text() if STYLE.exists() else ''
    m = re.search(r'## Headlines and openings.*?(?=\n## Claims)', t, re.S)
    return m.group(0) if m else ''


# ---- fact-preservation checks ----
NUM = re.compile(r'\d[\d,.]*\d|\d')
LINK = re.compile(r'\]\(([^)]+)\)|https?://\S+')
QUOTE = re.compile(r'["\u201c]([^"\u201d]{3,})["\u201d]')
NOTE_START = re.compile(r'^\s*(Data through|Source:|Methods:|Download)')
SUPERLATIVE = re.compile(r'\b(\w+est|most|least|only|first|last|record|every|all|never|no)\b', re.I)
CAP = re.compile(r"\b[A-Z][a-zA-Z'\u2019.-]+")


def facts(s):
    caps = set()
    for sent in re.split(r'(?<=[.!?:])\s+|\n', s):
        words = CAP.findall(sent)
        first = sent.lstrip('*#- "[').split(' ')[0] if sent.strip() else ''
        caps |= {w.rstrip('.') for w in words if w != first}
    return (collections.Counter(NUM.findall(s)), collections.Counter(LINK.findall(s)),
            collections.Counter(QUOTE.findall(s)), caps)


def check(edit, body):
    o, s = edit['original'], edit['suggested']
    if o == 'TITLE':
        return None
    if not o.strip() or o == s:
        return 'empty or no-op'
    if body.count(o) != 1:
        return 'original not found exactly once in the article'
    if '|' in o:
        return 'touches a table row'
    if re.sub(r'[*_`]', '', o) == re.sub(r'[*_`]', '', s):
        return 'formatting only (captions are styled by the builder)'
    if NOTE_START.match(o):
        return 'touches a data/methods note'
    sup = SUPERLATIVE.findall(o)
    if collections.Counter(sup) != collections.Counter(SUPERLATIVE.findall(s)):
        return 'changes a superlative or qualifier claim'
    fo, fs = facts(o), facts(s)
    if fo[0] != fs[0]:
        return f'numbers changed {dict(fo[0] - fs[0])} -> {dict(fs[0] - fo[0])}'
    if fo[1] != fs[1]:
        return 'links changed'
    if fo[2] != fs[2]:
        return 'quote changed'
    lost = {w for w in fo[3] if w.lower() not in s.lower()}
    added = {w for w in fs[3] if w.lower() not in o.lower()}
    if lost or added:
        return f'proper nouns changed (lost {sorted(lost)}, added {sorted(added)})'
    if any(b.lower() in s.lower() for b in BANNED):
        return 'banned filler phrase'
    return None


def check_title(old, new):
    fo, fs = facts(old), facts(new)
    if fo[0] != fs[0]:
        return 'headline numbers changed'
    if {w.lower() for w in fs[3]} - {w.lower() for w in CAP.findall(old)}:
        return 'headline adds a proper noun'
    words = new.split()
    if sum(w[:1].isupper() for w in words[1:]) > len(fs[3]) + 2 and new.istitle():
        return 'not sentence case'
    if new.rstrip().endswith('?'):
        return 'question headline'
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('article'); ap.add_argument('--apply', action='store_true')
    ap.add_argument('--report'); ap.add_argument('--models', default='openai,gemini')
    a = ap.parse_args()
    path = Path(a.article); src = path.read_text()
    m = re.match(r'---\n(.*?)\n---\n', src, re.S)
    front, body = (m.group(1), src[m.end():]) if m else ('', src)
    tm = re.search(r'^title: "(.*)"$', front, re.M); title = tm.group(1) if tm else ''
    text = f'TITLE: {title}\n\n{body}'
    # Sequential pass (default): OpenAI edits first, then Gemini reviews the
    # OpenAI-edited text. Each pass's edits go through the same safety checks.
    accepted, rejected, new_body, new_title = [], [], body, title
    order = [n for n in ('openai', 'gemini') if n in a.models.split(',')]
    for name in order:
        fn = {'openai': ask_openai, 'gemini': ask_gemini}[name]
        try:
            raw = [dict(e, model=name) for e in fn(f'TITLE: {new_title}\n\n{new_body}')]
        except Exception as ex:  # noqa: keep running with the other model
            msg = ex.read().decode()[:200] if isinstance(ex, urllib.error.HTTPError) else str(ex)
            print(f'{name} failed: {msg}', file=sys.stderr)
            continue
        pass_ok, pass_title = [], new_title
        for e in raw:
            e['models'] = [name]
            if e['original'].startswith('TITLE'):
                e['original'] = 'TITLE'
                e['suggested'] = re.sub(r'^TITLE:\s*', '', e['suggested'])
                why = check_title(pass_title, e['suggested']) if new_title == pass_title else 'second headline suggestion'
            else:
                why = check(e, new_body)
                if not why and any(e['original'] in x['original'] or x['original'] in e['original'] for x in pass_ok):
                    why = 'overlaps an accepted edit'
            if why:
                rejected.append((e, why)); continue
            e['before_title'] = new_title
            pass_ok.append(e); accepted.append(e)
            if e['original'] == 'TITLE':
                new_title = e['suggested']
            else:
                new_body = new_body.replace(e['original'], e['suggested'], 1)
    cost = {'openai': (1.25, 10.0), 'gemini': (1.25, 10.0)}  # USD per 1M tokens in/out, rough
    usd = sum(i * cost[p][0] / 1e6 + o * cost[p][1] / 1e6 for p, _, i, o in USAGE)
    lines = [f'# Readability review: {path.parent.name}', '',
             'Models: ' + ', '.join(f'{p} {mdl} ({i} in / {o} out tokens)' for p, mdl, i, o in USAGE),
             f'Approx. cost: ${usd:.3f}', f'Accepted {len(accepted)}, rejected {len(rejected)}', '', '## Accepted', '']
    for e in accepted:
        lines += [f"- **{'/'.join(e['models'])}**: {e['reason']}", f"  - Before: {e.get('before_title', title) if e['original']=='TITLE' else e['original']}",
                  f"  - After: {e['suggested']}", '']
    lines += ['## Needs fact-check (not applied; verify each against a primary source)', '']
    for f in FLAGS:
        lines += [f"- **{f['model']}**: {f['reason']}", f"  - Text: {f['original']}", f"  - Suggested fix: {f['suggested']}", '']
    if not FLAGS:
        lines += ['- None', '']
    lines += ['## Rejected', '']
    for e, why in rejected:
        lines += [f"- **{'/'.join(e['models'])}** ({why}): {e['reason']}", f"  - Before: {e['original']}", f"  - After: {e['suggested']}", '']
    report = '\n'.join(lines)
    if a.report:
        Path(a.report).write_text(report)
    print(report)
    if a.apply and accepted:
        if new_title != title:
            front = front.replace(f'title: "{title}"', 'title: ' + json.dumps(new_title), 1)
        path.write_text(f'---\n{front}\n---\n{new_body}' if m else new_body)


if __name__ == '__main__':
    main()

# Readability review (GPT, then Gemini), required before publish

Approved by Ryan, Oct 27, 2026. Every article's final draft goes through GPT, then Gemini, before publish; recaps and articles that get later edits can run it too.

```
python3 /workspace/fcb-review/review.py content/articles/<slug>/article.md --apply --report /workspace/fcb-review/<slug>-report.md
```

- Runs on the Grok Bot box only. It reads `OPENAI_API_KEY` and `GEMINI_API_KEY` from the environment. Keys are never written to files, the repo or GitHub Actions secrets.
- `automation/readability_review.py` is the same logic, kept in the repo for review. Models: `FCB_OPENAI_MODEL` (default `gpt-5.5`) and `FCB_GEMINI_MODEL` (default `gemini-2.5-pro`). `--models openai` runs one model.
- Sequential by default: GPT (OpenAI) edits first, then Gemini reviews the GPT-edited text. Each pass's edits go through the safety checks below before the next pass starts.
- Both models get the article and an editor prompt that allows readability edits only (clearer sentence-case headline, simpler sentences, flow, table lead-ins, cutting filler) and forbids changing any number, name, quote, date, stat or link, or adding a fact.
- Suggestions come back as JSON `{original, suggested, reason}`. The script rejects any edit that changes a number, link, quote, proper noun or superlative (best/most/only/every/record...), touches a table row or a Data/Source/Methods note, is formatting-only, uses a banned filler phrase, or whose original text isn't found exactly once. A headline edit must keep its numbers, add no proper noun and not be a question.
- Accepted edits are applied to `article.md` and a before/after markdown report is written. Read the report, then run the normal checks (`python3 -m unittest automation/test_editorial_style.py`) and publish. Readability edits are pre-approved.
- Cost is about $0.05-0.10 per article per model.

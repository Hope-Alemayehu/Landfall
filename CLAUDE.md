# Landfall

## Commits
- Never add `Co-Authored-By` or any other attribution lines to commit messages in this repo.
- Do not commit or push unless asked; the maintainer reviews and commits.

## Constraints
- Qollab picks the project type from top-level files: keep `main.py` at the root and never add a top-level
  `index.html` or `main.js` (the website lives in `public/`).
- Keep `main()` in `main.py` on one line with only int/float/str/bool annotations; Qollab builds its run
  settings from that signature.
- `requirements.txt` is Qollab's (installed in the browser); website dependencies go in `pyproject.toml`.
- Analysis numbers must not change unintentionally: rerun the five presets and compare the JSON reports.
- No em dash characters in any file or UI text.

## Commands
- Tests: `python -m pytest tests`
- Website locally: `python scripts/dev_server.py`, then open http://127.0.0.1:8000
- After changing the analysis: `python scripts/export_example.py` (refreshes `public/data/adder.json`)

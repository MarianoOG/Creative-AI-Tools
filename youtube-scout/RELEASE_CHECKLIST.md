# Release checklist

Go through every item before tagging a release. A feature that breaks a hard
constraint is removed, not documented.

## Automated

- [ ] `pytest` passes (fixtures only; no network)
- [ ] `python scripts/guard.py --tracked` passes (no keys, emails or local data tracked)
- [ ] `pre-commit run --all-files` passes (gitleaks + guard)

## Hard constraints

1. **Open-source the system only, never data**
   - [ ] `git ls-files youtube-scout` lists no `brand.txt`, `keywords.generated.txt`,
         `config.toml`, `.env`, `out/`, `state/`, `cache/` or exclude list
   - [ ] Test fixtures are synthetic, not recorded third-party data
   - [ ] No sample outputs, notes or datasets in the README, issues or release assets
2. **No email collection, no contact scraping**
   - [ ] No code reads or extracts emails, links, social handles or "about" contact fields
   - [ ] Output fields are exactly: title, URL, subscriber count, video count,
         last upload, recent titles, fit reason, discovery path
3. **Official YouTube Data API only**
   - [ ] Every request goes through `youtube.HttpTransport` to `googleapis.com/youtube/v3`
   - [ ] Only the methods in `youtube.COSTS`; no HTML pages, no internal/suggest endpoints
4. **No published scores or rankings**
   - [ ] No numeric fit, score or rank field in the output or summary
5. **No API keys in the repo**
   - [ ] Keys only from env vars / `.env`; `.env.example` has empty values
   - [ ] A missing key exits with a message naming the variable (`tests/test_cli.py`)
6. **Read-only**
   - [ ] Only `GET` requests; no OAuth scopes; no write methods (insert/update/delete/rate)
7. **Retention and sensitive data**
   - [ ] Dated outputs and state are purged after `retention_days` (≤ 30)
   - [ ] No raw API responses are written
   - [ ] Comment text, commenter ids and author names are never written
         (`tests/test_comments.py`, `tests/test_pipeline.py`)
   - [ ] Nothing about made-for-kids or minor-looking channels is written beyond a count
8. **README**
   - [ ] States that it uses YouTube API Services
   - [ ] Links the YouTube Terms of Service and the Google Privacy Policy
   - [ ] Explains the data handling above and is in sync with the code

## Engineering

- [ ] Quota stop is at most 80% of the daily quota; per-method usage is logged
- [ ] Re-running a finished day makes no API or LLM calls; a crashed run resumes
- [ ] Version bumped in `pyproject.toml` and `youtube_scout/__init__.py`

# Vietnamese financial news crawler → JSON

Collects financial news about Vietnam from RSS feeds, extracts article bodies,
splits them into sentences, stores everything in SQLite and exports JSON for the
aspect-based sentiment model.

Two English sources are enabled. The full list of 13 sources (including 11
Vietnamese ones) is in `doc/nguon-du-lieu.md`.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```bash
./absa crawl                      # fetch new articles
./absa stats                      # show what is in the database
./absa export --day 2026-11-19    # write JSON
./absa --help                     # all options
```

The first run takes everything currently in the feeds. Later runs only pick up
new articles, deduplicated by URL.

Run hourly — the narrowest feed only covers about 31 hours, so running less
often loses articles permanently:

```cron
0 * * * * cd /path/to/aspect-based-FSA && ./absa crawl >> data/crawl.log 2>&1
```

## Output

One file per article, `<doc_id>.json` under `data/exports/<day>/`, holding an
array of sentences:

```json
[
  {
    "sent_id": "vietnamnews_20261118_57f513e3f5#0",
    "doc_id": "vietnamnews_20261118_57f513e3f5",
    "sent_idx": 0,
    "text": "Cà Mau producers step up efforts to meet HCM City market demands",
    "lang": "en",
    "is_title": true
  }
]
```

`sent_id` is `<doc_id>#<sent_idx>`. `sent_idx = 0` is the article title.

A sample export for 2026-11-19 (34 articles, 839 sentences) is committed under
`data/exports/`.

## Layout

```
src/absa_fsa/
  config.py     source registry and .env-based settings
  fetch.py      HTTP layer: robots.txt, 1s per-domain rate limit, retries
  feeds.py      RSS/Atom parsing, tolerant dates, future-timestamp clamping
  extract.py    HTML to title and body (one generic algorithm for all sites)
  textnorm.py   text normalisation and sentence splitting
  db.py         SQLite: articles, sentences, crawl_runs
  pipeline.py   wiring plus JSON export
  cli.py        command line
```

## Notes

- **Offsets are computed on normalised text.** `normalize()` runs once, before
  sentence splitting. Do not normalise again afterwards or the model's target
  spans will be off by a few characters.
- The SQLite database is not committed: it is a binary file that changes on
  every crawl. Rebuild it with `./absa crawl`.
- Python 3.14 is fine for the crawler. Adding the model or machine translation
  will need 3.12, since torch and transformers do not support 3.14 yet.

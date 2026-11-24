# Aspect-based financial sentiment for Vietnam news

Extracts (target, aspect, sentiment) triplets from financial news about Vietnam and shows
how sentiment moves over time. This repo holds the data pipeline (crawl news, split into
sentences, export JSON for the model) and a web dashboard.

The model is built by another team and is not integrated yet, so the dashboard currently
runs on generated sample data.

```
RSS / sitemap → crawl → SQLite → JSON → model → triplets → API → dashboard
```

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

./absa crawl                    # fetch new articles
./absa backfill --days 30       # fetch past days through sitemaps
./absa export --day 2026-11-19  # write sentences as JSON
./absa mock                     # generate sample data for the dashboard
./absa serve                    # dashboard at http://127.0.0.1:8002/
```

`./absa --help` lists everything. Run `crawl` hourly, since the feeds only keep the latest
articles.

## Data for the model

`data/exports/<day>/<doc_id>.json`, one file per article, an array of sentences:

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

`sent_id` is `<doc_id>#<sent_idx>`; `sent_idx = 0` is the title.

## Layout

```
src/absa_fsa/   crawler, database, API, sample data generator
web/            dashboard (plain HTML/JS)
doc/            proposal, meeting notes, source list
data/           database and exports
```

## Notes

- Target offsets are computed on normalised text. Normalising it again shifts every span.
- `data/mock.db` is sample data from keyword rules, not model output. Use it to try the UI only.

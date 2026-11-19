"""Dòng lệnh: crawl | export | stats"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import config, db, pipeline


def _log(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def cmd_crawl(args) -> int:
    srcs = config.SOURCES
    if args.source:
        srcs = [s for s in srcs if s.slug in args.source]
        if not srcs:
            print(f"Không có nguồn nào khớp {args.source}", file=sys.stderr)
            print("Nguồn có sẵn:", ", ".join(s.slug for s in config.SOURCES), file=sys.stderr)
            return 1

    print(f"Crawl {len(srcs)} nguồn: {', '.join(s.slug for s in srcs)}\n")
    r = pipeline.crawl(srcs, limit=args.limit)
    print(f"\n{'─'*52}")
    print(f"  Chế độ      : {'backfill (lần đầu)' if r['is_backfill'] else 'incremental'}")
    print(f"  Bài trong feed: {r['feed_items']}")
    print(f"  Bài mới     : {r['new']}")
    print(f"  Bỏ qua (đã có): {r['skipped']}")
    print(f"  Lỗi         : {r['failed']}")
    print(f"  Câu thu được: {r['sentences']}")
    print(f"{'─'*52}")
    return 0


def cmd_export(args) -> int:
    r = pipeline.export_jsonl(day=args.day, split_by_article=not args.single)
    print(f"Đã xuất vào {r['dir']}")
    if args.single:
        print(f"  sentences.jsonl: {r['sentences']} câu của {r['articles']} bài")
    else:
        print(f"  {r['files']} file .json (mỗi bài 1 file), tổng {r['sentences']} câu")
    return 0


def cmd_stats(args) -> int:
    with db.session() as conn:
        s = db.stats(conn)
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0

    print(f"Bài : {s['articles']}")
    print(f"Câu : {s['sentences']}")
    if s["by_source"]:
        print(f"\n{'nguồn':<16}{'lang':<6}{'bài':>6}{'backfill':>10}   mới nhất")
        print("─" * 72)
        for r in s["by_source"]:
            print(f"{r['source']:<16}{r['lang']:<6}{r['n']:>6}{r['backfill'] or 0:>10}   {(r['newest'] or '')[:19]}")
    if s["runs"]:
        print(f"\n{'run':>4}  {'bắt đầu':<20}{'mới':>5}{'bỏ qua':>8}{'lỗi':>6}{'câu':>7}  ghi chú")
        print("─" * 72)
        for r in s["runs"]:
            print(f"{r['run_id']:>4}  {r['started_at'][:19]:<20}{r['n_new']:>5}"
                  f"{r['n_skipped']:>8}{r['n_failed']:>6}{r['n_sentences']:>7}  {r['note'] or ''}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="absa", description="Crawl tin tài chính -> JSON")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("crawl", help="Crawl feed, lưu vào DB")
    c.add_argument("--source", action="append", help="chỉ crawl slug này (lặp được)")
    c.add_argument("--limit", type=int, default=0, help="tối đa N bài mới mỗi nguồn (0 = không giới hạn)")
    c.set_defaults(func=cmd_crawl)

    e = sub.add_parser("export", help="Xuất JSONL")
    e.add_argument("--day", help="YYYY-MM-DD theo giờ VN; bỏ trống = xuất tất cả")
    e.add_argument("--single", action="store_true",
                   help="gộp vào 1 file sentences.jsonl thay vì mỗi bài 1 file")
    e.set_defaults(func=cmd_export)

    s = sub.add_parser("stats", help="Thống kê trong DB")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_stats)

    args = ap.parse_args(argv)
    _log(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

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


def cmd_serve(args) -> int:
    import uvicorn
    from pathlib import Path
    from .api import create_app
    db_path = Path(args.db) if args.db else config.WEB_DB_PATH

    # Kiểm tra cổng TRƯỚC khi in địa chỉ, để không báo "đang chạy" khi thật ra không bind được.
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((args.host, args.port))
        except OSError as e:
            print(f"Cổng {args.port} đang được chương trình khác dùng ({e.strerror}).\n"
                  f"Chọn cổng khác, ví dụ: ./absa serve --port {args.port + 1}", file=sys.stderr)
            return 1

    print(f"Đọc {db_path}")
    print(f"  Giao diện : http://{args.host}:{args.port}/")
    print(f"  API docs  : http://{args.host}:{args.port}/docs")
    uvicorn.run(create_app(db_path), host=args.host, port=args.port, log_level="info")
    return 0


def cmd_mock(args) -> int:
    from . import mock
    r = mock.build(days=args.days, seed=args.seed)
    real_a, real_b = r["real_range"]
    print(f"Đã ghi {config.MOCK_DB_PATH}\n")
    print("DỮ LIỆU MẪU — nhãn do luật từ khóa gán, KHÔNG phải kết quả model.\n")
    print(f"  Bài        : {r['articles']}  (thật {r['articles_real']}, bản sao ngày giả {r['articles'] - r['articles_real']})")
    print(f"  Ngày thật  : {real_a} → {real_b}; các ngày trước đó là ngày giả")
    print(f"  Câu        : {r['sentences']}")
    n = r["triplets"]
    sw = r["sent_with_triplet"]
    print(f"  Bộ ba      : {n}  trên {sw} câu ({100 * sw / r['sentences']:.1f}% câu có bộ ba)")
    print(f"  Câu >=2 bộ ba: {r['sent_multi']}   | có cảm xúc ngược nhau: {r['sent_conflict']}")
    sc = r["by_sentiment"]
    print(f"  Cảm xúc    : " + ", ".join(f"{k} {sc.get(k, 0)}" for k in ("positive", "negative", "neutral")))
    print("\n  Top mục tiêu: " + ", ".join(f"{k} {v}" for k, v in r["top_targets"]))
    print("\n  Theo khía cạnh:")
    for k, v in r["by_aspect"]:
        print(f"    {k:<34}{v:>5}")
    print(f"\n  {'ngày':<12}{'bài':>5}{'bộ ba':>7}")
    for d in r["days"]:
        tag = "" if real_a <= d["day"] <= real_b else "  (giả)"
        print(f"  {d['day']:<12}{d['articles']:>5}{d['triplets']:>7}{tag}")
    e = r["errors"]
    print(f"\n  Kiểm tra: span lệch {e['span_lệch']}, aspect sai {e['aspect_sai']}, mồ côi {e['mồ_côi']}")
    return 0 if not any(e.values()) else 1


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

    m = sub.add_parser("mock", help="Sinh DB dữ liệu mẫu (data/mock.db) để thử giao diện")
    m.add_argument("--days", type=int, default=30, help="số ngày dữ liệu mẫu (mặc định 30)")
    m.add_argument("--seed", type=int, default=7, help="hạt giống ngẫu nhiên, cùng seed ra cùng dữ liệu")
    m.set_defaults(func=cmd_mock)

    sv = sub.add_parser("serve", help="Chạy API (và web)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8002)
    sv.add_argument("--db", help="DB để đọc; mặc định theo ABSA_WEB_DB (data/mock.db)")
    sv.set_defaults(func=cmd_serve)

    args = ap.parse_args(argv)
    _log(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

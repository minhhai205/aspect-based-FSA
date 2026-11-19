# Crawl tin tài chính → JSON

Thu thập tin tài chính về Việt Nam từ RSS, tách câu, lưu SQLite, xuất JSON cho model.

Hiện bật 2 nguồn tiếng Anh. Danh sách 13 nguồn (gồm 11 tiếng Việt) ở `doc/nguon-du-lieu.md`.

## Cài đặt

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Dùng

```bash
./absa crawl                      # crawl bài mới
./absa stats                      # xem đã có gì trong DB
./absa export --day 2026-11-19    # xuất JSON
./absa --help                     # xem hết tùy chọn
```

Lần chạy đầu lấy hết bài đang có trong feed. Các lần sau chỉ lấy bài mới,
khử trùng lặp theo URL.

Chạy định kỳ mỗi giờ (feed hẹp nhất chỉ phủ ~31 giờ, chạy thưa hơn là mất bài):

```cron
0 * * * * cd /đường/dẫn/aspect-based-FSA && ./absa crawl >> data/crawl.log 2>&1
```

## Đầu ra

Mỗi bài một file `<doc_id>.json` trong `data/exports/<ngày>/` — mảng câu:

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

`sent_id` = `<doc_id>#<sent_idx>`. `sent_idx = 0` là tiêu đề bài.

## Cấu trúc

```
src/absa_fsa/
  config.py     danh sách nguồn + cấu hình từ .env
  fetch.py      HTTP: robots.txt, giãn nhịp 1s/tên miền, thử lại
  feeds.py      đọc RSS/Atom, xử lý ngày lệch chuẩn và mốc tương lai
  extract.py    HTML → tiêu đề + thân bài (thuật toán chung cho mọi báo)
  textnorm.py   chuẩn hóa chữ + tách câu
  db.py         SQLite: articles, sentences, crawl_runs
  pipeline.py   ghép các bước + xuất JSON
  cli.py        dòng lệnh
```

## Lưu ý

- **Offset tính trên text đã chuẩn hóa.** `normalize()` chạy một lần trước khi tách câu.
  Không chuẩn hóa lại sau đó, nếu không span của model sẽ lệch.
- Python 3.14 chạy tốt cho crawler. Khi nào thêm model/dịch máy thì cần 3.12
  (torch/transformers chưa hỗ trợ 3.14).

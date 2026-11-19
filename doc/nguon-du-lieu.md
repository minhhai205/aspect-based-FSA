# Nguồn crawl

13 feed RSS: 2 tiếng Anh, 11 tiếng Việt.

## Tiếng Anh (2)

| Nguồn              | Feed                                     |
| ------------------ | ---------------------------------------- |
| VnEconomy English  | `https://en.vneconomy.vn/economy.rss`    |
| Vietnam News (VNA) | `https://vietnamnews.vn/rss/economy.rss` |

## Tiếng Việt (11)

| Nguồn                       | Feed                                                |
| --------------------------- | --------------------------------------------------- |
| CafeF – Chứng khoán         | `https://cafef.vn/thi-truong-chung-khoan.rss`       |
| CafeF – Doanh nghiệp        | `https://cafef.vn/doanh-nghiep.rss`                 |
| CafeF – Tài chính ngân hàng | `https://cafef.vn/tai-chinh-ngan-hang.rss`          |
| CafeF – Vĩ mô đầu tư        | `https://cafef.vn/vi-mo-dau-tu.rss`                 |
| VnEconomy – Chứng khoán     | `https://vneconomy.vn/chung-khoan.rss`              |
| VnEconomy – Tài chính       | `https://vneconomy.vn/tai-chinh.rss`                |
| Vietstock – Cổ phiếu        | `https://vietstock.vn/830/chung-khoan/co-phieu.rss` |
| VnExpress – Kinh doanh      | `https://vnexpress.net/rss/kinh-doanh.rss`          |
| Dân trí – Kinh doanh        | `https://dantri.com.vn/rss/kinh-doanh.rss`          |
| Thanh Niên – Kinh tế        | `https://thanhnien.vn/rss/kinh-te.rss`              |
| Tuổi Trẻ – Kinh doanh       | `https://tuoitre.vn/rss/kinh-doanh.rss`             |

## Danh sách cho code

```
en  https://en.vneconomy.vn/economy.rss
en  https://vietnamnews.vn/rss/economy.rss
vi  https://cafef.vn/thi-truong-chung-khoan.rss
vi  https://cafef.vn/doanh-nghiep.rss
vi  https://cafef.vn/tai-chinh-ngan-hang.rss
vi  https://cafef.vn/vi-mo-dau-tu.rss
vi  https://vneconomy.vn/chung-khoan.rss
vi  https://vneconomy.vn/tai-chinh.rss
vi  https://vietstock.vn/830/chung-khoan/co-phieu.rss
vi  https://vnexpress.net/rss/kinh-doanh.rss
vi  https://dantri.com.vn/rss/kinh-doanh.rss
vi  https://thanhnien.vn/rss/kinh-te.rss
vi  https://tuoitre.vn/rss/kinh-doanh.rss
```

## Lưu ý khi xử lý

- **Thanh Niên** — feed trả HTML entity chưa giải mã (`&ocirc;` thay vì `ô`). Phải decode, không thì hỏng hết tiếng Việt.
- **Tuổi Trẻ** — `pubDate` không theo chuẩn RFC-822, cần bộ đọc ngày riêng.
- **Tuổi Trẻ** — một số bài có mốc thời gian ở tương lai (lệch múi giờ server).
- **VnEconomy** — một bài có thể nằm ở cả mục Chứng khoán lẫn Tài chính → khử trùng lặp theo URL.

"""Lược đồ của đề tài: 4 loại target, 11 khía cạnh hai cấp, 3 nhãn cảm xúc.

Nguồn: slide 7 (target) và slide 8 (khía cạnh). Cấp 1 theo FiQA, cấp 2 do nhóm định nghĩa.
"""

from __future__ import annotations

ASPECT_SCHEME: dict[str, tuple[str, ...]] = {
    "Corporate": (
        "Kết quả kinh doanh",
        "Sự kiện doanh nghiệp",
        "Nợ và huy động vốn",
    ),
    "Stock": (
        "Diễn biến giá cổ phiếu",
        "Giao dịch của nhà đầu tư",
    ),
    "Market": (
        "Diễn biến thị trường chung",
    ),
    "Economy": (
        "Tăng trưởng và lạm phát",
        "Chính sách tiền tệ và lãi suất",
        "Tỷ giá",
        "Thương mại và đầu tư",
        "Quy định và chính sách tài khóa",
    ),
}

ASPECT_L2: tuple[str, ...] = tuple(l2 for v in ASPECT_SCHEME.values() for l2 in v)
L2_TO_L1: dict[str, str] = {l2: l1 for l1, v in ASPECT_SCHEME.items() for l2 in v}

SENTIMENTS = ("positive", "negative", "neutral")

# 4 loại target (slide 7)
TARGET_TYPES = ("company", "agency", "currency", "index")

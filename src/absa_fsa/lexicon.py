"""Từ điển thực thể: tên xuất hiện trong tin -> mã chuẩn hóa.

Đây là hạt giống của từ điển thực thể thật ("Hòa Phát" / "Tập đoàn Hòa Phát" / "HPG"
đều quy về HPG). Hiện chỉ có các tên tiếng Anh hay gặp trong 2 nguồn đang bật.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Entity:
    canonical_id: str
    type: str               # company | agency | currency | index
    surfaces: tuple[str, ...]


ENTITIES: tuple[Entity, ...] = (
    # --- chỉ số, thị trường ---
    Entity("VN-INDEX", "index", ("VN-Index", "VNIndex", "VN Index")),
    Entity("VN30", "index", ("VN30-Index", "VN30 Index", "VN30")),
    Entity("HNX-INDEX", "index", ("HNX-Index", "HNX Index")),
    Entity("UPCOM-INDEX", "index", ("UPCoM-Index", "UPCoM Index")),
    Entity("HOSE", "index", ("Ho Chi Minh Stock Exchange", "HoSE", "HOSE")),
    Entity("HNX", "index", ("Hanoi Stock Exchange", "HNX")),
    Entity("STOCK-MARKET", "index", ("stock market", "securities market")),

    # --- tiền tệ ---
    Entity("VND", "currency", ("Vietnamese dong", "VND", "dong")),

    # --- cơ quan quản lý ---
    Entity("SBV", "agency", ("State Bank of Vietnam", "SBV", "central bank")),
    Entity("MOF", "agency", ("Ministry of Finance", "MoF", "MOF", "finance ministry")),
    Entity("SSC", "agency", ("State Securities Commission", "SSC")),
    Entity("MOIT", "agency", ("Ministry of Industry and Trade", "MoIT", "MOIT")),
    Entity("NSO", "agency", ("National Statistics Office", "NSO", "General Statistics Office")),

    # --- doanh nghiệp niêm yết ---
    Entity("VIC", "company", ("Vingroup", "VIC")),
    Entity("VHM", "company", ("Vinhomes", "VHM")),
    Entity("VRE", "company", ("Vincom Retail", "VRE")),
    Entity("VNM", "company", ("Vinamilk", "VNM")),
    Entity("HPG", "company", ("Hoa Phat Group", "Hoa Phat", "HPG")),
    Entity("MSN", "company", ("Masan Group", "Masan", "MSN")),
    Entity("MWG", "company", ("Mobile World", "MWG")),
    Entity("FPT", "company", ("FPT Corporation", "FPT")),
    Entity("VCB", "company", ("Vietcombank", "VCB")),
    Entity("BID", "company", ("BIDV", "BID")),
    Entity("CTG", "company", ("VietinBank", "CTG")),
    Entity("TCB", "company", ("Techcombank", "TCB")),
    Entity("MBB", "company", ("MB Bank", "MBBank", "MBB")),
    Entity("VPB", "company", ("VPBank", "VPB")),
    Entity("ACB", "company", ("ACB",)),
    Entity("STB", "company", ("Sacombank", "STB")),
    Entity("HDB", "company", ("HDBank", "HDB")),
    Entity("LPB", "company", ("LPBank", "LPB")),
    Entity("SHB", "company", ("SHB",)),
    Entity("TPB", "company", ("TPBank", "TPB")),
    Entity("VIB", "company", ("VIB",)),
    Entity("SSI", "company", ("SSI Securities", "SSI")),
    Entity("VCI", "company", ("Vietcap", "VCI")),
    Entity("HCM", "company", ("HSC", "Ho Chi Minh City Securities")),
    Entity("GAS", "company", ("PV Gas", "PetroVietnam Gas")),
    Entity("PLX", "company", ("Petrolimex", "PLX")),
    Entity("BSR", "company", ("Binh Son Refining", "BSR")),
    Entity("GVR", "company", ("Vietnam Rubber Group", "GVR")),
    Entity("VJC", "company", ("Vietjet Air", "Vietjet", "VJC")),
    Entity("HVN", "company", ("Vietnam Airlines", "HVN")),
    Entity("ACV", "company", ("Airports Corporation of Vietnam", "ACV")),
    Entity("NVL", "company", ("Novaland", "NVL")),
    Entity("PDR", "company", ("Phat Dat", "PDR")),
    Entity("DXG", "company", ("Dat Xanh", "DXG")),
    Entity("KDH", "company", ("Khang Dien", "KDH")),
    Entity("SAB", "company", ("Sabeco", "SAB")),
    Entity("POW", "company", ("PV Power", "POW")),
    Entity("REE", "company", ("REE Corporation", "REE")),
    Entity("PNJ", "company", ("Phu Nhuan Jewelry", "PNJ")),
    Entity("DGC", "company", ("Duc Giang Chemicals", "DGC")),
    Entity("GMD", "company", ("Gemadept", "GMD")),
    Entity("VTP", "company", ("Viettel Post", "VTP")),
    Entity("FRT", "company", ("FPT Retail", "FRT")),
)

ENTITY_BY_ID = {e.canonical_id: e for e in ENTITIES}


def _build() -> tuple[re.Pattern[str], dict[str, Entity]]:
    """Một regex gộp mọi tên, tên dài đứng trước để khớp tên dài nhất."""
    pairs: list[tuple[str, Entity]] = []
    for e in ENTITIES:
        for s in e.surfaces:
            pairs.append((s, e))
    pairs.sort(key=lambda p: -len(p[0]))
    by_surface: dict[str, Entity] = {}
    for s, e in pairs:
        by_surface.setdefault(s, e)
    alt = "|".join(re.escape(s) for s, _ in pairs)
    # biên từ: không dính chữ, số, gạch nối ở hai đầu
    rx = re.compile(rf"(?<![\w-])(?:{alt})(?![\w-])")
    return rx, by_surface


_RX, _BY_SURFACE = _build()


def find_mentions(text: str) -> list[tuple[int, int, Entity]]:
    """Trả (start, end, entity) không chồng lấn, theo thứ tự xuất hiện.

    Phân biệt hoa thường: "dong" (tiền) chỉ khớp chữ thường, "Dong Nai" thì không.
    """
    out: list[tuple[int, int, Entity]] = []
    for m in _RX.finditer(text):
        ent = _BY_SURFACE.get(m.group(0))
        if ent is None:
            continue
        out.append((m.start(), m.end(), ent))
    return out

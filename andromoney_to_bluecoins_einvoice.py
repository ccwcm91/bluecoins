#!/usr/bin/env python3
"""Interactive AndroMoney to Bluecoins CSV converter.

The converter is intentionally conservative: it proposes Bluecoins rows from
AndroMoney rows, asks for review, and remembers accepted mappings in a JSON
rules file.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable


BLUECOINS_FIELDS = [
    "(1)Type",
    "(2)Date",
    "(3)Item or Payee",
    "(4)Amount",
    "(5)Currency",
    "(6)ConversionRate",
    "(7)Parent Category",
    "(8)Category",
    "(9)Account Type",
    "(10)Account",
    "(11)Notes",
    "(12) Label",
    "(13) Status",
    "(14) Split",
]

BC_TYPE = "(1)Type"
BC_DATE = "(2)Date"
BC_TITLE = "(3)Item or Payee"
BC_AMOUNT = "(4)Amount"
BC_GROUP = "(7)Parent Category"
BC_CATEGORY = "(8)Category"
BC_ACCOUNT = "(10)Account"
BC_NOTE = "(11)Notes"
BC_TAG = "(12) Label"
BC_STATUS = "(13) Status"

DEFAULT_ACCOUNT_MAP = {
    "中信一般": "中信雙和一般 30443",
    "現金": "錢包",
    "玉山uni": "玉山Unicard 7467",
    "玉山only 新": "玉山Only 4481",
    "玉山only": "玉山Only附卡 2739",
    "玉山": "玉山南勢角 24318",
    "玉山UBear": "玉山U Bear 3897",
    "富邦數位": "富邦營業部數位 63892",
    "台新Richart": "台新敦南Richart 64165",
    "台新Richart子帳戶": "台新敦南Richart子帳戶",
    "中信中華電信": "中信中華電信聯名卡 2597",
    "中信uniopen": "中信uniopen 6887",
    "一銀數位": "第一永和數位 67667",
    "一銀定存": "第一定存",
    "富邦一般": "富邦永和一般 02555",
    "聯邦綠卡": "聯邦綠卡 1007",
    "國泰cube": "國泰CUBE 5756",
    "國泰數位": "國泰數位 10996",
    "台新GoGo": "台新@GoGo 0507",
    "台新太陽": "台新太陽 7307",
    "聯邦New New Bank": "聯邦數位 43444",
    "中信中油": "中信中油 7627",
    "一銀房貸": "第一大安房貸 66395",
    "員工持股信託": "員工持股信託",
    "MTK股票": "員工持股信託",
    "土銀數位": "土銀數位 02329",
    "中信證券": "中信證券 07750",
    "彰銀": "彰銀數位 92700",
    "彰銀My購": "彰銀My購 5102",
}

DEFAULT_CATEGORY_MAP = {
    # 飲食類 (維持現狀)
    "餐飲食品|早餐": ("支出", "飲食", "外食三餐"),
    "餐飲食品|午餐": ("支出", "飲食", "外食三餐"),
    "餐飲食品|晚餐": ("支出", "飲食", "外食三餐"),
    "餐飲食品|飲料": ("支出", "飲食", "飲料"),
    "餐飲食品|公司餐費": ("支出", "飲食", "公司餐費"),
    "餐飲食品|點心零嘴": ("支出", "飲食", "點心零嘴"),

    # 家庭類 (整合)
    "3C通訊|電話費": ("支出", "家庭", "電話網路費"),
    "居家生活|水費": ("支出", "家庭", "水費"),
    "居家生活|電費": ("支出", "家庭", "電費"),
    "居家生活|瓦斯費": ("支出", "家庭", "瓦斯費"),
    "借貸|貸款利息": ("支出", "家庭", "房貸利息"),
    "居家生活|管理費": ("支出", "家庭", "管理費"),
    "居家生活|小渝生活費": ("支出", "家庭", "生活費"),
    "居家生活|大賣場購物": ("支出", "家庭", "大賣場購物"),
    "房屋|其他": ("支出", "房屋", "裝修"),
    "居家生活|傢俱": ("支出", "房屋", "家具家電"),
    "居家生活|家電用品": ("支出", "房屋", "家具家電"),
	
    # 健康與保險
    "醫療保健|購買藥物": ("支出", "健康與保險", "買藥"),
    "醫療保健|看診": ("支出", "健康與保險", "看診"),
    "醫療保健|診所就醫": ("支出", "健康與保險", "看診"),
    "醫療保健|科林呼吸器訂閱": ("支出", "健康與保險", "科林呼吸器訂閱"),
    "醫療保健|保險": ("支出", "健康與保險", "保險"),
    "小孩|看診": ("支出", "健康與保險", "看診"),

    # 汽車類 (統一名稱)
    "汽機車|油錢": ("支出", "汽車", "汽油"),
    "汽機車|維修保養": ("支出", "汽車", "保養"),
    "汽機車|停車費": ("支出", "汽車", "臨時停車費"),
    "汽機車|車位租金": ("支出", "汽車", "停車位月租"),
    "汽機車|美容洗車": ("支出", "汽車", "洗車"),
    "汽機車|過路費": ("支出", "汽車", "eTag加值"),

    # 政府類
    "稅|所得稅": ("支出", "政府", "所得稅"),
    "稅|房屋稅": ("支出", "政府", "房屋稅"),
    "汽機車|保險與稅捐": ("支出", "政府", "牌照稅"),
    "醫療保健|國民年金": ("支出", "政府", "國民年金"),

    # 娛樂/教育類
    "3C通訊|軟體服務": ("支出", "娛樂", "軟體服務"),
    "休閒娛樂|旅行遊玩": ("支出", "娛樂", "旅遊消費"),
    "休閒娛樂|住宿": ("支出", "娛樂", "旅館"),
    "休閒娛樂|機票": ("支出", "娛樂", "旅遊交通"),
    "休閒娛樂|租車": ("支出", "娛樂", "旅遊交通"),
    "休閒娛樂|門票": ("支出", "娛樂", "旅遊消費"),
    "休閒娛樂|旅遊交通": ("支出", "娛樂", "旅遊交通"),
    "休閒娛樂|電腦遊戲": ("支出", "娛樂", "遊戲"),
    "圖書刊物|書籍": ("支出", "教育", "書籍"),
    "小孩|才藝費": ("支出", "教育", "才藝費"),

    # 其他
    "一般收入|信用卡回饋": ("收入", "其他", "信用卡回饋"),
    "一般收入|公司薪資": ("收入", "工作", "獎金"),
    "一般收入|其他": ("收入", "其他", "其他"),
    "費用|手續費": ("支出", "其他", "手續費"),
    "其他|雜支": ("支出", "其他", "其他"),
    "投資收入|利息": ("收入", "利息", "活存"),
    "利息收入|活存利息": ("收入", "利息", "活存"),

    # 轉帳類 (雖然程式會自動判斷，但加入對應可作為備援)
    "轉帳|一般轉帳": ("轉帳", "(轉帳)", "(轉帳)"),
    "轉帳|信用卡費": ("轉帳", "(轉帳)", "(轉帳)"),

    # 舊資料分類 (待整理)
    "3C通訊|電腦商品": ("支出", "舊資料分類", "3C通訊_電腦商品"),
    "一般收入|收取還款": ("收入", "舊資料分類", "一般收入_收取還款"),
    "盤點|盤盈": ("收入", "舊資料分類", "盤點_盤盈"),
    "盤點|盤損": ("支出", "舊資料分類", "盤點_盤損"),
    "其他|盤盈": ("收入", "舊資料分類", "其他_盤盈"),
    "其他|盤損": ("支出", "舊資料分類", "其他_盤損"),
    "人情交際|應酬交際": ("支出", "舊資料分類", "人情交際_應酬交際"),
    "人情交際|送禮請客": ("支出", "舊資料分類", "人情交際_送禮請客"),
}

AUTO_SKIP_CATEGORIES = set()

SALARY_DEDUCTION_MAP = {
    ("稅", "所得稅"): ("支出", "政府", "所得稅"),
    ("醫療保健", "勞保"): ("支出", "政府", "勞保"),
    ("醫療保健", "健保"): ("支出", "政府", "健保"),
    ("醫療保健", "團保"): ("支出", "健康與保險", "公司團保"),
    ("費用", "福利金"): ("支出", "其他固定支出", "福利金"),
    ("餐飲食品", "公司餐費"): ("支出", "飲食", "公司餐費"),
}

ACCOUNT_TYPE_MAP = {
    "中信雙和一般 30443": "銀行",
    "富邦營業部數位 63892": "銀行",
    "台新敦南Richart 64165": "銀行",
    "台新敦南Richart子帳戶": "銀行",
    "第一永和數位 67667": "銀行",
    "玉山南勢角 24318": "銀行",
    "富邦永和一般 02555": "銀行",
    "國泰數位 10996": "銀行",
    "聯邦數位 43444": "銀行",
    "第一大安房貸 66395": "銀行",
    "第一定存": "銀行",
    "土銀數位 02329": "銀行",
    "中信證券 07750": "銀行",
    "彰銀數位 92700": "銀行",
    "玉山Unicard 7467": "信用卡",
    "玉山Only 4481": "信用卡",
    "玉山Only附卡 2739": "信用卡",
    "玉山U Bear 3897": "信用卡",
    "台新@GoGo 0507": "信用卡",
    "台新太陽 7307": "信用卡",
    "中信中華電信聯名卡 2597": "信用卡",
    "中信uniopen 6887": "信用卡",
    "聯邦綠卡 1007": "信用卡",
    "國泰CUBE 5756": "信用卡",
    "中信中油 7627": "信用卡",
    "彰銀My購 5102": "信用卡",
    "錢包": "現金",
    "家電家具": "資產",
    "員工持股信託": "投資",
}


@dataclass(frozen=True)
class AndroRow:
    raw: dict[str, str]
    index: int

    @property
    def id(self) -> str:
        return self.raw.get("Id", "")

    @property
    def amount(self) -> int:
        return parse_amount(self.raw.get("金額", "0"))

    @property
    def date(self) -> str:
        return self.raw.get("日期", "")

    @property
    def clock(self) -> str:
        return self.raw.get("時間", "")

    @property
    def category(self) -> str:
        return self.raw.get("分類", "")

    @property
    def subcategory(self) -> str:
        return self.raw.get("子分類", "")

    @property
    def from_account(self) -> str:
        return self.raw.get("付款(轉出)", "")

    @property
    def to_account(self) -> str:
        return self.raw.get("收款(轉入)", "")

    @property
    def note(self) -> str:
        return self.raw.get("備註", "")

    @property
    def project(self) -> str:
        return self.raw.get("專案", "")

    @property
    def merchant(self) -> str:
        return self.raw.get("商家(公司)", "")


@dataclass(frozen=True)
class ReviewItem:
    source_rows: list[AndroRow]
    label: str

    @property
    def newest_sort_key(self) -> tuple[str, str, int]:
        newest = max(self.source_rows, key=lambda row: source_sort_key(row))
        return source_sort_key(newest)


@dataclass(frozen=True)
class RuleOption:
    name: str
    description: str
    rows: list[dict[str, str]]
    matched_einvoice_keys: set[tuple[str, int]] = field(default_factory=set)
    saved: bool = False


class Rules:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()
        self.data.setdefault("accounts", {})
        self.data.setdefault("categories", {})
        self.data.setdefault("tags", {})
        self.data.setdefault("titles", {})
        self.data.setdefault("named_rules", {})
        self.data.setdefault("default_blank_time", "00:00:00")

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def account(self, name: str) -> str:
        if not name:
            return ""
        return self.data["accounts"].get(name.strip()) or DEFAULT_ACCOUNT_MAP.get(name.strip()) or name.strip()

    def remember_account(self, source: str, target: str) -> None:
        if source and target:
            self.data["accounts"][source] = target

    def category(self, main: str, sub: str) -> tuple[str, str, str]:
        key = category_key(main, sub)
        value = self.data["categories"].get(key)
        if value:
            return value["type"], value["group"], value["category"]
        return DEFAULT_CATEGORY_MAP.get(key, ("支出", main or "其他", sub or main or "其他"))

    def remember_category(self, main: str, sub: str, tx_type: str, group: str, category: str) -> None:
        self.data["categories"][category_key(main, sub)] = {
            "type": tx_type,
            "group": group,
            "category": category,
        }

    def named_rule(self, signature: str) -> dict[str, Any] | None:
        return self.data["named_rules"].get(signature)

    def remember_named_rule(
        self,
        signature: str,
        rule_name: str,
        source_summary: str,
        rows: list[dict[str, str]],
    ) -> None:
        self.data["named_rules"][signature] = {
            "rule": rule_name,
            "source_summary": source_summary,
            "rows": rows,
        }


def category_key(main: str, sub: str) -> str:
    return f"{main.strip()}|{sub.strip()}"


def parse_amount(value: str) -> int:
    return int(round(float((value or "0").replace(",", ""))))


def normalize_time(value: str, default: str = "00:00:00") -> str:
    value = (value or "").strip()
    if not value:
        return default
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return default
    digits = digits.zfill(4)
    hour = int(digits[:-2])
    minute = int(digits[-2:])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid AndroMoney time: {value!r}")
    return f"{hour:02d}:{minute:02d}:00"


def bluecoins_datetime(date_value: str, time_value: str, default_time: str = "00:00:00") -> tuple[str, str]:
    day = datetime.strptime(date_value, "%Y%m%d").date()
    clock = normalize_time(time_value, default_time)
    return f"{day.month}/{day.day}/{day.year} {clock[:5]}", clock[:5]


def source_sort_key(row: AndroRow) -> tuple[str, str, int]:
    return (row.date, normalize_time(row.clock), row.index)


def source_signature(rows: list[AndroRow]) -> str:
    if len(rows) > 1:
        ids = ",".join(sorted(row.id for row in rows))
        date = rows[0].date if rows else ""
        return f"batch:{date}:{ids}"
    row = rows[0]
    return "|".join(
        [
            "row",
            row.category,
            row.subcategory,
            row.from_account,
            row.to_account,
            row.note,
            row.project,
            row.merchant,
        ]
    )


def source_summary(rows: list[AndroRow]) -> str:
    if len(rows) > 1:
        amount = sum(row.amount for row in rows)
        ids = ",".join(row.id for row in rows)
        return f"{rows[0].date} batch ids={ids} total_source_amount={amount}"
    row = rows[0]
    return (
        f"{row.date} {row.clock or '0000'} {row.amount} "
        f"{row.category}/{row.subcategory} {row.from_account or '-'}->{row.to_account or '-'} "
        f"note={row.note or '-'} project={row.project or '-'} merchant={row.merchant or '-'}"
    )


def read_andromoney(path: Path) -> tuple[list[str], list[str], list[AndroRow]]:
    with path.open("r", encoding="cp950", newline="") as fh:
        raw_rows = list(csv.reader(fh))
    if len(raw_rows) < 2:
        raise ValueError("AndroMoney CSV must contain metadata and header rows.")
    metadata = raw_rows[0]
    header = raw_rows[1]
    parsed = []
    for idx, row in enumerate(raw_rows[2:], start=3):
        if not any(cell.strip() for cell in row):
            continue
        padded = row + [""] * (len(header) - len(row))
        parsed.append(AndroRow(dict(zip(header, padded)), idx))
    return metadata, header, parsed


def write_andromoney(path: Path, metadata: list[str], header: list[str], rows: list[AndroRow]) -> None:
    with path.open("w", encoding="cp950", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(metadata)
        writer.writerow(header)
        for row in rows:
            writer.writerow([row.raw.get(col, "") for col in header])


def find_einvoice_match(date_str: str, amount: int, einvoices: dict | None) -> tuple[str | None, tuple[str, int] | None, str | None]:
    """
    比對電子發票。傳回 (明細內容, 匹配鍵值, 額外說明備註)。
    """
    if not einvoices:
        return None, None, None

    target_amount = abs(amount)
    row_date_dt = datetime.strptime(date_str, "%Y%m%d").date()

    # 第一階段：日期完全一致
    exact_date_key = (date_str, target_amount)
    if exact_date_key in einvoices:
        return einvoices[exact_date_key], exact_date_key, None

    # 第二階段：彈性比對 (發票日期比記帳日期晚 1-3 天)
    for day_offset in range(1, 4):
        potential_invoice_date_dt = row_date_dt + timedelta(days=day_offset)
        potential_invoice_date_str = potential_invoice_date_dt.strftime("%Y%m%d")
        potential_key = (potential_invoice_date_str, target_amount)

        if potential_key in einvoices:
            info = f"(發票日期: {potential_invoice_date_str} 比記帳日期晚 {day_offset} 天)"
            return einvoices[potential_key], potential_key, info

    return None, None, None


def read_einvoices(path: Path) -> dict[tuple[str, int], str]:
    """讀取財政部電子發票 CSV (包含標準 CSV 與 Master/Detail 管道格式) 並以 (日期, 金額) 為 Key 彙整明細。"""
    einvoices = {}
    if not path or not path.exists():
        return einvoices
    
    lines = []
    for encoding in ["utf-8-sig", "utf-8", "cp950", "big5"]:
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
                lines = fh.readlines()
                if lines: break
        except Exception:
            continue

    if not lines:
        return einvoices

    # 判斷是否為 M|D (Master/Detail) 管道格式
    is_pipe_format = any(l.strip().startswith("M|") for l in lines[:20])

    if is_pipe_format:
        master_info = {}  # inv_no -> {key: (date, amt), header: str}
        detail_map = {}   # inv_no -> [item_lines]
        for line in lines:
            p = [x.strip() for x in line.split('|')]
            if len(p) < 2: continue
            if p[0] == 'M' and len(p) >= 8:
                carrier_name = p[1]
                carrier_no = p[2]
                raw_date = p[3] # YYYYMMDD
                store_tax_id = p[4]
                store_name = p[5]
                inv_no = p[6]
                total_amt = p[7]
                
                # 格式化日期為 YYYY-MM-DD
                fmt_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                
                header = (
                    f"載具名稱:{carrier_name}\n"
                    f"載具號碼:{carrier_no}\n"
                    f"發票日期:{fmt_date}\n"
                    f"商店統編:{store_tax_id}\n"
                    f"商店店名:{store_name}\n"
                    f"發票號碼:{inv_no}\n"
                    f"總金額:{total_amt}\n"
                    f"明細:"
                )
                master_info[inv_no] = {
                    "key": (raw_date, parse_amount(total_amt)),
                    "header": header
                }
            elif p[0] == 'D' and len(p) >= 4:
                inv_no = p[1]
                item_amt = p[2]
                item_name = p[3]
                detail_map.setdefault(inv_no, []).append(f"${item_amt} {item_name}")
        
        for inv_no, info in master_info.items():
            items = detail_map.get(inv_no, [])
            if items:
                key = info["key"]
                val = info["header"] + "\n" + "\n".join(items)
                # 若同日期同金額有多張發票，以分隔線區分
                einvoices[key] = (einvoices[key] + "\n\n---\n\n" + val) if key in einvoices else val
        return einvoices

    # 處理標準表格 CSV 格式
    header_idx = -1
    for i, line in enumerate(lines):
        if "發票日期" in line and ("金額" in line or "品名" in line):
            header_idx = i
            break
    
    if header_idx != -1:
        reader = csv.DictReader(lines[header_idx:])
        temp_map = {} # (date, total_amt) -> {inv_no: ..., items: []}
        for row in reader:
            raw_date = row.get("發票日期", "").replace("/", "").replace("-", "").strip()
            total_amt_str = row.get("總金額") or row.get("金額") or "0"
            raw_total_amount = parse_amount(total_amt_str)
            
            inv_no = row.get("發票號碼", "")
            item_name = row.get("品名", "").strip()
            qty = row.get("數量", "1").strip()
            item_amt = row.get("金額") or row.get("小計") or ""
            
            if not raw_date or raw_total_amount == 0 or not item_name: continue
            key = (raw_date, raw_total_amount)
            detail = f"{item_name} x{qty}"
            if item_amt: detail += f" ${item_amt}"
            
            if key not in temp_map:
                temp_map[key] = {"inv_no": inv_no, "items": []}
            temp_map[key]["items"].append(detail)
            
        for key, info in temp_map.items():
            prefix = f"發票號碼:{info['inv_no']}\n" if info['inv_no'] else ""
            prefix += f"總金額:{key[1]}\n"
            prefix += "明細:\n"
            einvoices[key] = prefix + "\n".join(info["items"])
    
    return einvoices

def read_bluecoins_header(path: Path) -> list[str]:
    if not path.exists():
        return BLUECOINS_FIELDS
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        return next(reader, BLUECOINS_FIELDS)


def parse_filter_date(value: str) -> datetime.date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def filter_rows_by_date(rows: list[AndroRow], date_from: str | None, date_to: str | None) -> list[AndroRow]:
    start = parse_filter_date(date_from) if date_from else None
    end = parse_filter_date(date_to) if date_to else None
    filtered = []
    for row in rows:
        row_date = datetime.strptime(row.date, "%Y%m%d").date()
        if start and row_date < start:
            continue
        if end and row_date > end:
            continue
        filtered.append(row)
    return filtered


def write_bluecoins(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def make_row(
    *,
    tx_type: str,
    date: str,
    title: str,
    amount: int,
    group: str,
    category: str,
    account: str,
    note: str = "",
    tag: str = "",
    split: str = "",
) -> dict[str, str]:
    type_map = {"收入": "i", "支出": "e", "轉帳": "t"}
    acc_type = ACCOUNT_TYPE_MAP.get(account, "銀行")

    return {
        "(1)Type": type_map.get(tx_type, tx_type),
        "(2)Date": date,
        "(3)Item or Payee": title,
        "(4)Amount": str(amount),
        "(5)Currency": "TWD",
        "(6)ConversionRate": "1",
        "(7)Parent Category": group,
        "(8)Category": category,
        "(9)Account Type": acc_type,
        "(10)Account": account,
        "(11)Notes": note,
        "(12) Label": tag,
        "(13) Status": "",
        "(14) Split": split,
    }


def title_for(row: AndroRow) -> str:
    # 1. 優先處理具有特定格式要求的備註 (如生活費)
    if row.category == "居家生活" and row.subcategory == "小渝生活費":
        parsed = parse_life_expense_title(row.note)
        if parsed:
            return parsed

    # 2. 針對電話費的特殊命名邏輯：含有「小渝」則轉換為「Ivy電話費」，其餘預設為「CCW電話費」
    if row.category == "3C通訊" and row.subcategory == "電話費":
        if "小渝" in row.note:
            return "Ivy電話費"
        if not row.note.strip():
            return "CCW電話費"

    # 3. 針對管理費：格式為「管理費-地點」，若無備註則預設為「力霸十二樓」
    if row.category == "居家生活" and row.subcategory == "管理費":
        suffix = row.note.strip() or "力霸十二樓"
        return f"管理費-{suffix}"

    # 4. 針對水、電、瓦斯費：格式為「子分類-地點」，若無備註則預設為「力霸十二樓」
    if row.category == "居家生活" and row.subcategory in ["水費", "電費", "瓦斯費"]:
        suffix = row.note.strip() or "力霸十二樓"
        return f"{row.subcategory}-{suffix}"

    # 4. 針對車位租金：統一轉換為「停車位月租」
    if row.subcategory == "車位租金" or row.note.strip() == "車位租金":
        return "停車位月租"

    # 針對診所就醫：標題統一改為「看診」
    if row.subcategory == "診所就醫":
        return "看診"

    # 5. 針對利息：區分定存與活存，一銀房貸每月1日視為定存
    if (row.category == "投資收入" and row.subcategory == "利息") or \
       (row.category == "利息收入" and row.subcategory == "活存利息"):
        if (row.from_account == "一銀房貸" or row.to_account == "一銀房貸") and row.date.endswith("01"):
            return "利息-定存"
        return "利息-活存"

    # 3. 標題處理：優先使用備註，若無則使用子分類
    title = row.note.strip() or row.subcategory or row.category or "未命名"

    # 移除學雜費項目最前面的「周懋昀」或「周穆寬」
    for name in ["周懋昀", "周穆寬"]:
        if title.startswith(name):
            title = title[len(name):].strip()

    return title


def note_for(row: AndroRow) -> str:
    if should_clear_note(row):
        return ""
    parts = [row.note, row.merchant]
    return " ".join(part for part in parts if part).strip()


def tag_for(row: AndroRow) -> str:
    if row.category == "居家生活" and row.subcategory == "小渝生活費":
        return "Ivy"
    if row.category == "3C通訊" and row.subcategory == "電話費" and "小渝" in row.note:
        return "Ivy"
    project = row.project.strip()
    normalized = project.lower()
    if normalized == "line pay":
        return "LinePay"
    if normalized == "icash pay":
        return "icashPay"
    if normalized == "中油 pay":
        return "中油pay"
    return project


def parse_life_expense_title(note: str) -> str:
    note = (note or "").strip()
    if len(note) >= 5 and note[:4].isdigit() and note.endswith("月"):
        month_text = note[4:-1]
        zh_months = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
            "十一": 11,
            "十二": 12,
        }
        month = zh_months.get(month_text)
        if month:
            return f"{month}月生活費"
    return ""


def school_fee_category(row: AndroRow) -> str:
    if row.category != "小孩" or row.subcategory != "學雜費":
        return ""
    text = f"{row.note} {row.merchant}"
    if "周懋昀" in text:
        return "懋學雜費"
    if "周穆寬" in text:
        return "寬學雜費"
    return ""


def should_clear_note(row: AndroRow) -> bool:
    if row.category == "小孩" and row.subcategory == "學雜費":
        return bool(school_fee_category(row))
    if row.category == "居家生活" and row.subcategory in ["管理費", "水費", "電費", "瓦斯費"]:
        return True
    if row.category == "3C通訊" and row.subcategory == "電話費":
        return True
    if row.category == "居家生活" and row.subcategory == "小渝生活費":
        return True
    if row.category == "3C通訊" and row.subcategory == "軟體服務" and row.note == "Google Cloud":
        return True
    if row.subcategory == "車位租金" or row.note.strip() == "車位租金":
        return True
    return False


def is_salary_candidate(row: AndroRow) -> bool:
    if row.from_account != "中信一般" and row.to_account != "中信一般":
        return False
    try:
        parsed = normalize_time(row.clock)
    except ValueError:
        return False
    row_time = time.fromisoformat(parsed)
    return time(2, 45) <= row_time <= time(3, 15)


def group_salary_batches(rows: list[AndroRow]) -> dict[int, list[AndroRow]]:
    candidates = [row for row in rows if is_salary_candidate(row)]
    by_date: dict[str, list[AndroRow]] = {}
    for row in candidates:
        by_date.setdefault(row.date, []).append(row)

    row_to_batch: dict[int, list[AndroRow]] = {}
    for batch in by_date.values():
        has_salary = any(row.category == "一般收入" and row.subcategory == "公司薪資" for row in batch)
        if not has_salary:
            continue
        for row in batch:
            row_to_batch[row.index] = batch
    return row_to_batch


def convert_salary_batch(batch: list[AndroRow], rules: Rules, einvoices: dict = None) -> tuple[list[dict[str, str]], set[tuple[str, int]]]:
    sorted_batch = sorted(batch, key=lambda row: (row.date, normalize_time(row.clock), row.id))
    base = sorted_batch[0]
    full_date, _ = bluecoins_datetime(base.date, "0300", rules.data["default_blank_time"])
    month = int(base.date[4:6])
    title = f"{month}月薪資"
    rows: list[dict[str, str]] = []
    local_matched_keys = set()

    # 1. 先計算認股相關數值，以便後續在中信一般帳戶中扣除
    stock_purchase = sum(abs(row.amount) for row in sorted_batch if row.note == "MTK股票" or row.subcategory == "股票")
    stock_subsidy = sum(row.amount for row in sorted_batch if row.note == "持股補助")
    stock_self_pay = stock_purchase - stock_subsidy

    main_salary = sum(
        row.amount
        for row in sorted_batch
        if row.category == "一般收入"
        and row.subcategory == "公司薪資"
        and row.note not in {"持股補助", "加班費", "獎學金"}
    )
    salary_transfer = next((row for row in sorted_batch if row.subcategory == "MTK帳戶分配"), None)
    salary_transfer_amount = salary_transfer.amount if salary_transfer else 0
    overtime = sum(
        row.amount
        for row in sorted_batch
        if row.category == "一般收入" and row.subcategory == "公司薪資" and row.note == "加班費"
    )

    if main_salary:
        rows.append(
            make_row(
                tx_type="收入",
                date=full_date,
                title=title,
                amount=main_salary - salary_transfer_amount - stock_self_pay,
                group="工作",
                category="薪水",
                account=rules.account("中信一般"),
                note="",
                split="s",
            )
        )
    if salary_transfer_amount:
        rows.append(
            make_row(
                tx_type="收入",
                date=full_date,
                title=title,
                amount=salary_transfer_amount,
                group="工作",
                category="薪水",
                account=rules.account(salary_transfer.to_account),
                note="",
                split="s",
            )
        )
    if overtime:
        rows.append(
            make_row(
                tx_type="收入",
                date=full_date,
                title=title,
                amount=overtime,
                group="工作",
                category="加班費",
                account=rules.account("中信一般"),
                note="",
                split="s",
            )
        )

    # 處理特定補助項目 (停車費、獎學金)
    for row in sorted_batch:
        if row.note in ["MTK停車費", "獎學金"]:
            display_note = row.note.replace("MTK", "")
            rows.append(
                make_row(
                    tx_type="收入",
                    date=full_date,
                    title=title,
                    amount=row.amount,
                    group="工作",
                    category="補助",
                    account=rules.account("中信一般"),
                    note=display_note,
                    split="s",
                )
            )

    for row in sorted_batch:
        mapped = SALARY_DEDUCTION_MAP.get((row.category, row.subcategory))
        if not mapped:
            continue
        tx_type, group, category = mapped

        # 特殊處理：勞退自提 (原 AndroMoney 分類為醫療保健/勞保，且備註含勞退自提)
        display_note = row.note
        if (row.category == "醫療保健" and row.subcategory == "勞保") and "勞退自提" in row.note:
            category = "勞退自提"
            # 移除備註中的文字
            display_note = row.note.replace("勞退自提", "").strip()

        # 嘗試對應電子發票 (如公司餐費、停車費)
        inv_detail, inv_key, inv_info = find_einvoice_match(row.date, row.amount, einvoices)
        if inv_detail:
            local_matched_keys.add(inv_key)
            if display_note:
                display_note = f"{display_note}\n\n{inv_detail}"
            else:
                display_note = inv_detail
            
            if inv_info:
                display_note = f"{display_note}\n{inv_info}"

        rows.append(
            make_row(
                tx_type=tx_type,
                date=full_date,
                title=title,
                amount=abs(row.amount),
                group=group,
                category=category,
                account=rules.account("中信一般"),
                note=display_note,
                split="s",
            )
        )

    if stock_self_pay:
        rows.append(
            make_row(
                tx_type="收入",
                date=full_date,
                title=title,
                amount=stock_self_pay,
                group="工作",
                category="薪水",
                account=rules.account("員工持股信託"),
                note="自提",
                split="s",
            )
        )
    if stock_subsidy:
        rows.append(
            make_row(
                tx_type="收入",
                date=full_date,
                title=title,
                amount=stock_subsidy,
                group="工作",
                category="補助",
                account=rules.account("員工持股信託"),
                note="公提",
                split="s",
            )
        )

    return rows, local_matched_keys


def convert_generic_split(batch: list[AndroRow], rules: Rules, einvoices: dict = None) -> tuple[list[dict[str, str]], set[tuple[str, int]]]:
    """將具有相同時間與帳戶的交易合併為 Split 格式。"""
    sorted_batch = sorted(batch, key=lambda r: r.index)
    # 尋找主項目（非手續費）作為標題基準
    main_row = next((r for r in sorted_batch if r.subcategory != "手續費"), sorted_batch[0])
    common_title = title_for(main_row)

    # 判斷是否為海外刷卡手續費 (約為支出金額的 1.5%)
    is_overseas_fee = False
    fee_row = next((r for r in sorted_batch if r.subcategory == "手續費"), None)
    if fee_row and main_row and fee_row != main_row:
        main_amount = sum(r.amount for r in sorted_batch if r.subcategory != "手續費")
        if main_amount > 0:
            ratio = fee_row.amount / main_amount
            # 判斷比例是否接近 1.5% (取 1.4% ~ 1.6% 區間)
            if 0.014 <= ratio <= 0.016:
                is_overseas_fee = True

    results = []
    local_matched_keys = set()
    for row in sorted_batch:
        converted_rows, matched_key = convert_regular(row, rules, einvoices)
        if matched_key:
            local_matched_keys.add(matched_key)
        for cr in converted_rows:
            # 除非是手續費，否則保留各自透過 title_for 產生的標題
            if row.subcategory == "手續費":
                cr[BC_TITLE] = common_title
            cr["(14) Split"] = "s"
            if is_overseas_fee and row.subcategory == "手續費":
                cr[BC_CATEGORY] = "海外刷卡手續費"
        results.extend(converted_rows)
    return results, local_matched_keys


def convert_regular(row: AndroRow, rules: Rules, einvoices: dict = None) -> tuple[list[dict[str, str]], tuple[str, int] | None]:
    full_date, _ = bluecoins_datetime(row.date, row.clock, rules.data["default_blank_time"])
    title = title_for(row)
    note = note_for(row)
    tag = tag_for(row)

    # 結合電子發票明細 (僅限支出交易)
    matched_invoice_key = None
    if einvoices and not row.to_account:
        einvoice_detail, inv_key, inv_info = find_einvoice_match(row.date, row.amount, einvoices)
        if einvoice_detail:
            matched_invoice_key = inv_key
            # 直接附加格式化好的發票詳細資訊
            if note:
                note = f"{note}\n\n{einvoice_detail}"
            else:
                note = einvoice_detail
            
            if inv_info:
                note = f"{note}\n{inv_info}"

    # 自動偵測 MTK 股票購入交易，轉換為轉帳至資產帳戶
    if "MTK股票" in row.note or row.subcategory == "股票":
        if row.from_account and not row.to_account:
            return (
                [
                    make_row(
                        tx_type="轉帳",
                        date=full_date,
                        title="股票購入",
                        amount=-abs(row.amount),
                        group="(轉帳)",
                        category="(轉帳)",
                        account=rules.account(row.from_account or row.to_account),
                        note=note,
                        tag=tag,
                    ),
                    make_row(
                        tx_type="轉帳",
                        date=full_date,
                        title="股票購入",
                        amount=abs(row.amount),
                        group="(轉帳)",
                        category="(轉帳)",
                        account=rules.account("員工持股信託"),
                        note=note,
                        tag=tag,
                    ),
                ],
                matched_invoice_key,
            )

    if row.from_account and row.to_account:
        transfer_title = "一般轉帳" if row.subcategory == "一般轉帳" else row.subcategory or "轉帳"
        return (
            [
                make_row(
                    tx_type="轉帳",
                    date=full_date,
                    title=transfer_title,
                    amount=-abs(row.amount),
                    group="(轉帳)",
                    category="(轉帳)",
                    account=rules.account(row.from_account),
                    note=note,
                    tag=tag,
                ),
                make_row(
                    tx_type="轉帳",
                    date=full_date,
                    title=transfer_title,
                    amount=abs(row.amount),
                    group="(轉帳)",
                    category="(轉帳)",
                    account=rules.account(row.to_account),
                    note=note,
                    tag=tag,
                ),
            ],
            matched_invoice_key,
        )

    tx_type, group, category = rules.category(row.category, row.subcategory)
    
    # 1. 股利關鍵字優先處理：搜尋子分類、備註與專案欄位
    if "股利" in (row.subcategory + row.note + row.project):
        tx_type = "收入"
        group = "投資"
        category = "股利"
    # 2. 所有的投資收入與一般收入強制轉換為收入類型 (i)，並去除空格影響
    elif row.category.strip() in ["投資收入", "一般收入"]:
        tx_type = "收入"

    custom_school_category = school_fee_category(row)
    if custom_school_category:
        group = "教育"
        category = custom_school_category

    # 針對 AndroMoney 分類為「停車費」但備註為「車位租金」的情況，強制轉換類別為「停車位月租」
    if row.subcategory == "停車費" and row.note.strip() == "車位租金":
        group = "汽車"
        category = "停車位月租"

    # 針對一銀房貸帳戶每月1日的定存利息特殊處理
    if (row.category == "投資收入" and row.subcategory == "利息") or \
       (row.category == "利息收入" and row.subcategory == "活存利息"):
        if (row.to_account == "一銀房貸" or row.from_account == "一銀房貸") and row.date.endswith("01"):
            group = "利息"
            category = "定存"

    # 核心邏輯：優先根據帳戶欄位存在與否判斷金流方向 (比類別關鍵字判斷更準確)
    if row.to_account and not row.from_account:
        tx_type = "收入"
    elif row.from_account and not row.to_account:
        tx_type = "支出"

    is_income = tx_type == "收入"
    # 彈性選擇帳戶：若為收入但 to_account 為空，則從 from_account 抓取（適應 AndroMoney 的輸入習慣）
    account_name = (row.to_account or row.from_account) if is_income else (row.from_account or row.to_account)
    account = rules.account(account_name)

    # 根據 Bluecoins 匯入指南：
    # 支出交易 (Type 'e') 與收入交易 (Type 'i') 在匯入時皆使用正數。
    # Bluecoins 會根據 Type 自動決定增減方向。
    amount = abs(row.amount)
    return [
        make_row(
            tx_type=tx_type,
            date=full_date,
            title=title,
            amount=amount,
            group=group,
            category=category,
            account=account,
            note=note,
            tag=tag,
        )
    ], matched_invoice_key


def convert_all(rows: list[AndroRow], rules: Rules, einvoices: dict = None) -> list[tuple[list[AndroRow], list[dict[str, str]], str]]:
    converted = []
    for item in build_review_items(rows):
        options = candidate_rule_options(item, rules, einvoices)
        converted.append((item.source_rows, options[0].rows if options else [], item.label))
    return converted


def build_review_items(rows: list[AndroRow]) -> list[ReviewItem]:
    salary_batches = group_salary_batches(rows)

    # 預先群組相同時間與帳戶的非薪資交易
    salary_indices = set(salary_batches.keys())
    other_groups: dict[tuple, list[AndroRow]] = {}
    for row in rows:
        if row.index in salary_indices:
            continue

        def get_group_key(r: AndroRow):
            # 對於公共事業費用、管理費或電話費，強制視為獨立交易而不自動合併
            if r.subcategory in ["電費", "水費", "瓦斯費", "管理費", "電話費"]:
                return (r.date, normalize_time(r.clock), r.from_account, r.to_account, r.index)
            return (r.date, normalize_time(r.clock), r.from_account, r.to_account)

        # 群組關鍵字: 日期, 規格化時間, 付款帳戶, 收款帳戶
        other_groups.setdefault(get_group_key(row), []).append(row)

    items: list[ReviewItem] = []
    processed_indices = set()

    for row in rows:
        if row.index in processed_indices:
            continue
        if row.index in salary_batches:
            batch = salary_batches[row.index]
            items.append(ReviewItem(batch, "薪資批次"))
            for b in batch: processed_indices.add(b.index)
        else:
            key = get_group_key(row)
            grp = other_groups[key]
            label = "拆分交易" if len(grp) > 1 else "一般交易"
            items.append(ReviewItem(grp, label))
            for g in grp: processed_indices.add(g.index)

    return sorted(items, key=lambda item: item.newest_sort_key, reverse=True)


def candidate_rule_options(item: ReviewItem, rules: Rules, einvoices: dict = None) -> list[RuleOption]:
    signature = source_signature(item.source_rows)
    options: list[RuleOption] = []
    saved = rules.named_rule(signature)
    if saved:
        options.append(
            RuleOption(
                saved.get("rule", "saved_rule"),
                "rules.json saved suggestion",
                [dict(row) for row in saved.get("rows", [])],
                saved=True,
            )
        )

    if item.label == "薪資批次":
        salary_rows, salary_matched_keys = convert_salary_batch(item.source_rows, rules, einvoices)
        options.append(RuleOption("salary_batch", "薪資批次拆分", salary_rows, salary_matched_keys))
        options.append(RuleOption("manual_custom", "以薪資批次建議為底稿手動修改", salary_rows, salary_matched_keys))
        options.append(RuleOption("skip", "略過這批資料", []))
        return options

    if item.label == "拆分交易":
        split_rows, split_matched_keys = convert_generic_split(item.source_rows, rules, einvoices)
        options.append(RuleOption("generic_split", "合併為拆分交易(含手續費)", split_rows, split_matched_keys))
        options.append(RuleOption("manual_custom", "以拆分建議為底稿手動修改", split_rows, split_matched_keys))
        options.append(RuleOption("skip", "略過這批資料", []))
        return options

    row = item.source_rows[0]
    regular_rows, regular_matched_key = convert_regular(row, rules, einvoices)
    single_matched_keys = {regular_matched_key} if regular_matched_key else set()

    if "MTK股票" in row.note or row.subcategory == "股票":
        options.append(RuleOption("stock_transfer", "自動將 MTK 股票對應至資產帳戶(員工持股信託)", regular_rows, single_matched_keys))
    if row.category == "小孩" and row.subcategory == "學雜費" and school_fee_category(row):
        options.append(RuleOption("school_fee_by_child", "依孩子姓名分流學雜費類別", regular_rows, single_matched_keys))
    if row.category == "居家生活" and row.subcategory == "小渝生活費":
        options.append(RuleOption("life_expense_ivy", "生活費標題與 Ivy tag", regular_rows, single_matched_keys))
    if row.from_account and row.to_account:
        options.append(RuleOption("transfer_two_rows", "轉帳輸出為一出一入兩列", regular_rows, single_matched_keys))
    elif row.to_account and not row.from_account:
        options.append(RuleOption("income_category_mapping", "收入類別與帳戶對應", regular_rows, single_matched_keys))
    else:
        options.append(RuleOption("expense_category_mapping", "支出類別與帳戶對應", regular_rows, single_matched_keys))

    if not any(option.name == "manual_custom" for option in options):
        options.append(RuleOption("manual_custom", "以上方第一個建議為底稿手動修改", [dict(row) for row in options[0].rows], options[0].matched_einvoice_keys))
    options.append(RuleOption("skip", "略過這筆資料", []))
    return options


def print_source(rows: list[AndroRow], label: str) -> None:
    print(f"\n=== AndroMoney {label}: {len(rows)} source row(s) ===")
    for row in rows:
        print(f"#{row.index} Id={row.id}")
        print(f"  日期/時間: {row.date} {row.clock or '0000'}")
        print(f"  金額/幣別: {row.amount} {row.raw.get('幣別', '')}")
        print(f"  分類: {row.category} / {row.subcategory}")
        print(f"  轉出 -> 轉入: {row.from_account or '-'} -> {row.to_account or '-'}")
        print(f"  備註: {row.note or '-'}")
        print(f"  專案: {row.project or '-'}")
        print(f"  商家: {row.merchant or '-'}")


def print_candidate(rows: list[dict[str, str]]) -> None:
    print("\n--- Bluecoins 候選資料 (進階範本格式) ---")
    if not rows:
        print("(no output rows)")
        return
    for idx, row in enumerate(rows, start=1):
        print(f"Row #{idx}:")
        for field in BLUECOINS_FIELDS:
            print(f"  {field:20}: {row.get(field, '')}")


def print_rule_options(options: list[RuleOption]) -> None:
    print("--- Candidate rules ---")
    for idx, option in enumerate(options, start=1):
        marker = " saved" if option.saved else ""
        print(f"{idx}. {option.name}{marker} - {option.description}")


def edit_candidate(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    while True:
        target = input("要修改哪一列與欄位？格式 row.field=value，直接 Enter 結束修改：").strip()
        if not target:
            return rows
        if "=" not in target or "." not in target.split("=", 1)[0]:
            print("格式不正確，例如 1.類別=外食三餐")
            continue
        left, value = target.split("=", 1)
        row_no_text, field = left.split(".", 1)
        try:
            row_no = int(row_no_text) - 1
        except ValueError:
            print("列號需為數字。")
            continue
        if row_no < 0 or row_no >= len(rows):
            print("列號超出範圍。")
            continue
        if field not in BLUECOINS_FIELDS:
            print(f"未知欄位：{field}")
            continue
        rows[row_no][field] = value
        print_candidate(rows)


def remember_from_review(source_rows: list[AndroRow], candidate_rows: list[dict[str, str]], rules: Rules) -> None:
    if len(source_rows) != 1 or not candidate_rows:
        return
    source = source_rows[0]
    first = candidate_rows[0]
    if source.from_account and not source.to_account:
        rules.remember_account(source.from_account, first[BC_ACCOUNT])
    if source.to_account and not source.from_account:
        rules.remember_account(source.to_account, first[BC_ACCOUNT])
    if first[BC_TYPE] not in {"轉帳", "新帳戶"}:
        rules.remember_category(source.category, source.subcategory, first[BC_TYPE], first[BC_GROUP], first[BC_CATEGORY])


def interactive_review(
    items: Iterable[ReviewItem],
    rules: Rules,
    einvoices: dict = None,
) -> tuple[list[dict[str, str]], list[AndroRow], set[tuple[str, int]]]:
    accepted: list[dict[str, str]] = []
    skipped: list[AndroRow] = []
    matched_keys = set()

    for i, item in enumerate(items):
        print_source(item.source_rows, item.label)
        options = candidate_rule_options(item, rules, einvoices)
        print_rule_options(options)
        selected = choose_rule_option(options)
        if selected is None:
            for remaining_item in items[i:]:
                skipped.extend(remaining_item.source_rows)
            return accepted, skipped, matched_keys
        if selected.name == "skip":
            skipped.extend(item.source_rows)
            continue
        candidate_rows = [dict(row) for row in selected.rows]
        print_candidate(candidate_rows)
        edited = False
        while True:
            action = input("[a]接受 [e]修改 [r]換 rule [s]略過 [q]結束：").strip().lower() or "a"
            if action == "a":
                accepted.extend(candidate_rows)
                remember_from_review(item.source_rows, candidate_rows, rules)
                
                # 記錄匹配成功的發票 Key (從選定的 RuleOption 中取得)
                matched_keys.update(selected.matched_einvoice_keys)

                if edited:
                    save = input("要把這次修改保存為下次的建議 rule 嗎？[y/N] ").strip().lower()
                    if save == "y":
                        rules.remember_named_rule(
                            source_signature(item.source_rows),
                            selected.name,
                            source_summary(item.source_rows),
                            candidate_rows,
                        )
                rules.save()
                break
            if action == "e":
                candidate_rows = edit_candidate(candidate_rows)
                edited = True
                continue
            if action == "r":
                print_rule_options(options)
                selected = choose_rule_option(options)
                if selected is None:  # User quit in rule selection
                    for remaining_item in items[i:]:
                        skipped.extend(remaining_item.source_rows)
                    return accepted, skipped, matched_keys
                if selected.name == "skip":
                    skipped.extend(item.source_rows)
                    break
                candidate_rows = [dict(row) for row in selected.rows]
                edited = False
                print_candidate(candidate_rows)
                continue
            if action == "s":
                skipped.extend(item.source_rows)
                break
            if action == "q":
                # Save all remaining items as skipped
                for remaining_item in items[i:]:
                    skipped.extend(remaining_item.source_rows)
                return accepted, skipped, matched_keys
            print("請輸入 a/e/r/s/q。")
    return accepted, skipped, matched_keys


def choose_rule_option(options: list[RuleOption]) -> RuleOption | None:
    while True:
        choice = input("選擇 rule 編號，或 q 結束：").strip().lower()
        if choice == "q":
            return None
        try:
            idx = int(choice or "1") - 1
        except ValueError:
            print("請輸入 rule 編號。")
            continue
        if 0 <= idx < len(options):
            return options[idx]
        print("rule 編號超出範圍。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert AndroMoney CSV to reviewed Bluecoins CSV candidates.")
    parser.add_argument("-i", "--input", "--andro", dest="andro", default="AndroMoney_202605.csv", type=Path, help="AndroMoney cp950 CSV path")
    parser.add_argument("--bluecoins-reference", default="Bluecoins_CSV_Advanced_Template.csv", type=Path, help="Bluecoins sample CSV path")
    parser.add_argument("--output", default="bluecoins_import.csv", type=Path, help="Output Bluecoins CSV path")
    parser.add_argument("--rules", default="rules.json", type=Path, help="Persistent rules JSON path")
    parser.add_argument("--einvoice", nargs="?", const=Path("einvoice"), type=Path, help="電子發票明細 CSV 路徑或包含多個 CSV 的目錄 (預設為 'einvoice' 資料夾)")
    parser.add_argument("--default-blank-time", help="Default time for blank AndroMoney time fields, e.g. 00:00:00")
    parser.add_argument("--date-from", help="Only convert AndroMoney rows on or after YYYY-MM-DD")
    parser.add_argument("--date-to", help="Only convert AndroMoney rows on or before YYYY-MM-DD")
    parser.add_argument("--yes", action="store_true", help="Accept every proposed row without prompting")
    args = parser.parse_args()

    rules = Rules(args.rules)
    if args.default_blank_time:
        normalize_time(args.default_blank_time)
        rules.data["default_blank_time"] = args.default_blank_time
        rules.save()

    # 彙整所有電子發票明細
    einvoices = {}
    if args.einvoice:
        targets = [args.einvoice] if not args.einvoice.is_dir() else list(args.einvoice.glob("*.csv"))
        if args.einvoice.is_dir():
            print(f"從目錄加載發票檔: {[t.name for t in targets]}")
            
        for target in targets:
            file_data = read_einvoices(target)
            for key, val in file_data.items():
                if key in einvoices:
                    # 避免重複讀取相同內容
                    if val not in einvoices[key]:
                        einvoices[key] += "\n\n---\n\n" + val
                else:
                    einvoices[key] = val

    metadata, header, all_rows = read_andromoney(args.andro)
    rows = filter_rows_by_date(all_rows, args.date_from, args.date_to)
    reference_fields = read_bluecoins_header(args.bluecoins_reference)
    # 強制使用進階範本標頭以符合匯入需求
    if reference_fields != BLUECOINS_FIELDS:
        print(f"提示：參考檔 {args.bluecoins_reference} 標頭格式非進階範本，將強制輸出為 Bluecoins Advanced Template 格式。")
        fields = BLUECOINS_FIELDS
    else:
        fields = reference_fields

    # 建立輸出資料夾
    output_dir = args.andro.parent / f"{args.andro.stem}_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 在輸出檔名加上日期時間戳記
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = output_dir / f"{args.output.stem}_{timestamp}{args.output.suffix}"
    skipped_path = output_dir / f"skipped_{timestamp}.csv"
    unmatched_einvoice_path = output_dir / f"unmatched_einvoices_{timestamp}.txt"

    items = build_review_items(rows)

    # Auto-skip specific categories (Ignore "收取還款", "盤盈", "盤損")
    active_items = []
    auto_skipped_rows = []
    for item in items:
        if len(item.source_rows) == 1:
            row = item.source_rows[0]
            if category_key(row.category, row.subcategory) in AUTO_SKIP_CATEGORIES:
                auto_skipped_rows.extend(item.source_rows)
                continue
        active_items.append(item)
    items = active_items

    matched_einvoice_keys = set()

    if args.yes:
        accepted = []
        skipped = auto_skipped_rows
        for item in items:
            opt = candidate_rule_options(item, rules, einvoices)[0]
            if opt.name == "skip":
                skipped.extend(item.source_rows)
            else:
                accepted.extend(opt.rows)
                # 自動模式下記錄匹配成功的發票 (從選定的 RuleOption 中取得)
                matched_einvoice_keys.update(opt.matched_einvoice_keys)
    else:
        print(f"讀入 {len(rows)} 筆 AndroMoney 交易，準備逐筆審核。")
        accepted, manual_skipped, matched_einvoice_keys = interactive_review(items, rules, einvoices)
        skipped = auto_skipped_rows + manual_skipped

    write_bluecoins(output_path, accepted, fields)
    if skipped:
        write_andromoney(skipped_path, metadata, header, skipped)

    # 找出並輸出財政部有資料但 AndroMoney 沒對到的發票
    unmatched_count = 0
    if einvoices:
        unmatched_details = []
        for key, detail in einvoices.items():
            if key not in matched_einvoice_keys:
                # 檢查這張發票的日期是否在轉換區間內
                inv_date_dt = datetime.strptime(key[0], "%Y%m%d").date()
                start = parse_filter_date(args.date_from) if args.date_from else None
                end = parse_filter_date(args.date_to) if args.date_to else None
                
                if (not start or inv_date_dt >= start) and (not end or inv_date_dt <= end):
                    unmatched_details.append(f"--- 未匹配發票 (金額: {key[1]}) ---\n{detail}")
                    unmatched_count += 1
        
        if unmatched_details:
            unmatched_einvoice_path.write_text("\n\n".join(unmatched_details), encoding="utf-8")

    rules.save()
    print(f"已輸出 {len(accepted)} 筆 Bluecoins 候選資料：{output_path}")
    if skipped:
        print(f"已輸出 {len(skipped)} 筆略過/未處理資料：{skipped_path}")
    if unmatched_count > 0:
        print(f"注意：有 {unmatched_count} 筆財政部發票在 AndroMoney 中找不到對應消費，明細已輸出至：{unmatched_einvoice_path}")
    
    print(f"規則檔：{args.rules}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

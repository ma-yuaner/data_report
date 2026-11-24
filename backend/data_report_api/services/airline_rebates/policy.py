"""Deterministic extraction for the HKG26003 pilot document."""
from datetime import date
import re
from typing import BinaryIO

from pypdf import PdfReader

def require(pattern: str, text: str) -> re.Match[str]:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"政策结构未匹配：{pattern}")
    return match


def parse_policy(source: BinaryIO) -> dict:
    reader = PdfReader(source)
    if len(reader.pages) != 3:
        raise ValueError("预期 HKG26003 共三页")
    first, matrix, settlement = [re.sub(r"\s+", "", page.extract_text() or "") for page in reader.pages]
    for page in (first, matrix, settlement):
        require("HKG26003", page)
    dates = require(r"(\d{4})年(\d+)月(\d+)日[—–-](\d{4})年(\d+)月(\d+)日", first)
    start, end = [date(*map(int, dates.groups()[i:i + 3])).isoformat() for i in (0, 3)]
    for marker in ("以承运日期为准", "781票证", "KN", "MU/FM", "包机、包收入航班", "婴儿票", "集团客户", "追溯旧票"):
        require(re.escape(marker), first)
    for marker in ("不含税费及基础代理费", "四舍五入进整", "IATA"):
        require(re.escape(marker), settlement)

    def codes(pattern: str) -> list[str]:
        return require(pattern, matrix).group(1).rstrip("/").split("/")

    cabin_a = r"([A-Z](?:/[A-Z])+)"
    number = r"(\d+(?:\.\d+)?)"
    page_text = re.sub(r"\s+", " ", reader.pages[1].extract_text() or "")
    bounds = [
        ("T＞6000", 6000, None),
        ("3000＜T≤6000", 3000, 6000),
        ("1600＜T≤3000", 1600, 3000),
        ("600＜T≤1600", 600, 1600),
    ]
    tiers = []
    groups = None
    for marker, lower, upper in bounds:
        # The PDF text layer loses column separators when stripping line wrapping.
        # Separate numeric cells from the original page text before matching.

        marker_pattern = r"\s*".join(re.escape(char) for char in marker)
        pattern = marker_pattern + r"\s*" + cabin_a + (r"\s+" + number) * 5 + r"\s*" + cabin_a + (r"\s+" + number) * 4
        cells = require(pattern, page_text).groups()
        tier_groups = [cells[0].split("/"), cells[6].split("/")]
        if groups not in (None, tier_groups):
            raise ValueError("费率档位的舱位分组不一致")
        groups = tier_groups
        tiers.append({
            "lowerExclusive": lower * 10000,
            "upperInclusive": None if upper is None else upper * 10000,
            "ratesPercent": {"groupA": list(cells[1:6]), "groupB": [*cells[7:11], cells[5]]},
        })
    return {
        "policyId": "HKG26003", "flownStart": start, "flownEnd": end, "currency": "HKD",
        "ticketPrefix": "781", "carriers": ["MU", "FM"], "carrierException": "KN 且销售系统实际承运方为 MU/FM",
        "excludedCabins": require(r"([A-Z](?:/[A-Z])+)舱的运输收入不计量不计奖", first)[1].split("/"),
        "measureOnlyCabins": require(r"([A-Z]、[A-Z])舱的运输收入计量不计奖", first)[1].split("、"),
        "exclude": ["包机或包收入航班", "婴儿票", "纯内地客票", "非东上航实际承运航段"],
        "measureOnly": ["集团客户"], "originBasis": "换开追溯旧票", "periodBasis": "航段实际承运日",
        "agencyBasis": "IATA", "amountBasis": "净承运收入，扣税费及基础代理费，HKD 汇总后四舍五入进整",
        "routeCategories": ["longHaul", "shortHaul", "regionalNonDesignated", "regionalDesignated", "otherOrigin"],
        "longHaul": codes(r"国家代码为:([A-Z/]+)2\.国际非远程"),
        "shortHaul": codes(r"国家代码为:([A-Z/]+)，且全航程不包含远程点"),
        "regionalNonDesignated": {
            "HKG": codes(r"港澳非指定航线[:：]HKG-([A-Z/]+)始发"),
            "MFM": codes(r"MFM-([A-Z/]+)始发"),
        },
        "regionalDesignated": {"HKG": codes(r"香港指定航线[:：]HKG-([A-Z/]+)始发")},
        "cabinGroups": groups, "tiers": tiers,
        "evidencePages": {"eligibility": 1, "routesAndTiers": 2, "settlement": 3},
        "unresolved": ["最低档为严格大于 600 万，低于或等于门槛不推定费率", "政策未列出的港澳航线保留待核"],
    }

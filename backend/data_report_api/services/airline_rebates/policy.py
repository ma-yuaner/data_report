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


def source_clauses(first, matrix, settlement):
    """Capture full clauses from the text layer, including qualifications and exceptions."""
    patterns = (
        (first, {
            "period": r"适用日期[:：](.*?)[。]二、奖励办法",
            "agency": r"(香港营业部所辖指定代理人)使用",
            "stock": r"使用(东航（MU）\d{3}票证)销售",
            "scope": r"票证销售的(.*?)，并由",
            "carrier": r"(并由东上航实际承运的运输收入)。",
            "exception": r"(收入含实际承运分公司划为[A-Z]{2}但销售系统显示实际承运方为[A-Z]{2}/[A-Z]{2}的航班)。",
            "excluded": r"([A-Z](?:/[A-Z])+舱的运输收入不计量不计奖)",
            "charter": r"(包机、包收入航班)婴儿票",
            "infant": r"包收入航班(婴儿票)纯内地",
            "domestic": r"婴儿票(纯内地客票)代码共享",
            "non_operated": r"(代码共享航班及与外航联运航班中非东上航实际承运航段的运输收入)",
            "measure_only": r"([A-Z]、[A-Z]舱的运输收入计量不计奖)",
            "measure_clients": r"计量不计奖(集团客户的运输收入)注",
            "origin": r"注[:：](.*?销量还原，航程始发追溯旧票。)",
        }),
        (matrix, {
            "long": r"1\.(国际远程航线为.*?)(?=2\.国际非远程)",
            "short": r"2\.(国际非远程航线为.*?)(?=3\.地区航线)",
            "regional_scope": r"3\.(地区航线为.*?)(?=4\.地区航线)",
            "hkg_non": r"(HKG-[A-Z/]+始发的联程、单程、来回程、缺口程（包括客票中的中国大陆段）)",
            "mfm_non": r"(MFM-[A-Z/]+始发的联程、单程、来回程、缺口程（包括客票中的中国大陆段）)",
            "hkg_designated": r"(HKG-[A-Z/]+始发的联程、单程、来回程、缺口程（包括客票中的中国大陆段）)",
            "other_origin": r"6\.异地始发航线[:：](.*?。)",
        }),
        (settlement, {
            "revenue": r"3\.奖励的计算(.*?)三、奖励的发放",
            "payment": r"三、奖励的发放(.*?)四、财务结算",
            "rounding": r"四、财务结算[:：]1、(.*?)2、",
            "iata": r"2、(以代理人明细中的IATA号作为核算依据。)",
            "evaluation": r"五、评估机制(.*?。)",
        }),
    )
    clauses = {}
    for source, entries in patterns:
        for key, pattern in entries.items():
            text = source
            if key == "hkg_designated":
                text = source.split("5.地区航线", 1)[-1]
            clauses[key] = require(pattern, text)[1]
    return clauses


def parse_policy(source: BinaryIO) -> dict:
    reader = PdfReader(source)
    if len(reader.pages) != 3:
        raise ValueError("预期 HKG26003 共三页")
    first, matrix, settlement = [re.sub(r"\s+", "", page.extract_text() or "") for page in reader.pages]
    for page in (first, matrix, settlement):
        require("HKG26003", page)
    dates = require(r"(\d{4})年(\d+)月(\d+)日[—–-](\d{4})年(\d+)月(\d+)日", first)
    start, end = [date(*map(int, dates.groups()[i:i + 3])).isoformat() for i in (0, 3)]
    clauses = source_clauses(first, matrix, settlement)
    ticket_prefix = require(r"([0-9]{3})票证", clauses["stock"])[1]
    clauses["issue_date"] = clauses["period"]

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
        clauses[f"tier-{lower * 10000}"] = require(pattern, page_text)[0]
        tiers.append({
            "lowerExclusive": lower * 10000,
            "upperInclusive": None if upper is None else upper * 10000,
            "ratesPercent": {"groupA": list(cells[1:6]), "groupB": [*cells[7:11], cells[5]]},
        })
    return {
        "policyId": "HKG26003", "flownStart": start, "flownEnd": end, "currency": "HKD",
        "ticketPrefix": ticket_prefix, "carriers": ["MU", "FM"],
        "sourceClauses": clauses,
        "excludedCabins": require(r"([A-Z](?:/[A-Z])+)舱的运输收入不计量不计奖", first)[1].split("/"),
        "measureOnlyCabins": require(r"([A-Z]、[A-Z])舱的运输收入计量不计奖", first)[1].split("、"),
        "exclude": ["包机或包收入航班", "婴儿票", "纯内地客票", "非东上航实际承运航段"],
        "measureOnly": ["集团客户"], "originBasis": "换开追溯旧票", "periodBasis": "航段实际承运日",
        "agencyBasis": "IATA", "amountBasis": "净承运收入，扣税费及基础代理费，HKD 四舍五入进整",
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

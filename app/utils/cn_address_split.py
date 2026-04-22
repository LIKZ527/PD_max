"""
将中国常见「整行地址」粗分为省 / 市 / 区（县）与剩余详址。

用于 Excel 批量导入等场景；无法可靠拆分时返回 (None, None, None, 原文)，
由调用方走「仅名称 + 整行地址」极简落库。
"""

from __future__ import annotations

import re

# 直辖市：省、市字段在业务上常同为「xx市」
_MUNICIPAL = re.compile(
    r"^(?P<prov>(?:北京|上海|天津|重庆)市)"
    r"(?P<dist>[^省市区县]{0,20}?(?:区|县|旗))"
    r"(?P<detail>.*)$"
)

# 省 / 自治区 + 地级单位 + 县级区划 + 详址
_PROV = (
    r"(?P<prov>"
    r"[^省港澳台]+?省"
    r"|(?:内蒙古|广西|西藏|宁夏|新疆)(?:维吾尔|回族|壮族)?自治区"
    r"|香港特别行政区|澳门特别行政区"
    r")"
)

_STANDARD = re.compile(
    rf"^{_PROV}"
    r"(?P<city>.+?(?:市|自治州|地区|盟))"
    r"(?P<dist>.+?(?:区|县|旗|市))"
    r"(?P<detail>.*)$"
)


def split_cn_region_address(addr: str) -> tuple[str | None, str | None, str | None, str]:
    """
    :param addr: 已 strip 或含首尾空白的整行地址
    :return: (province, city, district, detail)；拆不出结构化四级时前三项为 None，最后一项为剩余全文
    """
    s = (addr or "").strip()
    if not s:
        return None, None, None, ""

    m = _MUNICIPAL.match(s)
    if m:
        prov = m.group("prov")
        dist = m.group("dist").strip()
        detail = (m.group("detail") or "").strip()
        if prov and dist:
            return prov, prov, dist, detail
        return None, None, None, s

    m = _STANDARD.match(s)
    if m:
        prov = m.group("prov").strip()
        city = m.group("city").strip()
        dist = m.group("dist").strip()
        detail = (m.group("detail") or "").strip()
        if prov and city and dist:
            return prov, city, dist, detail

    return None, None, None, s

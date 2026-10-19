"""日历门：优先 ADS 天气节假日表；表不可达时用内置 2026-09 错位与法定假窗口。"""
from __future__ import annotations

from datetime import date, timedelta


# 2026-09 中秋错位（方案 §5.1）
LUNAR_MISALIGN = {
    date(2026, 9, 25): "2025-10-06",
}

# 法定假日前后 1 日（示例：国庆；引擎按年扩展时可改 yaml）
FIXED_HOLIDAY_WINDOWS: list[tuple[date, date, str]] = [
    (date(2026, 10, 1), date(2026, 10, 7), "国庆节"),
]


def event_label_for(day: date) -> str:
    ds = day.isoformat()
    if day in LUNAR_MISALIGN:
        return f"农历错位，对照日 {LUNAR_MISALIGN[day]}"
    for start, end, name in FIXED_HOLIDAY_WINDOWS:
        if start - timedelta(days=1) <= day <= end + timedelta(days=1):
            return name
    return ""


def compare_day_primary(day: date) -> date:
    """定比：364 天前（同星期几）。固定假日窗口内仍用去年同日由调用方覆盖。"""
    return day - timedelta(days=364)


def compare_day_same_date_yoy(day: date) -> date:
    return day.replace(year=day.year - 1)


def compare_day_wow(day: date) -> date:
    return day - timedelta(days=7)

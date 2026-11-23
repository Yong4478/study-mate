"""
시계열 데이터 분석 (순수 파이썬 함수 - DB/AI와 무관해서 테스트하기 쉬움)

입력: [{"date": "2026-11-01", "value": 90, "memo": "..."}, ...]  (날짜 오름차순)
출력: 요약(summary) / 통계(statistics) 딕셔너리
"""
import statistics as stats
from collections import OrderedDict
from datetime import date, timedelta

from core.config import now_iso

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def minutes_to_text(minutes: float) -> str:
    """150 → '2시간 30분'"""
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}시간 {m}분"
    if h:
        return f"{h}시간"
    return f"{m}분"


def _avg(values: list[int]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def calc_trend(values: list[int]) -> tuple[str, str]:
    """
    최근 7개 기록 평균 vs 직전 7개 기록 평균을 비교해서 추세를 판단합니다.
    (기록이 14개보다 적으면 절반씩 나눠 비교)
    반환: (설명 문장, 방향 up/down/flat/unknown)
    """
    if len(values) < 4:
        return "데이터 부족 (최소 4개 이상 필요)", "unknown"

    window = 7 if len(values) >= 14 else len(values) // 2
    recent = values[-window:]
    previous = values[-2 * window : -window]
    recent_avg, prev_avg = _avg(recent), _avg(previous)

    if prev_avg == 0:
        change = 100.0 if recent_avg > 0 else 0.0
    else:
        change = (recent_avg - prev_avg) / prev_avg * 100

    if change >= 5:
        label, direction = "상승", "up"
    elif change <= -5:
        label, direction = "하락", "down"
    else:
        label, direction = "유지", "flat"

    text = (
        f"{label} (최근 {window}개 기록 평균 {recent_avg:.0f}분, "
        f"직전 {window}개 대비 {change:+.0f}%)"
    )
    return text, direction


def build_summary(records: list[dict]) -> dict:
    """GET /api/data/summary 의 결과이자, AI 시스템 프롬프트에 들어갈 요약"""
    if not records:
        return {
            "period": "데이터 없음",
            "count": 0,
            "unit": "분",
            "metrics": {"total": 0, "average": 0, "max": 0, "max_date": None, "min": 0, "min_date": None},
            "trend": "데이터 부족 (최소 4개 이상 필요)",
            "trend_direction": "unknown",
            "recent_7days": [],
            "monthly": [],
            "generated_at": now_iso(),
        }

    values = [r["value"] for r in records]
    max_rec = max(records, key=lambda r: r["value"])
    min_rec = min(records, key=lambda r: r["value"])
    trend_text, direction = calc_trend(values)

    # 월별 합계
    monthly: "OrderedDict[str, list[int]]" = OrderedDict()
    for r in records:
        monthly.setdefault(r["date"][:7], []).append(r["value"])

    return {
        "period": f"{records[0]['date']} ~ {records[-1]['date']}",
        "count": len(records),
        "unit": "분",
        "metrics": {
            "total": sum(values),
            "average": _avg(values),
            "max": max_rec["value"],
            "max_date": max_rec["date"],
            "min": min_rec["value"],
            "min_date": min_rec["date"],
        },
        "trend": trend_text,
        "trend_direction": direction,
        "recent_7days": [{"date": r["date"], "value": r["value"]} for r in records[-7:]],
        "monthly": [
            {"month": m, "total": sum(v), "average": _avg(v), "days": len(v)} for m, v in monthly.items()
        ],
        "generated_at": now_iso(),
    }


def _streaks(records: list[dict]) -> tuple[int, int]:
    """(현재 연속 공부 일수, 최장 연속 공부 일수). 1분 이상 공부한 날이 하루도 빠짐없이 이어져야 연속."""
    longest = current = 0
    prev_day: date | None = None
    for r in records:
        day = date.fromisoformat(r["date"])
        if r["value"] > 0:
            current = current + 1 if prev_day and day - prev_day == timedelta(days=1) and current > 0 else 1
        else:
            current = 0
        longest = max(longest, current)
        prev_day = day
    return current, longest


def build_statistics(records: list[dict], goal_minutes: int) -> dict:
    """(보너스) GET /api/data/statistics: 추가 지표 + 그래프용 시계열"""
    values = [r["value"] for r in records]
    count = len(values)
    achieved = sum(1 for v in values if v >= goal_minutes)
    study_days = sum(1 for v in values if v > 0)
    current_streak, longest_streak = _streaks(records)

    by_weekday: dict[str, list[int]] = {w: [] for w in WEEKDAYS}
    for r in records:
        by_weekday[WEEKDAYS[date.fromisoformat(r["date"]).weekday()]].append(r["value"])
    weekday_average = {w: _avg(v) for w, v in by_weekday.items()}
    filled = {w: a for w, a in weekday_average.items() if by_weekday[w]}
    best_weekday = max(filled, key=filled.get) if filled else None

    # 7개 기록 이동평균 (그래프에서 추세선으로 사용)
    series = []
    for i, r in enumerate(records):
        window = values[max(0, i - 6) : i + 1]
        series.append({"date": r["date"], "value": r["value"], "ma7": _avg(window)})

    return {
        "count": count,
        "goal_minutes": goal_minutes,
        "goal_achieved_days": achieved,
        "goal_achievement_rate": round(achieved / count * 100, 1) if count else 0.0,
        "study_days": study_days,
        "rest_days": count - study_days,
        "median": float(stats.median(values)) if values else 0.0,
        "std_dev": round(stats.pstdev(values), 1) if values else 0.0,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "weekday_average": weekday_average,
        "best_weekday": best_weekday,
        "series": series,
    }

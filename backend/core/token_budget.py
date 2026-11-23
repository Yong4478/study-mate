"""
AI 토큰 사용 한도 (과금/사용량 보호)

- AI 응답에 담겨 오는 usage.total_tokens 를 Firestore 'usage' 컬렉션에 월별로 누적합니다.
    usage / 2026-11  →  { total_tokens: 12345, calls: 40, updated_at: "..." }
- 이번 달 누적이 TOKEN_LIMIT(기본 100,000)에 도달하면 /api/chat 이 429 로 거절합니다.
- Firestore 에 저장하므로 Render 무료 서버가 잠들었다 깨어나도 누적값이 유지됩니다.
- 매월 1일에 새 문서가 쓰이므로 자동으로 초기화됩니다.
※ 코디세이 콘솔은 모델별 차감 배수(gpt-5-mini 0.5배 등)를 적용하므로,
  여기서 세는 '원래 토큰 수'가 콘솔 차감량보다 크거나 같습니다. (= 더 보수적으로 막음)
"""
import logging

from core import database
from core.config import now_iso, now_kst, settings

USAGE_COLLECTION = "usage"
logger = logging.getLogger("study-mate.tokens")


class TokenBudgetExceeded(Exception):
    pass


def _month() -> str:
    return now_kst().strftime("%Y-%m")


def _ref():
    return database.get_db().collection(USAGE_COLLECTION).document(_month())


def get_usage() -> dict:
    snap = _ref().get()
    data = (snap.to_dict() or {}) if snap.exists else {}
    used = int(data.get("total_tokens", 0))
    limit = settings.TOKEN_LIMIT
    return {
        "month": _month(),
        "used_tokens": used,
        "limit_tokens": limit,
        "remaining_tokens": max(0, limit - used) if limit > 0 else None,
        "calls": int(data.get("calls", 0)),
        "enabled": limit > 0,
    }


def check() -> None:
    """AI 를 부르기 전에 확인. 한도를 넘었으면 예외."""
    if settings.TOKEN_LIMIT <= 0:  # 0 이하이면 제한 끔
        return
    usage = get_usage()
    if usage["used_tokens"] >= settings.TOKEN_LIMIT:
        raise TokenBudgetExceeded(
            f"이번 달 AI 토큰 한도({settings.TOKEN_LIMIT:,}개)를 모두 사용했어요. "
            f"(사용 {usage['used_tokens']:,}개) 다음 달에 초기화됩니다."
        )


def add(tokens: int | None) -> None:
    """AI 응답을 받은 뒤 사용한 토큰을 더합니다. 기록 실패가 채팅을 막지 않도록 에러는 로그만 남깁니다."""
    if not tokens:
        return
    try:
        ref = _ref()
        snap = ref.get()
        data = (snap.to_dict() or {}) if snap.exists else {}
        ref.set(
            {
                "total_tokens": int(data.get("total_tokens", 0)) + int(tokens),
                "calls": int(data.get("calls", 0)) + 1,
                "updated_at": now_iso(),
            },
            merge=True,
        )
    except Exception as e:
        logger.warning("토큰 사용량 기록 실패: %s", e)

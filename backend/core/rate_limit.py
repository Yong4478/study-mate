"""
AI 호출 횟수 제한 (과금/사용량 보호)

- 1분에 사용자(IP)당 CHAT_LIMIT_PER_MINUTE 번
- 하루(서버 기준)에 전체 CHAT_LIMIT_PER_DAY 번
메모리에만 저장하므로 서버가 재시작되면 초기화됩니다. (입문용으로 충분)
"""
import time
from collections import defaultdict, deque
from threading import Lock

from core.config import now_kst, settings


class RateLimitExceeded(Exception):
    pass


_lock = Lock()
_per_ip: dict[str, deque] = defaultdict(deque)
_daily = {"date": None, "count": 0}


def check(client_key: str) -> None:
    now = time.monotonic()
    today = now_kst().date()
    with _lock:
        if _daily["date"] != today:
            _daily["date"], _daily["count"] = today, 0
        if _daily["count"] >= settings.CHAT_LIMIT_PER_DAY:
            raise RateLimitExceeded(f"오늘 AI 호출 한도({settings.CHAT_LIMIT_PER_DAY}회)를 모두 사용했어요. 내일 다시 이용해 주세요.")

        window = _per_ip[client_key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= settings.CHAT_LIMIT_PER_MINUTE:
            raise RateLimitExceeded(f"질문이 너무 빨라요. 1분에 {settings.CHAT_LIMIT_PER_MINUTE}번까지 가능해요. 잠시 후 다시 시도하세요.")

        window.append(now)
        _daily["count"] += 1


def reset() -> None:
    """테스트용"""
    with _lock:
        _per_ip.clear()
        _daily.update(date=None, count=0)

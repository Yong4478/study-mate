"""
환경 변수 설정을 한 곳에서 관리합니다.

- 로컬: backend/.env 파일에 값을 적으면 자동으로 읽습니다. (.env는 절대 GitHub에 올리지 않기!)
- 배포(Render): 대시보드의 Environment 메뉴에 같은 이름으로 등록합니다.
"""
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()  # .env 파일이 있으면 읽고, 없으면 그냥 넘어갑니다.

# 한국 시간(KST). zoneinfo 대신 고정 오프셋을 써서 윈도우에서도 추가 설치가 필요 없습니다.
KST = timezone(timedelta(hours=9))


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Settings:
    # ── AI (OpenAI 호환 API: 경남 코디세이 발급 키) ─────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    # 경남 코디세이: https://copa.codyssey.kr/v1  (콘솔 > 문서 탭의 Cursor/OpenAI Base URL)
    # 비워두면 OpenAI 공식 주소(https://api.openai.com/v1)를 사용합니다.
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "").strip()
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
    # 과금/사용량 보호: 답변 길이 상한
    OPENAI_MAX_TOKENS: int = _int_env("OPENAI_MAX_TOKENS", 1500)
    # (선택) 코디세이 콘솔에서 사용량을 묶어 보기 위한 세션 헤더 값 (영문·숫자·._:- 120자 이내)
    CODYSSEY_SESSION_ID: str = os.getenv("CODYSSEY_SESSION_ID", "").strip()

    # ── Firebase ──────────────────────────────────────────────
    # 둘 중 하나만 설정하면 됩니다.
    #  1) FIREBASE_SERVICE_ACCOUNT_JSON : 서비스 계정 키 JSON 내용 전체 (Render 추천)
    #  2) FIREBASE_SERVICE_ACCOUNT_PATH : 키 파일 경로 (로컬 추천, 예: ./firebase-key.json)
    FIREBASE_SERVICE_ACCOUNT_JSON: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    FIREBASE_SERVICE_ACCOUNT_PATH: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()

    # ── CORS ──────────────────────────────────────────────────
    # 쉼표로 구분. 예: https://study-mate.vercel.app,http://localhost:5500
    ALLOWED_ORIGINS: list[str] = [
        o.strip().rstrip("/")
        for o in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000",
        ).split(",")
        if o.strip()
    ]
    # (선택) Vercel 미리보기 주소처럼 바뀌는 도메인을 정규식으로 허용. 예: https://study-mate-.*\.vercel\.app
    ALLOWED_ORIGIN_REGEX: str | None = os.getenv("ALLOWED_ORIGIN_REGEX", "").strip() or None

    # ── 서비스 설정 ────────────────────────────────────────────
    DAILY_GOAL_MINUTES: int = _int_env("DAILY_GOAL_MINUTES", 120)  # 하루 목표 공부 시간(분)
    CHAT_HISTORY_LIMIT: int = _int_env("CHAT_HISTORY_LIMIT", 10)  # AI에게 함께 보낼 이전 메시지 수
    # 과금 보호: AI 호출 횟수 제한
    CHAT_LIMIT_PER_MINUTE: int = _int_env("CHAT_LIMIT_PER_MINUTE", 10)  # 사용자(IP)당 1분
    CHAT_LIMIT_PER_DAY: int = _int_env("CHAT_LIMIT_PER_DAY", 200)  # 서버 전체 하루
    # 과금 보호: 이번 달 AI 토큰 사용 한도 (0 이면 제한 없음)
    TOKEN_LIMIT: int = _int_env("TOKEN_LIMIT", 100_000)


settings = Settings()


def now_kst() -> datetime:
    return datetime.now(KST)


def now_iso() -> str:
    """저장용 시간 문자열 (예: 2026-11-22T18:40:00+09:00)"""
    return now_kst().isoformat(timespec="seconds")

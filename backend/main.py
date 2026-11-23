"""
스터디 메이트 API - 내 공부 기록을 아는 AI 코치

실행 (backend 폴더에서):
    uvicorn main:app --reload
문서:
    http://localhost:8000/docs  (Swagger UI)
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.ai_client import AIError, ai_status
from core.rate_limit import RateLimitExceeded
from core.token_budget import TokenBudgetExceeded
from core.config import now_iso, settings
from core.database import DatabaseNotConfigured
from routers import chat, conversations, data
from services.errors import ConflictError, NotFoundError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("study-mate")

app = FastAPI(
    title="Study Mate API",
    description=(
        "**내 공부 기록을 아는 AI 코치** 🧑‍🏫\n\n"
        "하루 공부 시간(분)을 기록하면, AI가 내 기록 요약을 보고 맞춤형으로 답해줍니다.\n\n"
        "- 데이터: `data` 컬렉션 (문서 ID = 날짜)\n"
        "- 대화: `conversations` 컬렉션\n"
        "- AI: OpenAI 호환 API (경남 코디세이 키)"
    ),
    version="1.0.0",
)


# ── 예상 못 한 에러도 JSON으로 응답 (CORS 헤더가 붙도록 CORS보다 안쪽에 둡니다) ──
@app.middleware("http")
async def catch_unexpected_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("처리되지 않은 에러: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다. 서버 로그를 확인하세요."})


# ── CORS: 프론트엔드(Vercel) 주소에서 오는 요청을 허용 ──
allow_all = "*" in settings.ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all else settings.ALLOWED_ORIGINS,
    allow_origin_regex=settings.ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,  # 쿠키를 쓰지 않으므로 False (단순하고 안전)
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 서비스 에러 → HTTP 상태 코드 ──
@app.exception_handler(NotFoundError)
async def not_found_handler(_: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def conflict_handler(_: Request, exc: ConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(AIError)
async def ai_error_handler(_: Request, exc: AIError):
    logger.warning("AI 호출 실패(%s): %s", exc.kind, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "kind": exc.kind})


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": str(exc)})


@app.exception_handler(TokenBudgetExceeded)
async def token_budget_handler(_: Request, exc: TokenBudgetExceeded):
    return JSONResponse(status_code=429, content={"detail": str(exc)})


@app.exception_handler(DatabaseNotConfigured)
async def db_config_handler(_: Request, exc: DatabaseNotConfigured):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── 라우터 등록 ──
app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.get("/", tags=["상태"], summary="환영 메시지")
def root():
    return {"service": "Study Mate API", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["상태"], summary="서버 상태 확인 (콜드스타트 깨우기용)")
def health():
    return {
        "status": "ok",
        "time": now_iso(),
        "firebase_configured": bool(settings.FIREBASE_SERVICE_ACCOUNT_JSON or settings.FIREBASE_SERVICE_ACCOUNT_PATH),
        "ai": ai_status(),
        "allowed_origins": ["*"] if allow_all else settings.ALLOWED_ORIGINS,
    }

"""AI 채팅 API 라우터"""
from fastapi import APIRouter, Request

from core import rate_limit
from schemas import ChatRequest, ChatResponse
from services import chat_service

router = APIRouter(prefix="/api", tags=["AI 채팅"])


@router.post("/chat", response_model=ChatResponse, summary="AI 대화 (데이터 요약 주입 + 자동 저장)")
def chat(req: ChatRequest, request: Request):
    """
    1. 데이터 요약 조회 → 2. 시스템 프롬프트에 삽입 → 3. GPT 호출 → 4. conversations 에 자동 저장

    - conversation_id 를 주면 이어서 대화하고, 없으면 새 대화를 만듭니다.
    - use_tools=true 이면 (보너스) AI 가 필요할 때 내부 기능을 도구로 호출합니다.
    - 과금 보호: 1분/하루 호출 횟수 제한 (초과 시 429)
    """
    rate_limit.check(client_ip(request))
    return chat_service.chat(req)


def client_ip(request: Request) -> str:
    # Render 같은 프록시 뒤에서는 실제 IP가 X-Forwarded-For 헤더에 들어옵니다.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

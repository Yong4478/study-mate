"""
대화 기록 API 라우터.

"대화 불러오기" 방식: (A) 채택
  - GET /api/conversations       → 목록만 (messages 미포함, 가볍게)
  - GET /api/conversations/{id}  → 해당 대화의 전체 messages
"""
from fastapi import APIRouter, Query

from schemas import Conversation, ConversationCreate, ConversationListItem, DeleteResult
from services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["대화 기록"])


@router.post("", response_model=Conversation, status_code=201, summary="대화 저장")
def create_conversation(payload: ConversationCreate):
    """채팅(POST /api/chat)은 자동 저장되므로, 이 API는 대화를 직접 저장하고 싶을 때 사용합니다."""
    messages = [m.model_dump() for m in payload.messages]
    return conversation_service.create_conversation(payload.title, messages)


@router.get("", response_model=list[ConversationListItem], summary="대화 목록 조회 (messages 미포함)")
def list_conversations(limit: int = Query(50, ge=1, le=100)):
    return conversation_service.list_conversations(limit)


@router.get("/{conversation_id}", response_model=Conversation, summary="특정 대화 불러오기 (전체 messages)")
def get_conversation(conversation_id: str):
    return conversation_service.get_conversation(conversation_id)


@router.delete("/{conversation_id}", response_model=DeleteResult, summary="대화 삭제")
def delete_conversation(conversation_id: str):
    return conversation_service.delete_conversation(conversation_id)

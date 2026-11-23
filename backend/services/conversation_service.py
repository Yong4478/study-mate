"""
대화 기록(conversations 컬렉션) 저장/조회/삭제.

Firestore 구조
  conversations (컬렉션)
   └─ (자동 ID)
        { title: "이번 달 공부 얼마나 했어?",
          messages: [ {role: "user", content: "...", created_at: "..."},
                      {role: "assistant", content: "...", created_at: "..."} ],
          message_count: 2, last_message: "...",
          created_at: "...", updated_at: "..." }
"""
from core import database
from core.config import now_iso
from services.errors import NotFoundError

LIST_FIELDS = ["title", "message_count", "last_message", "created_at", "updated_at"]


def _collection():
    return database.get_db().collection(database.CONVERSATIONS_COLLECTION)


def make_title(text: str, limit: int = 30) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _preview(messages: list[dict]) -> str:
    return make_title(messages[-1]["content"], 50) if messages else ""


def _normalize(messages: list[dict]) -> list[dict]:
    now = now_iso()
    return [
        {"role": m["role"], "content": m["content"], "created_at": m.get("created_at") or now}
        for m in messages
    ]


def create_conversation(title: str, messages: list[dict]) -> dict:
    msgs = _normalize(messages)
    if not title.strip():
        first_user = next((m["content"] for m in msgs if m["role"] == "user"), msgs[0]["content"])
        title = make_title(first_user)
    now = now_iso()
    data = {
        "title": title.strip(),
        "messages": msgs,
        "message_count": len(msgs),
        "last_message": _preview(msgs),
        "created_at": now,
        "updated_at": now,
    }
    ref = _collection().document()  # 자동 ID
    ref.set(data)
    return {"id": ref.id, **data}


def append_messages(conversation_id: str, new_messages: list[dict]) -> dict:
    ref = _collection().document(conversation_id)
    snap = ref.get()
    if not snap.exists:
        raise NotFoundError(f"대화({conversation_id})를 찾을 수 없습니다.")
    data = snap.to_dict()
    msgs = data.get("messages", []) + _normalize(new_messages)
    changes = {
        "messages": msgs,
        "message_count": len(msgs),
        "last_message": _preview(msgs),
        "updated_at": now_iso(),
    }
    ref.update(changes)
    return {"id": conversation_id, **data, **changes}


def list_conversations(limit: int = 50) -> list[dict]:
    """최근 대화 순. messages 는 빼고 가볍게 가져옵니다(select)."""
    query = (
        _collection()
        .select(LIST_FIELDS)
        .order_by("updated_at", direction="DESCENDING")
        .limit(limit)
    )
    items = []
    for doc in query.stream():
        d = doc.to_dict() or {}
        items.append(
            {
                "id": doc.id,
                "title": d.get("title", "(제목 없음)"),
                "message_count": d.get("message_count", 0),
                "last_message": d.get("last_message", ""),
                "created_at": d.get("created_at", ""),
                "updated_at": d.get("updated_at", ""),
            }
        )
    return items


def get_conversation(conversation_id: str) -> dict:
    snap = _collection().document(conversation_id).get()
    if not snap.exists:
        raise NotFoundError(f"대화({conversation_id})를 찾을 수 없습니다.")
    d = snap.to_dict()
    messages = d.get("messages", [])
    return {
        "id": snap.id,
        "title": d.get("title", ""),
        "messages": messages,
        "message_count": len(messages),
        "created_at": d.get("created_at", ""),
        "updated_at": d.get("updated_at", ""),
    }


def delete_conversation(conversation_id: str) -> dict:
    ref = _collection().document(conversation_id)
    if not ref.get().exists:
        raise NotFoundError(f"대화({conversation_id})를 찾을 수 없습니다.")
    ref.delete()
    return {"id": conversation_id, "deleted": True}

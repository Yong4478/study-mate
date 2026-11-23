"""
공부 기록(data 컬렉션) CRUD + 요약/통계/내보내기.

Firestore 구조
  data (컬렉션)
   └─ 2026-11-22 (문서 ID = 날짜 → 하루 1개 기록이 자연스럽게 보장됨)
        { date: "2026-11-22", value: 90, memo: "FastAPI 복습",
          created_at: "...", updated_at: "..." }
"""
import csv
import io
import json

from core import database
from core.config import now_iso, settings
from schemas import DataCreate, DataUpdate
from services.analysis import build_statistics, build_summary
from services.errors import ConflictError, NotFoundError


def _collection():
    return database.get_db().collection(database.DATA_COLLECTION)


def _to_record(doc) -> dict:
    d = doc.to_dict() or {}
    return {
        "id": doc.id,
        "date": d.get("date", doc.id),
        "value": int(d.get("value", 0)),
        "memo": d.get("memo", ""),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }


def list_records(start: str | None = None, end: str | None = None, order: str = "asc", limit: int | None = None) -> list[dict]:
    """날짜순 목록. start/end 는 'YYYY-MM-DD' 문자열(포함)."""
    docs = _collection().order_by("date").stream()
    records = [_to_record(doc) for doc in docs]
    # 데이터가 수백 개 수준이라 파이썬에서 거르는 편이 단순합니다.
    if start:
        records = [r for r in records if r["date"] >= start]
    if end:
        records = [r for r in records if r["date"] <= end]
    if order == "desc":
        records.reverse()
    if limit:
        records = records[:limit]
    return records


def create_record(payload: DataCreate) -> dict:
    doc_id = payload.date.isoformat()
    ref = _collection().document(doc_id)
    if ref.get().exists:
        raise ConflictError(f"{doc_id} 기록이 이미 있습니다. 수정(PUT /api/data/{doc_id})을 이용하세요.")
    now = now_iso()
    data = {"date": doc_id, "value": payload.value, "memo": payload.memo, "created_at": now, "updated_at": now}
    ref.set(data)
    return {"id": doc_id, **data}


def update_record(doc_id: str, payload: DataUpdate) -> dict:
    ref = _collection().document(doc_id)
    snap = ref.get()
    if not snap.exists:
        raise NotFoundError(f"{doc_id} 기록을 찾을 수 없습니다.")
    changes = {"value": payload.value, "memo": payload.memo, "updated_at": now_iso()}
    ref.update(changes)
    return {**_to_record(snap), **changes}


def delete_record(doc_id: str) -> dict:
    ref = _collection().document(doc_id)
    if not ref.get().exists:
        raise NotFoundError(f"{doc_id} 기록을 찾을 수 없습니다.")
    ref.delete()
    return {"id": doc_id, "deleted": True}


def get_summary() -> dict:
    return build_summary(list_records())


def get_statistics(goal_minutes: int | None = None, start: str | None = None, end: str | None = None) -> dict:
    return build_statistics(list_records(start=start, end=end), goal_minutes or settings.DAILY_GOAL_MINUTES)


def export_records(fmt: str = "csv") -> tuple[str, str, str]:
    """(본문, MIME 타입, 파일명) 반환"""
    records = [{"date": r["date"], "value": r["value"], "memo": r["memo"]} for r in list_records()]
    if fmt == "json":
        return json.dumps(records, ensure_ascii=False, indent=2), "application/json", "study_log.json"

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["date", "value", "memo"])
    writer.writeheader()
    writer.writerows(records)
    # ﻿(BOM): 엑셀에서 한글 메모가 깨지지 않게 해줍니다.
    return "﻿" + buf.getvalue(), "text/csv; charset=utf-8", "study_log.csv"

"""
데이터(공부 기록) API 라우터.

라우터는 "주소와 입출력 형식"만 담당하고, 실제 처리는 services/data_service.py 가 합니다.
※ /summary, /statistics, /export 는 /{id} 보다 위에 선언해야 경로가 헷갈리지 않습니다.
"""
import datetime as dt
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Path, Query, Response

from schemas import DataCreate, DataRecord, DataUpdate, DeleteResult, Statistics, Summary
from services import data_service

router = APIRouter(prefix="/api/data", tags=["데이터 (공부 기록)"])

# 문서 ID = 날짜 (YYYY-MM-DD). 형식이 다르면 422
DateId = Annotated[str, Path(pattern=r"^\d{4}-\d{2}-\d{2}$", description="문서 ID = 날짜 (YYYY-MM-DD)", examples=["2026-11-22"])]


@router.post("", response_model=DataRecord, status_code=201, summary="새 데이터 추가")
def create_data(payload: DataCreate):
    """같은 날짜가 이미 있으면 409 를 돌려줍니다."""
    return data_service.create_record(payload)


@router.get("", response_model=list[DataRecord], summary="데이터 목록 조회")
def list_data(
    start: Optional[dt.date] = Query(None, description="시작 날짜(포함)"),
    end: Optional[dt.date] = Query(None, description="끝 날짜(포함)"),
    order: Literal["asc", "desc"] = Query("asc", description="asc=오래된 순, desc=최신 순"),
    limit: Optional[int] = Query(None, ge=1, le=1000),
):
    return data_service.list_records(
        start=start.isoformat() if start else None,
        end=end.isoformat() if end else None,
        order=order,
        limit=limit,
    )


@router.get("/summary", response_model=Summary, summary="데이터 요약 (프롬프트 주입용)")
def get_summary():
    """기간, 개수, 합계/평균/최대/최소, 최근 추세, 최근 7개 기록, 월별 합계"""
    return data_service.get_summary()


@router.get("/statistics", response_model=Statistics, summary="(보너스) 상세 통계 + 그래프용 데이터")
def get_statistics(
    goal: Optional[int] = Query(None, ge=1, le=1440, description="하루 목표(분). 기본값은 서버 설정"),
    start: Optional[dt.date] = Query(None, description="이 날짜부터만 계산 (그래프 기간 필터)"),
    end: Optional[dt.date] = Query(None, description="이 날짜까지만 계산"),
):
    """목표 달성률, 연속 공부 일수, 요일별 평균, 중앙값/표준편차, 7개 기록 이동평균(그래프용)"""
    return data_service.get_statistics(
        goal, start.isoformat() if start else None, end.isoformat() if end else None
    )


@router.get("/export", summary="(보너스) 데이터 내보내기 CSV/JSON")
def export_data(format: Literal["csv", "json"] = Query("csv")):
    body, media_type, filename = data_service.export_records(format)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/{id}", response_model=DataRecord, summary="데이터 수정")
def update_data(id: DateId, payload: DataUpdate):
    return data_service.update_record(id, payload)


@router.delete("/{id}", response_model=DeleteResult, summary="데이터 삭제")
def delete_data(id: DateId):
    return data_service.delete_record(id)

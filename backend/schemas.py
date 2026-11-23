"""
Pydantic 스키마: 요청/응답 데이터의 "모양"과 "규칙"을 정의합니다.

FastAPI 는 요청이 들어오면 여기 정의된 규칙으로 자동 검증하고,
규칙에 맞지 않으면 라우터 코드가 실행되기 전에 422 에러를 돌려줍니다.
→ 잘못된 데이터가 DB에 들어가는 것을 막아줍니다.
"""
import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from core.config import now_kst

# ───────────────────────── 공부 기록 데이터 ─────────────────────────


class DataCreate(BaseModel):
    """POST /api/data 요청 본문"""

    date: dt.date = Field(..., description="공부한 날짜 (YYYY-MM-DD). 하루에 1개 기록", examples=["2026-11-22"])
    value: int = Field(..., ge=0, le=1440, description="공부 시간(분). 0~1440", examples=[90])
    memo: str = Field("", max_length=100, description="무엇을 공부했는지 (100자 이내)", examples=["FastAPI 라우터 복습"])

    @field_validator("date")
    @classmethod
    def not_future(cls, v: dt.date) -> dt.date:
        if v > now_kst().date():
            raise ValueError("미래 날짜는 기록할 수 없습니다.")
        return v

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, v: str) -> str:
        return v.strip()


class DataUpdate(BaseModel):
    """PUT /api/data/{id} 요청 본문 (날짜는 문서 ID라서 바꿀 수 없음)"""

    value: int = Field(..., ge=0, le=1440, examples=[120])
    memo: str = Field("", max_length=100, examples=["알고리즘 2문제"])

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, v: str) -> str:
        return v.strip()


class DataRecord(BaseModel):
    """응답으로 나가는 공부 기록 1건"""

    id: str = Field(..., description="문서 ID (= 날짜 문자열)")
    date: str
    value: int
    memo: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Metrics(BaseModel):
    total: int = 0
    average: float = 0
    max: int = 0
    max_date: Optional[str] = None
    min: int = 0
    min_date: Optional[str] = None


class DailyPoint(BaseModel):
    date: str
    value: int


class MonthlyStat(BaseModel):
    month: str
    total: int
    average: float
    days: int


class Summary(BaseModel):
    """GET /api/data/summary 응답 (시스템 프롬프트에 주입되는 요약)"""

    period: str = Field(..., examples=["2026-07-26 ~ 2026-11-22"])
    count: int
    unit: str = "분"
    metrics: Metrics
    trend: str = Field(..., examples=["상승 (최근 7일 평균 150분, 직전 7일 대비 +12%)"])
    trend_direction: Literal["up", "down", "flat", "unknown"]
    recent_7days: list[DailyPoint] = []
    monthly: list[MonthlyStat] = []
    generated_at: str


class Statistics(BaseModel):
    """GET /api/data/statistics 응답 (보너스: 추가 지표 + 그래프용 데이터)"""

    count: int
    goal_minutes: int
    goal_achieved_days: int
    goal_achievement_rate: float = Field(..., description="목표 달성률(%)")
    study_days: int = Field(..., description="공부한 날(1분 이상)")
    rest_days: int
    median: float
    std_dev: float
    current_streak: int = Field(..., description="마지막 기록일 기준 연속 공부 일수")
    longest_streak: int
    weekday_average: dict[str, float] = Field(..., description="요일별 평균(분)")
    best_weekday: Optional[str] = None
    series: list[dict] = Field(..., description="그래프용 [{date, value, ma7}]")


class DeleteResult(BaseModel):
    id: str
    deleted: bool = True


# ───────────────────────── 대화 기록 ─────────────────────────


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)
    created_at: Optional[str] = None


class ConversationCreate(BaseModel):
    """POST /api/conversations 요청 본문"""

    title: str = Field("", max_length=60, description="비우면 첫 질문으로 자동 생성")
    messages: list[Message] = Field(..., min_length=1, max_length=200)


class ConversationListItem(BaseModel):
    """
    GET /api/conversations 의 목록 항목.
    ※ 목록 응답에는 messages 를 넣지 않습니다(가볍게).
       전체 메시지는 GET /api/conversations/{id} 로 불러옵니다.
    """

    id: str
    title: str
    message_count: int
    last_message: str = Field("", description="마지막 메시지 미리보기(50자)")
    created_at: str
    updated_at: str


class Conversation(BaseModel):
    """GET /api/conversations/{id} 응답 (전체 메시지 포함)"""

    id: str
    title: str
    messages: list[Message]
    message_count: int
    created_at: str
    updated_at: str


# ───────────────────────── AI 채팅 ─────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, examples=["이번 달 공부 얼마나 했어?"])
    conversation_id: Optional[str] = Field(None, description="이어서 대화할 때 대화 ID. 없으면 새 대화를 만듭니다.")
    use_tools: bool = Field(False, description="(보너스) AI가 필요할 때 내부 기능을 도구로 호출")

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("메시지를 입력하세요.")
        return v


class ToolCallLog(BaseModel):
    name: str
    arguments: dict
    result_preview: str = ""


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    summary: Summary = Field(..., description="이번 답변에 주입된 데이터 요약")
    tool_calls: list[ToolCallLog] = []
    notice: Optional[str] = None
    model: str

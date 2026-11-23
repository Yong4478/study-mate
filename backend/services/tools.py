"""
(보너스) Function Calling 도구 정의.

AI 에게 "이런 기능들을 쓸 수 있어" 라고 JSON 스키마로 알려주면,
AI 가 질문을 보고 필요하다고 판단할 때 {"name": ..., "arguments": ...} 형태로 호출을 요청합니다.
실제 실행은 우리 서버가 하고(execute_tool), 결과를 다시 AI 에게 돌려줍니다.
"""
from datetime import date, timedelta

from services import conversation_service, data_service

MAX_RANGE_DAYS = 62

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_data_summary",
            "description": "공부 기록 전체 요약(기간, 개수, 합계/평균/최고/최저, 최근 추세, 월별 합계)을 조회한다. 전체적인 현황을 물을 때 사용.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": "요일별 평균, 연속 공부 일수(스트릭), 목표 달성률, 중앙값, 표준편차 같은 상세 통계를 조회한다. 요일/습관/목표 관련 질문에 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_minutes": {"type": "integer", "description": "하루 목표 공부 시간(분). 생략하면 서버 기본값"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_records",
            "description": "특정 기간의 날짜별 공부 기록(분, 메모)을 조회한다. '지난주', '10월 둘째 주', '특정 날짜' 처럼 요약에 없는 세부 내용이 필요할 때 사용. 최대 62일.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "시작 날짜 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "끝 날짜 YYYY-MM-DD (포함)"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_conversations",
            "description": "이전에 나눈 대화 목록(제목, 마지막 메시지, 날짜)을 조회한다. '예전에 내가 뭐 물어봤지?' 같은 질문에 사용.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "가져올 개수(기본 10, 최대 30)"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_conversation",
            "description": "특정 이전 대화의 메시지 내용을 조회한다. list_conversations 로 얻은 id 를 사용.",
            "parameters": {
                "type": "object",
                "properties": {"conversation_id": {"type": "string", "description": "대화 ID"}},
                "required": ["conversation_id"],
            },
        },
    },
]


def _get_records(start_date: str, end_date: str) -> dict:
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except (TypeError, ValueError):
        return {"error": "날짜는 YYYY-MM-DD 형식이어야 합니다."}
    if start > end:
        start, end = end, start
    if (end - start).days > MAX_RANGE_DAYS:
        start = end - timedelta(days=MAX_RANGE_DAYS)
    records = data_service.list_records(start=start.isoformat(), end=end.isoformat())
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "count": len(records),
        "total": sum(r["value"] for r in records),
        "records": [{"date": r["date"], "value": r["value"], "memo": r["memo"]} for r in records],
    }


def _get_conversation(conversation_id: str) -> dict:
    conv = conversation_service.get_conversation(conversation_id)
    conv["messages"] = [
        {"role": m["role"], "content": m["content"][:500]} for m in conv["messages"][-20:]
    ]
    return conv


def execute_tool(name: str, args: dict) -> dict:
    """AI가 요청한 도구를 실제로 실행합니다. 에러가 나도 AI가 이해할 수 있게 dict로 돌려줍니다."""
    try:
        if name == "get_data_summary":
            return data_service.get_summary()
        if name == "get_statistics":
            goal = args.get("goal_minutes")
            goal = int(goal) if isinstance(goal, (int, float)) and 1 <= goal <= 1440 else None
            stats = data_service.get_statistics(goal)
            stats.pop("series", None)  # 그래프용 긴 배열은 AI에게 필요 없음
            return stats
        if name == "get_records":
            return _get_records(args.get("start_date"), args.get("end_date"))
        if name == "list_conversations":
            limit = max(1, min(int(args.get("limit") or 10), 30))
            return {"conversations": conversation_service.list_conversations(limit)}
        if name == "get_conversation":
            return _get_conversation(str(args.get("conversation_id", "")))
        return {"error": f"알 수 없는 도구: {name}"}
    except Exception as e:  # 도구 하나가 실패해도 대화는 계속되도록
        return {"error": str(e)}

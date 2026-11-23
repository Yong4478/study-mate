"""
AI 채팅 (컨텍스트 주입 방식).

동작 흐름 (POST /api/chat)
  1) 데이터 요약 조회        → data_service.get_summary()  (= GET /api/data/summary 와 같은 함수)
  2) 요약을 시스템 프롬프트에 삽입 → build_system_prompt()
  3) GPT API 호출            → core.ai_client.chat_completion()
  4) 대화 내용 자동 저장      → conversation_service (conversations 컬렉션)
"""
import json
import logging

from core.ai_client import AIError, chat_completion
from core.config import now_iso, now_kst, settings
from schemas import ChatRequest
from services import conversation_service, data_service
from services.analysis import minutes_to_text
from services.tools import TOOLS, execute_tool

logger = logging.getLogger("study-mate.chat")
MAX_TOOL_ROUNDS = 3

SYSTEM_PROMPT_TEMPLATE = """당신은 '스터디 메이트'라는 공부 기록 분석 비서입니다.
사용자의 하루 공부 시간 기록(단위: 분)을 바탕으로 친근하고 구체적으로 답변하세요.

[오늘 날짜] {today}

[사용자 데이터 요약]
- 데이터 기간: {period}
- 총 레코드: {count}개
- 주요 지표: {metrics}
- 최근 트렌드: {trend}
- 최근 7개 기록: {recent}
- 월별 합계: {monthly}

위 데이터를 기반으로 맞춤형 답변을 제공하세요.
[답변 규칙]
1. 위 요약에 있는 숫자만 근거로 답하고, 없는 내용은 지어내지 마세요.
2. 분 단위는 필요하면 '2시간 30분'처럼 읽기 쉽게 바꿔 말하세요.
3. 3~5문장으로 짧게 답하고, 마지막에 실천할 수 있는 조언 한 줄을 덧붙이세요.{tool_rule}"""

TOOL_RULE = """
4. 요약에 없는 날짜별 세부 기록, 요일별 통계, 이전 대화 내용이 필요하면 제공된 도구를 호출해서 확인한 뒤,
   그 도구 결과도 근거로 사용해 답하세요."""


def build_system_prompt(summary: dict, use_tools: bool = False) -> str:
    """데이터 요약(summary)을 시스템 프롬프트 문자열에 끼워 넣습니다 = 컨텍스트 주입"""
    m = summary["metrics"]
    if summary["count"]:
        metrics = (
            f"합계 {m['total']}분({minutes_to_text(m['total'])}), 평균 {m['average']}분, "
            f"최고 {m['max']}분({m['max_date']}), 최저 {m['min']}분({m['min_date']})"
        )
    else:
        metrics = "아직 기록이 없습니다."
    recent = ", ".join(f"{p['date'][5:]} {p['value']}분" for p in summary["recent_7days"]) or "없음"
    monthly = ", ".join(
        f"{x['month']} {x['total']}분({x['days']}일, 하루 평균 {x['average']}분)" for x in summary["monthly"]
    ) or "없음"
    today = now_kst()
    weekday = "월화수목금토일"[today.weekday()]

    return SYSTEM_PROMPT_TEMPLATE.format(
        today=f"{today.date().isoformat()} ({weekday})",
        period=summary["period"],
        count=summary["count"],
        metrics=metrics,
        trend=summary["trend"],
        recent=recent,
        monthly=monthly,
        tool_rule=TOOL_RULE if use_tools else "",
    )


def _ask_plain(messages: list[dict]) -> str:
    message, _ = chat_completion(messages)
    return message.content


def _ask_with_tools(messages: list[dict]) -> tuple[str, list[dict]]:
    """AI가 도구 호출을 요청하면 실행해서 결과를 돌려주고, 최종 답변이 나올 때까지 반복합니다."""
    msgs = list(messages)
    logs: list[dict] = []

    for round_no in range(MAX_TOOL_ROUNDS + 1):
        # 마지막 라운드에서는 도구를 더 못 쓰게 해서 반드시 답변을 받습니다.
        tool_choice = "none" if round_no == MAX_TOOL_ROUNDS else "auto"
        message, _ = chat_completion(msgs, tools=TOOLS, tool_choice=tool_choice)
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return message.content, logs

        msgs.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(tc.function.name, args)
            result_json = json.dumps(result, ensure_ascii=False, default=str)[:6000]
            logger.info("[tool] %s(%s) -> %s", tc.function.name, args, result_json[:120])
            logs.append({"name": tc.function.name, "arguments": args, "result_preview": result_json[:150]})
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": result_json})

    return "도구 호출이 너무 많아 답변을 마무리하지 못했어요. 질문을 조금 더 구체적으로 해주세요.", logs


def chat(req: ChatRequest) -> dict:
    # 1) 데이터 요약 조회
    summary = data_service.get_summary()

    # 2) 요약을 시스템 프롬프트에 삽입
    system_prompt = build_system_prompt(summary, req.use_tools)

    # 이어지는 대화라면 이전 메시지도 함께 보내서 맥락을 유지
    conversation = None
    history: list[dict] = []
    if req.conversation_id:
        conversation = conversation_service.get_conversation(req.conversation_id)  # 없으면 404
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in conversation["messages"][-settings.CHAT_HISTORY_LIMIT :]
        ]
    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": req.message}]

    # 3) GPT API 호출
    tool_logs: list[dict] = []
    notice = None
    if req.use_tools:
        try:
            reply, tool_logs = _ask_with_tools(messages)
        except AIError as e:
            if e.kind != "bad_request":
                raise
            # 사용 중인 API가 도구 호출(tools)을 지원하지 않으면 기본 방식으로 다시 답변
            notice = "현재 API가 도구 호출을 지원하지 않아 기본(요약 주입) 방식으로 답변했어요."
            reply = _ask_plain(messages)
    else:
        reply = _ask_plain(messages)

    # 4) 대화 내용 자동 저장
    now = now_iso()
    new_messages = [
        {"role": "user", "content": req.message, "created_at": now},
        {"role": "assistant", "content": reply, "created_at": now},
    ]
    if conversation:
        conversation_service.append_messages(conversation["id"], new_messages)
        conversation_id = conversation["id"]
    else:
        conversation_id = conversation_service.create_conversation("", new_messages)["id"]

    return {
        "conversation_id": conversation_id,
        "reply": reply,
        "summary": summary,
        "tool_calls": tool_logs,
        "notice": notice,
        "model": settings.OPENAI_MODEL,
    }

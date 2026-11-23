"""
스터디 메이트 MCP 서버 (보너스: 멀티채널 연동)

배포된 백엔드 API를 MCP "도구"로 노출합니다.
→ Claude Desktop, MCP Inspector 같은 외부 클라이언트에서도
  "내 공부 요약 보여줘", "어제 90분 공부했다고 기록해줘" 같은 요청을 처리할 수 있어요.

실행
    pip install -r requirements.txt
    STUDY_MATE_API_URL=https://내-백엔드.onrender.com python server.py     (stdio 방식)

테스트 (Node 필요)
    npx @modelcontextprotocol/inspector python server.py
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer

API_URL = os.getenv("STUDY_MATE_API_URL", "http://localhost:8000").rstrip("/")

mcp = MCPServer("study-mate")


def call_api(method: str, path: str, body: dict | None = None, timeout: int = 90):
    """백엔드 REST API 호출 (표준 라이브러리만 사용)"""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API_URL + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode() or "null")
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        try:
            detail = json.loads(text).get("detail", text)
        except (json.JSONDecodeError, AttributeError):
            detail = text
        return {"error": f"HTTP {e.code}", "detail": detail}
    except urllib.error.URLError as e:
        return {"error": f"백엔드({API_URL})에 연결할 수 없습니다: {e.reason}. Render 무료 서버라면 1분 뒤 다시 시도하세요."}


@mcp.tool()
def get_data_summary() -> dict:
    """공부 기록 전체 요약(기간, 개수, 합계/평균/최고/최저, 최근 추세, 월별 합계)을 조회한다."""
    return call_api("GET", "/api/data/summary")


@mcp.tool()
def get_statistics(goal_minutes: int = 120) -> dict:
    """요일별 평균, 연속 공부 일수, 목표 달성률, 중앙값/표준편차 같은 상세 통계를 조회한다."""
    stats = call_api("GET", f"/api/data/statistics?goal={goal_minutes}")
    if isinstance(stats, dict):
        stats.pop("series", None)  # 그래프용 긴 배열은 제외
    return stats


@mcp.tool()
def get_records(start_date: str, end_date: str) -> dict:
    """특정 기간(YYYY-MM-DD ~ YYYY-MM-DD, 포함)의 날짜별 공부 기록(분, 메모)을 조회한다."""
    query = urllib.parse.urlencode({"start": start_date, "end": end_date})
    records = call_api("GET", f"/api/data?{query}")
    if isinstance(records, list):
        return {"count": len(records), "total_minutes": sum(r["value"] for r in records), "records": records}
    return records


@mcp.tool()
def add_record(date: str, minutes: int, memo: str = "") -> dict:
    """공부 기록을 추가한다. date=YYYY-MM-DD, minutes=공부한 시간(분), memo=공부한 내용."""
    return call_api("POST", "/api/data", {"date": date, "value": minutes, "memo": memo})


@mcp.tool()
def list_conversations(limit: int = 10) -> dict:
    """웹에서 AI 코치와 나눈 이전 대화 목록(제목, 마지막 메시지, 날짜)을 조회한다."""
    items = call_api("GET", f"/api/conversations?limit={max(1, min(limit, 100))}")
    return {"conversations": items} if isinstance(items, list) else items


@mcp.tool()
def get_conversation(conversation_id: str) -> dict:
    """특정 대화의 전체 메시지를 조회한다. (id 는 list_conversations 결과 사용)"""
    return call_api("GET", f"/api/conversations/{urllib.parse.quote(conversation_id)}")


@mcp.tool()
def ask_study_coach(question: str, use_tools: bool = False) -> dict:
    """웹 서비스의 AI 코치(POST /api/chat)에게 질문한다. 대화는 웹의 대화 기록에도 저장된다."""
    res = call_api("POST", "/api/chat", {"message": question, "use_tools": use_tools}, timeout=120)
    if isinstance(res, dict) and "reply" in res:
        return {"reply": res["reply"], "conversation_id": res["conversation_id"], "tool_calls": res.get("tool_calls", [])}
    return res


if __name__ == "__main__":
    mcp.run()  # 기본: stdio

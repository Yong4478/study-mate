"""
AI 호출 전용 모듈 (OpenAI 호환 API).

경남 코디세이에서 받은 키는 "OpenAI 방식"으로 호출합니다.
그래서 openai 라이브러리를 그대로 쓰고, 아래 3가지만 환경 변수로 바꿔 끼우면 됩니다.

    OPENAI_API_KEY   = 코디세이에서 받은 키
    OPENAI_BASE_URL  = https://copa.codyssey.kr/v1  (OpenAI 공식 키라면 비워두기)
    OPENAI_MODEL     = 사용할 모델 ID (예: gpt-5-mini)

다른 파일에서는 chat_completion(messages) 하나만 부르면 됩니다.
"""
from urllib.parse import urlparse

from openai import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from core import token_budget
from core.config import settings

_client = None
# 최신 모델(gpt-5, o 시리즈 등)은 max_tokens 대신 max_completion_tokens 를 요구합니다.
# 처음 거절당하면 자동으로 바꿔서 다시 시도하고, 이후에는 바뀐 값을 계속 씁니다.
_token_param = "max_tokens"


class AIError(RuntimeError):
    """AI 호출 실패. kind 로 원인을 구분합니다."""

    def __init__(self, message: str, kind: str = "server", status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status_code = status_code


def normalize_base_url(url: str) -> str:
    """사용자가 주소를 조금 다르게 붙여넣어도 동작하도록 정리합니다."""
    url = url.strip().rstrip("/")
    # 전체 엔드포인트를 붙여넣은 경우: .../v1/chat/completions → .../v1
    # 다른 엔드포인트 주소를 붙여넣은 경우: .../v1/chat/completions, .../v1/models → .../v1
    for suffix in ("/chat/completions", "/completions", "/models"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise AIError(
                "OPENAI_API_KEY 가 설정되지 않았습니다. 코디세이에서 받은 키를 .env(또는 Render 환경 변수)에 넣어주세요.",
                kind="config",
                status_code=500,
            )
        if not settings.OPENAI_API_KEY.isascii() or " " in settings.OPENAI_API_KEY:
            raise AIError(
                "OPENAI_API_KEY 에 한글/공백/따옴표 같은 잘못된 문자가 섞여 있어요. 키만 정확히 붙여넣으세요.",
                kind="config",
                status_code=500,
            )
        kwargs ={"api_key": settings.OPENAI_API_KEY, "timeout": 60, "max_retries": 1}
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = normalize_base_url(settings.OPENAI_BASE_URL)
        if settings.CODYSSEY_SESSION_ID:
            kwargs["default_headers"] = {"X-Codyssey-Session-Id": settings.CODYSSEY_SESSION_ID[:120]}
        _client = OpenAI(**kwargs)
    return _client


def ai_status() -> dict:
    """/health 에서 보여줄 AI 설정 상태 (키 값은 절대 노출하지 않음)"""
    host = urlparse(normalize_base_url(settings.OPENAI_BASE_URL)).netloc if settings.OPENAI_BASE_URL else "api.openai.com (기본값)"
    return {
        "api_key_set": bool(settings.OPENAI_API_KEY),
        "base_url_host": host,
        "model": settings.OPENAI_MODEL,
        "max_tokens": settings.OPENAI_MAX_TOKENS,
    }


def chat_completion(messages: list[dict], tools: list[dict] | None = None, tool_choice: str = "auto"):
    """
    Chat Completions API 호출.
    반환값: (message, usage)  - message.content 에 답변, message.tool_calls 에 도구 호출 요청
    """
    global _token_param
    client = get_client()

    params = {"model": settings.OPENAI_MODEL, "messages": messages}
    params[_token_param] = settings.OPENAI_MAX_TOKENS
    if tools:
        params["tools"] = tools
        params["tool_choice"] = tool_choice

    try:
        try:
            response = client.chat.completions.create(**params)
        except BadRequestError as e:
            # max_tokens 를 지원하지 않는 모델이면 max_completion_tokens 로 한 번 더 시도
            if _token_param == "max_tokens" and "max_tokens" in str(e):
                params.pop("max_tokens")
                params["max_completion_tokens"] = settings.OPENAI_MAX_TOKENS
                response = client.chat.completions.create(**params)
                _token_param = "max_completion_tokens"
            else:
                raise
    except AuthenticationError as e:
        raise AIError("API 키가 올바르지 않습니다(401). 코디세이에서 받은 키를 정확히 넣었는지 확인하세요.", "auth") from e
    except PermissionDeniedError as e:
        raise AIError("이 키로는 해당 모델을 쓸 권한이 없습니다(403). OPENAI_MODEL 을 확인하세요.", "auth") from e
    except NotFoundError as e:
        raise AIError("주소 또는 모델을 찾을 수 없습니다(404). OPENAI_BASE_URL 과 OPENAI_MODEL 을 확인하세요.", "not_found") from e
    except RateLimitError as e:
        raise AIError("요청 한도를 초과했습니다(429). 잠시 후 다시 시도하세요.", "rate_limit", 429) from e
    except BadRequestError as e:
        raise AIError(f"AI 요청 형식 오류(400): {e}", "bad_request") from e
    except APIConnectionError as e:
        cause = e.__cause__ or e.__context__ or e
        raise AIError(
            f"AI 서버에 연결할 수 없습니다. OPENAI_BASE_URL 주소를 확인하세요. "
            f"(요청 주소: {getattr(client, 'base_url', '?')} / 원인: {type(cause).__name__}: {cause})",
            "connection",
            504,
        ) from e
    except APIError as e:
        raise AIError(f"AI 서버 오류: {e}", "server") from e

    if isinstance(response, (str, bytes)) or not hasattr(response, "choices"):
        raise AIError(
            "AI 서버가 OpenAI 형식이 아닌 응답을 보냈어요. OPENAI_BASE_URL 이 '/v1' 로 끝나는지 확인하세요. "
            "(/models, /chat/completions 같은 뒷부분은 빼야 합니다)",
            "bad_response",
        )
    if not response.choices:
        raise AIError("AI 서버가 빈 응답을 보냈습니다.", "server")
    usage = getattr(response, "usage", None)
    token_budget.add(getattr(usage, "total_tokens", None))  # 이번 달 토큰 사용량 누적
    choice = response.choices[0]
    message = choice.message
    if not message.content and not getattr(message, "tool_calls", None):
        hint = " (OPENAI_MAX_TOKENS 를 늘려보세요)" if choice.finish_reason == "length" else ""
        message.content = f"답변을 만들지 못했어요{hint}. 다시 질문해 주세요."
    return message, usage

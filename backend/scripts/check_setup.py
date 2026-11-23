"""
설정 점검 스크립트 - "키 넣었는데 왜 안 돼요?" 를 1분 만에 확인합니다.

사용법 (backend 폴더에서):
    python -m scripts.check_setup          # 환경 변수 + Firebase + AI 채팅 + 도구 호출 지원 여부
    python -m scripts.check_setup --ai     # AI만 확인
"""
import argparse
import sys

from core.config import settings


def mask(value: str) -> str:
    return f"{value[:6]}…({len(value)}자)" if value else "(비어 있음)"


def check_env() -> None:
    print("① 환경 변수")
    print(f"   OPENAI_API_KEY   : {mask(settings.OPENAI_API_KEY)}")
    print(f"   OPENAI_BASE_URL  : {settings.OPENAI_BASE_URL or '(비어 있음 → OpenAI 공식 주소 사용)'}")
    print(f"   OPENAI_MODEL     : {settings.OPENAI_MODEL}")
    fb = "JSON 값" if settings.FIREBASE_SERVICE_ACCOUNT_JSON else settings.FIREBASE_SERVICE_ACCOUNT_PATH or "(비어 있음)"
    print(f"   FIREBASE 키      : {fb}")
    print(f"   ALLOWED_ORIGINS  : {settings.ALLOWED_ORIGINS}")


def check_firebase() -> bool:
    print("\n② Firebase Firestore 연결")
    try:
        from core.database import DATA_COLLECTION, get_db

        docs = list(get_db().collection(DATA_COLLECTION).limit(5).stream())
        print(f"   ✅ 연결 성공 ('{DATA_COLLECTION}' 컬렉션에서 문서 {len(docs)}개 읽음)")
        if not docs:
            print("   💡 데이터가 비어 있어요 → python -m scripts.seed_data 로 샘플을 넣어보세요.")
        return True
    except Exception as e:
        print(f"   ❌ 실패: {e}")
        print("   💡 Firebase 콘솔에서 Firestore Database 를 '만들기' 했는지, 키 파일 경로가 맞는지 확인하세요.")
        return False


def check_ai() -> bool:
    print("\n③ AI 채팅 호출")
    from core.ai_client import AIError, chat_completion, get_client

    try:
        client = get_client()
    except AIError as e:
        print(f"   ❌ {e.message}")
        return False

    try:  # 일부 OpenAI 호환 서버는 모델 목록 API를 지원하지 않아도 정상입니다.
        names = sorted(m.id for m in client.models.list().data)
        print(f"   ℹ️  사용 가능한 모델 {len(names)}개: {', '.join(names[:8])}{' …' if len(names) > 8 else ''}")
    except Exception:
        print("   ℹ️  모델 목록 조회는 지원하지 않는 서버예요. (채팅만 되면 괜찮습니다)")

    try:
        message, usage = chat_completion([{"role": "user", "content": "공부하는 학생에게 한 문장으로 응원해줘."}])
        print(f"   ✅ 응답: {message.content.strip()}")
        if usage:
            print(f"   ℹ️  토큰 사용량: {getattr(usage, 'total_tokens', '?')}")
    except AIError as e:
        print(f"   ❌ {e.message}")
        return False

    print("\n④ (보너스) 도구 호출(Function Calling) 지원 여부")
    tools = [{
        "type": "function",
        "function": {
            "name": "get_today_minutes",
            "description": "오늘 공부한 시간(분)을 조회한다",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }]
    try:
        message, _ = chat_completion([{"role": "user", "content": "오늘 공부 시간 조회해줘"}], tools=tools)
        if getattr(message, "tool_calls", None):
            print(f"   ✅ 지원함 (AI가 '{message.tool_calls[0].function.name}' 호출을 요청)")
        else:
            print("   ⚠️  호출 요청이 없었어요. 모델에 따라 도구를 덜 쓰기도 합니다.")
    except AIError as e:
        print(f"   ⚠️  지원하지 않는 것 같아요: {e.message}")
        print("      → 채팅 화면의 '도구 호출 모드'를 꺼두면 기본 기능은 모두 정상 동작합니다.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true", help="AI만 확인")
    args = parser.parse_args()

    check_env()
    ok = True
    if not args.ai:
        ok = check_firebase() and ok
    ok = check_ai() and ok
    print("\n🎉 모든 점검 통과!" if ok else "\n위의 ❌ 항목을 먼저 해결하세요.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

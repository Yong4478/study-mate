"""
Firebase Firestore 연결.

서비스 계정 키는 코드에 적지 않고 환경 변수로만 받습니다.
처음 get_db()가 호출될 때 한 번만 연결하고, 이후에는 같은 연결을 재사용합니다.
"""
import json
import os

from core.config import settings

# 컬렉션 이름 (과제 요구사항: data / conversations)
DATA_COLLECTION = "data"
CONVERSATIONS_COLLECTION = "conversations"

_db = None


class DatabaseNotConfigured(RuntimeError):
    """Firebase 환경 변수가 없을 때 발생하는 에러"""


def _load_credentials():
    from firebase_admin import credentials

    raw = settings.FIREBASE_SERVICE_ACCOUNT_JSON
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as e:
            raise DatabaseNotConfigured(
                "FIREBASE_SERVICE_ACCOUNT_JSON 값이 올바른 JSON이 아닙니다. "
                "키 파일 내용을 { 부터 } 까지 통째로 붙여넣었는지 확인하세요."
            ) from e
        return credentials.Certificate(info)

    path = settings.FIREBASE_SERVICE_ACCOUNT_PATH
    if path:
        if not os.path.exists(path):
            raise DatabaseNotConfigured(f"서비스 계정 키 파일을 찾을 수 없습니다: {path}")
        return credentials.Certificate(path)

    raise DatabaseNotConfigured(
        "Firebase 설정이 없습니다. .env 에 FIREBASE_SERVICE_ACCOUNT_PATH 또는 "
        "FIREBASE_SERVICE_ACCOUNT_JSON 을 설정하세요."
    )


def get_db():
    """Firestore 클라이언트를 돌려줍니다."""
    global _db
    if _db is None:
        import firebase_admin
        from firebase_admin import firestore

        if not firebase_admin._apps:  # 이미 초기화되어 있으면 다시 하지 않음
            firebase_admin.initialize_app(_load_credentials())
        _db = firestore.client()
    return _db

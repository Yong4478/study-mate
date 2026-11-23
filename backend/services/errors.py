"""서비스 계층에서 쓰는 에러. main.py 에서 HTTP 상태 코드로 바꿔서 응답합니다."""


class NotFoundError(Exception):
    """찾는 문서가 없음 → 404"""


class ConflictError(Exception):
    """이미 존재함 → 409"""

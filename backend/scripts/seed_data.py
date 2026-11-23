"""
샘플 데이터 생성 · 분석 · Firestore 업로드 스크립트

주제: "하루 공부 시간 기록" (단위: 분) - 입문자도 이해하기 쉬운 시계열 데이터
     (date, value, memo) = (날짜, 공부한 분, 공부한 내용)

사용법 (backend 폴더에서 실행):
    python -m scripts.seed_data --dry-run                 # 생성 + 분석 결과만 출력 (Firebase 불필요)
    python -m scripts.seed_data --save-csv data/my.csv    # 생성한 데이터를 CSV로 저장
    python -m scripts.seed_data                           # 오늘 기준 최근 120일 데이터를 Firestore에 업로드
    python -m scripts.seed_data --from-csv data/study_log_sample.csv   # CSV 파일을 업로드
    python -m scripts.seed_data --clear                   # data 컬렉션을 비운 뒤 업로드
"""
import argparse
import csv
import json
import random
from datetime import date, timedelta

from core.config import now_iso, now_kst, settings
from services.analysis import build_statistics, build_summary, minutes_to_text

# 공부 진도(앞쪽 → 뒤쪽으로 갈수록 심화)
CURRICULUM = [
    ["Python 기초 문법", "변수와 자료형", "조건문/반복문", "리스트·딕셔너리"],
    ["함수와 모듈", "파일 입출력", "예외 처리", "가상환경(venv)"],
    ["Git/GitHub", "HTTP와 REST", "FastAPI 입문", "Pydantic 검증"],
    ["Firestore CRUD", "HTML/CSS 레이아웃", "JavaScript fetch", "CORS 이해"],
    ["OpenAI API 호출", "프롬프트 설계", "Render 배포", "Vercel 배포", "알고리즘 문제 풀이"],
]


def generate(days: int = 120, end: date | None = None, seed: int = 42) -> list[dict]:
    """조금씩 공부 시간이 늘어나는(상승 추세) 현실적인 공부 기록을 만듭니다."""
    rng = random.Random(seed)
    end = end or now_kst().date()
    start = end - timedelta(days=days - 1)
    weekday_factor = [1.0, 1.05, 1.0, 0.95, 0.85, 0.75, 0.6]  # 월~일 (주말엔 조금 덜)
    records = []
    for i in range(days):
        day = start + timedelta(days=i)
        progress = i / max(days - 1, 1)  # 0 → 1
        base = 70 + 90 * progress  # 70분에서 160분까지 점점 증가
        value = base * weekday_factor[day.weekday()] + rng.gauss(0, 22)
        stage = CURRICULUM[min(int(progress * len(CURRICULUM)), len(CURRICULUM) - 1)]
        memo = rng.choice(stage)

        roll = rng.random()
        if roll < 0.07:  # 가끔 쉬는 날
            value, memo = 0, "휴식"
        elif roll > 0.97:  # 가끔 몰입한 날
            value *= 1.9
            memo = f"{memo} (몰입 데이!)"
        value = int(max(0, min(600, round(value / 5) * 5)))  # 5분 단위
        records.append({"date": day.isoformat(), "value": value, "memo": memo})
    return records


def load_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        rows = [{"date": r["date"], "value": int(r["value"]), "memo": r.get("memo", "")} for r in csv.DictReader(f)]
    return sorted(rows, key=lambda r: r["date"])


def save_csv(records: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "value", "memo"])
        writer.writeheader()
        writer.writerows(records)
    print(f"💾 CSV 저장: {path} ({len(records)}행)")


def print_analysis(records: list[dict]) -> None:
    s = build_summary(records)
    st = build_statistics(records, settings.DAILY_GOAL_MINUTES)
    m = s["metrics"]
    print("\n📊 분석 결과 (= GET /api/data/summary)")
    print(f"  기간   : {s['period']}  ({s['count']}개)")
    print(f"  합계   : {m['total']}분 ({minutes_to_text(m['total'])})")
    print(f"  평균   : {m['average']}분")
    print(f"  최고   : {m['max']}분 ({m['max_date']}) / 최저: {m['min']}분 ({m['min_date']})")
    print(f"  추세   : {s['trend']}")
    print("  월별   : " + ", ".join(f"{x['month']} {x['total']}분" for x in s["monthly"]))
    print("\n📈 추가 지표 (= GET /api/data/statistics)")
    print(f"  목표 {st['goal_minutes']}분 달성률: {st['goal_achievement_rate']}%  ({st['goal_achieved_days']}일)")
    print(f"  연속 공부: 현재 {st['current_streak']}일 / 최장 {st['longest_streak']}일")
    print(f"  요일별 평균: {json.dumps(st['weekday_average'], ensure_ascii=False)} → 최고 {st['best_weekday']}요일")


def upload(records: list[dict], clear: bool = False) -> None:
    from core.database import DATA_COLLECTION, get_db

    db = get_db()
    col = db.collection(DATA_COLLECTION)
    if clear:
        deleted = 0
        for doc in col.stream():
            doc.reference.delete()
            deleted += 1
        print(f"🧹 기존 문서 {deleted}개 삭제")

    now = now_iso()
    batch, pending = db.batch(), 0
    for r in records:
        batch.set(col.document(r["date"]), {**r, "created_at": now, "updated_at": now})
        pending += 1
        if pending == 400:  # Firestore 배치는 최대 500개
            batch.commit()
            batch, pending = db.batch(), 0
    if pending:
        batch.commit()
    print(f"✅ Firestore '{DATA_COLLECTION}' 컬렉션에 {len(records)}개 업로드 완료")


def main() -> None:
    parser = argparse.ArgumentParser(description="공부 기록 샘플 데이터 생성/분석/업로드")
    parser.add_argument("--days", type=int, default=120, help="생성할 일수 (기본 120, 과제 조건: 100 이상)")
    parser.add_argument("--end", type=str, default=None, help="마지막 날짜 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--from-csv", type=str, default=None, help="생성 대신 CSV 파일 사용")
    parser.add_argument("--save-csv", type=str, default=None, help="데이터를 CSV로 저장")
    parser.add_argument("--dry-run", action="store_true", help="업로드하지 않고 분석 결과만 출력")
    parser.add_argument("--clear", action="store_true", help="업로드 전에 data 컬렉션 비우기")
    args = parser.parse_args()

    if args.from_csv:
        records = load_csv(args.from_csv)
    else:
        end = date.fromisoformat(args.end) if args.end else None
        records = generate(args.days, end)
    print(f"🗂  데이터 {len(records)}개 준비 ({records[0]['date']} ~ {records[-1]['date']})")

    print_analysis(records)
    if args.save_csv:
        save_csv(records, args.save_csv)
    if not args.dry_run:
        upload(records, clear=args.clear)


if __name__ == "__main__":
    main()

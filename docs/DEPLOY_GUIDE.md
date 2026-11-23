# 🚀 배포 가이드 (Firebase → GitHub → Render → Vercel)

처음 하는 사람도 순서대로 따라 하면 되도록 정리했습니다. 전체 소요 시간은 30~40분 정도입니다.

```
① Firebase 준비 → ② 로컬에서 동작 확인 → ③ GitHub 업로드 → ④ Render(백엔드) → ⑤ Vercel(프론트) → ⑥ CORS 연결
```

---

## 1. Firebase 준비

1. https://console.firebase.google.com 접속 → **프로젝트 만들기** → 이름 `study-mate` (Google 애널리틱스는 꺼도 됩니다)
2. 왼쪽 메뉴 **빌드 → Firestore Database → 데이터베이스 만들기**
   - 위치: `asia-northeast3 (서울)`
   - **프로덕션 모드**로 시작 (서버의 Admin SDK만 접근하므로 브라우저 직접 접근은 막아두는 게 안전)
3. 왼쪽 위 ⚙️ **프로젝트 설정 → 서비스 계정** 탭 → **새 비공개 키 생성** → JSON 파일 다운로드
4. 다운로드한 파일 이름을 `firebase-key.json` 으로 바꿔 `backend/` 폴더에 넣기
   - ⚠️ 이 파일은 비밀번호와 같습니다. `.gitignore` 에 등록되어 있어 GitHub에 올라가지 않습니다.

## 2. 로컬에서 먼저 확인

```bash
cd backend
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # Windows: copy .env.example .env
```

`.env` 에서 `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` 을 코디세이에서 받은 값으로 채우고:

```bash
python -m scripts.check_setup     # ✅ 가 모두 뜨면 OK
python -m scripts.seed_data       # Firestore 에 120일치 샘플 업로드
uvicorn main:app --reload         # http://localhost:8000/docs
```

새 터미널에서 `cd frontend/public && python -m http.server 5500` → http://localhost:5500 에서 채팅이 되면 배포 준비 완료!

> 💡 로컬과 배포 서버는 **같은 Firestore** 를 쓰므로, 로컬에서 넣은 샘플 데이터가 배포 사이트에도 그대로 보입니다.

## 3. GitHub 업로드

```bash
cd study-mate          # 프로젝트 최상위 폴더
git init
git add .
git status             # ⚠️ .env, firebase-key.json 이 목록에 "없는지" 꼭 확인!
git commit -m "스터디 메이트: 내 공부 기록을 아는 AI 코치"
git branch -M main
git remote add origin https://github.com/내아이디/study-mate.git
git push -u origin main
```

## 4. Render (백엔드)

1. https://render.com → GitHub 계정으로 로그인
2. **New + → Web Service** → 방금 올린 저장소 선택
3. 설정 입력

| 항목 | 값 |
|---|---|
| Name | `study-mate-api` (주소가 `https://study-mate-api.onrender.com` 처럼 됨) |
| Region | Singapore (한국과 가장 가까움) |
| Branch | `main` |
| **Root Directory** | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | **Free** |

4. **Environment Variables** (Advanced → Add Environment Variable)

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.8` |
| `OPENAI_API_KEY` | 코디세이 키 |
| `OPENAI_BASE_URL` | 코디세이 API 주소 (없으면 추가하지 않기) |
| `OPENAI_MODEL` | 예: `gpt-4o-mini` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | `firebase-key.json` 파일을 메모장으로 열어 **`{` 부터 `}` 까지 전부** 복사해서 붙여넣기 |
| `ALLOWED_ORIGINS` | 일단 `http://localhost:5500` (6단계에서 Vercel 주소 추가) |

   > 다른 방법: Render의 **Secret Files** 에 `firebase-key.json` 을 올리고
   > `FIREBASE_SERVICE_ACCOUNT_PATH=/etc/secrets/firebase-key.json` 으로 설정해도 됩니다.

5. **Create Web Service** → 로그에 `Application startup complete` 가 보이면 성공
6. 브라우저에서 `https://study-mate-api.onrender.com/docs` → Swagger UI 확인
   `GET /api/data/summary` → **Try it out → Execute** 로 요약이 나오는지 확인

> 이 저장소의 `render.yaml` 을 쓰면 **New + → Blueprint** 로 위 설정을 한 번에 만들 수도 있습니다. (비밀 값은 직접 입력)

### 콜드스타트(첫 요청 지연) 대응

Render 무료 플랜은 15분 동안 요청이 없으면 잠들고, 다음 첫 요청에서 깨어나느라 최대 1분 정도 걸립니다.
- 프론트엔드: 접속하면 `/health` 로 먼저 서버를 깨우고, 2.5초 넘게 걸리면 **"서버를 깨우는 중이에요"** 배너를 표시합니다. 채팅이 9초 넘게 걸리면 말풍선에도 안내가 뜹니다.
- (선택) 발표/시연 직전에 `/health` 주소를 한 번 열어두면 바로 빠르게 동작합니다.

## 5. Vercel (프론트엔드)

1. https://vercel.com → GitHub 계정으로 로그인
2. **Add New… → Project** → 같은 저장소 **Import**
3. 설정 입력

| 항목 | 값 |
|---|---|
| **Root Directory** | `frontend` (Edit 눌러서 선택) |
| Framework Preset | Other |
| Build / Output | 그대로 두기 (`vercel.json` 이 `node generate-config.js`, `public` 으로 설정) |

4. **Environment Variables**: `API_BASE_URL` = `https://study-mate-api.onrender.com` (끝에 `/` 없이)
5. **Deploy** → `https://study-mate-xxxx.vercel.app` 주소 확인
   - 빌드 로그에 `✅ public/config.js 생성 완료 → API_BASE_URL = https://...` 가 보이면 정상

> ⚠️ Vercel 의 `API_BASE_URL` 을 나중에 바꾸면 **Deployments → … → Redeploy** 해야 반영됩니다. (빌드할 때 config.js 를 만들기 때문)

## 6. CORS 연결 (마지막 단계)

1. Render → 내 서비스 → **Environment** → `ALLOWED_ORIGINS` 수정
   ```
   https://study-mate-xxxx.vercel.app,http://localhost:5500
   ```
   - `https://` 포함, 끝에 `/` 없이, 쉼표로 구분
2. **Save, rebuild, and deploy** → 재배포 완료 후 Vercel 주소 접속 → 채팅·데이터·대화 기록 확인 🎉
3. `https://study-mate-api.onrender.com/health` 의 `allowed_origins` 에 내 Vercel 주소가 보이면 정상

> Vercel 은 커밋마다 `study-mate-git-브랜치-아이디.vercel.app` 같은 **미리보기 주소**도 만듭니다.
> 미리보기 주소까지 허용하려면 `ALLOWED_ORIGIN_REGEX=https://study-mate-.*\.vercel\.app` 를 추가하세요.

---

## 🧯 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 화면에 "서버에 연결할 수 없어요" + 브라우저 콘솔에 `CORS` 에러 | Render `ALLOWED_ORIGINS` 가 Vercel 주소와 **정확히** 같은지 (`https`, 끝 `/` 없음) |
| 화면이 `localhost:8000` 에 연결하려고 함 | Vercel `API_BASE_URL` 설정 후 **Redeploy** 했는지, 브라우저 강력 새로고침(Ctrl+Shift+R) |
| `/docs` 는 되는데 API 가 500 "Firebase 설정이 없습니다" | Render 에 `FIREBASE_SERVICE_ACCOUNT_JSON` 이 있는지 |
| `FIREBASE_SERVICE_ACCOUNT_JSON 값이 올바른 JSON이 아닙니다` | `{` 부터 `}` 까지 빠짐없이 붙여넣었는지 |
| `The database (default) does not exist` | Firebase 콘솔에서 Firestore Database 를 **만들기** 했는지 |
| AI 답변 대신 "API 키가 올바르지 않습니다" | `OPENAI_API_KEY` 재확인 → 로컬에서 `python -m scripts.check_setup --ai` |
| "주소 또는 모델을 찾을 수 없습니다(404)" | `OPENAI_BASE_URL`(끝에 `/v1` 필요 여부), `OPENAI_MODEL` 철자 |
| Render 빌드 실패 (패키지 설치 오류) | `PYTHON_VERSION=3.12.8` 환경 변수 추가 후 재배포 |
| 첫 접속이 1분 가까이 걸림 | 정상 (무료 플랜 콜드스타트) |

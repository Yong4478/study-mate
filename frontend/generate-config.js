/*
 * Vercel 빌드 단계에서 실행되어 public/config.js 를 만듭니다.
 * 순수 HTML/JS 는 환경 변수를 직접 읽을 수 없어서, 빌드할 때 값을 파일에 써 넣는 방식입니다.
 *
 *   Vercel → Settings → Environment Variables → API_BASE_URL = https://내-백엔드.onrender.com
 *   로컬에서 확인: API_BASE_URL=http://localhost:8000 node generate-config.js
 */
const fs = require("fs");
const path = require("path");

const apiBaseUrl = (process.env.API_BASE_URL || "http://localhost:8000").trim().replace(/\/+$/, "");
if (!process.env.API_BASE_URL) {
  console.warn("⚠️  API_BASE_URL 환경 변수가 없어 http://localhost:8000 을 사용합니다.");
}

const content = `// 이 파일은 generate-config.js 가 자동으로 만들었습니다. (${new Date().toISOString()})
window.APP_CONFIG = {
  API_BASE_URL: ${JSON.stringify(apiBaseUrl)},
};
`;
fs.writeFileSync(path.join(__dirname, "public", "config.js"), content);
console.log(`✅ public/config.js 생성 완료 → API_BASE_URL = ${apiBaseUrl}`);

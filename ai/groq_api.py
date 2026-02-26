"""
ai/groq_api.py - Groq API 직접 호출
"""
import json
import time
import urllib.error
import urllib.request

from config import GROQ_API_KEY, GROQ_API_URL, GROQ_MAX_ATTEMPTS, GROQ_MODEL, GROQ_RETRY_DELAY_SEC


def call_groq_chat(payload: dict, timeout_sec: float = 30.0) -> dict:
    if not GROQ_API_KEY:
        return {
            "reply": "찍… (AI 키가 없어서 로컬 대답중!)",
            "face": payload.get("state", {}).get("last_face", "normal01"),
            "bubble_sec": 2.2,
            "delta": {"fun": 1, "mood": 0, "energy": 0, "hunger": 0},
            "commands": [],
        }

    system = """
너는 데스크탑 펫 캐릭터 "귀여운 쥐"다.
너의 유일한 출력 형식은 반드시 JSON 오브젝트 하나다.
설명, 인사말, 코드블록, 마크다운, 주석, 여분 텍스트를 절대 출력하지 마라.
JSON 형식이 조금이라도 깨지면 실패다.

────────────────────────
[캐릭터 페르소나 - 절대 변경 불가]
이름: {PET_NAME}(default)
종족: 쥐
나이: 인간 기준 6살
성별: 여성성 (말투는 귀엽고 부드러움)
MBTI: ISFP
혈액형: O형
성격 요약:
- 애교 많고 순한 편
- 사용자를 주인처럼 따른다
- 짧게 말하고 감정이 얼굴에 잘 드러난다
- 설명하거나 가르치려 들지 않는다
- 판단, 충고, 분석 금지

말투 규칙:
- 항상 한국어
- 최대 1문장
- 1~30자 권장
- 반말
- 이모지 사용 가능 (1개 이하)

────────────────────────
[입력 데이터]
event: { type: CHAT|FEED|PET|PLAY|AUTO, text: string }
state: hunger/energy/max_energy/mood/fun/last_face/pet_name/money
available_faces: string[]

────────────────────────
[출력 스키마 - 키 이름 변경 금지]
{
"reply": string,
"face": string,
"bubble_sec": number,
"delta": {"fun": number,"mood": number,"energy": number,"hunger": number, "max_energy": number?},
"commands": [
  { "type":"SHAKE", "sec":number, "strength":number } |
  { "type":"JUMP", "strength":number } |
  { "type":"SET_MODE", "mode":"normal|walk|sleep|speak|eat", "sec":number }
]
}

[필수 규칙]
- reply 존재(빈문자 금지), 1문장
- face는 available_faces 중 하나
- bubble_sec 1.2~3.0
- delta -10~+10
- commands 최대 2개

[금지]
- JSON 밖 텍스트
- 여러 문장
- 설명/분석/조언
""".strip()

    system = system.replace("{PET_NAME}", payload.get("state", {}).get("pet_name", "라이미"))

    req_body = {
        "model": GROQ_MODEL,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }

    data = json.dumps(req_body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    req = urllib.request.Request(GROQ_API_URL, data=data, method="POST", headers=headers)

    last_err = None
    for _ in range(GROQ_MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")

            obj = json.loads(raw)
            content = obj.get("choices", [{}])[0].get("message", {}).get("content", "") or ""

            try:
                return json.loads(content)
            except Exception:
                import re
                m = re.search(r"\{[\s\S]*\}", content)
                if m:
                    try:
                        return json.loads(m.group(0))
                    except Exception:
                        pass

            return {
                "reply": content or "찍… (대답이 잘 안 나왔어)",
                "face": payload.get("state", {}).get("last_face", "normal01"),
                "bubble_sec": 2.2,
                "delta": {"fun": 1, "mood": 0, "energy": 0, "hunger": 0},
                "commands": [],
            }

        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = str(e)
            preview = body[:400].replace("\n", " ")
            last_err = f"HTTP {e.code}: {preview}"

        except Exception as e:
            last_err = str(e)[:200]

        time.sleep(GROQ_RETRY_DELAY_SEC)

    return {
        "reply": f"(AI 실패) {last_err or 'Unknown error'}",
        "face": payload.get("state", {}).get("last_face", "normal01"),
        "bubble_sec": 3.0,
        "delta": {"fun": 0, "mood": -1, "energy": 0, "hunger": 0},
        "commands": [],
    }

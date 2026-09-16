"""OpenAI 호환 엔드포인트(DeepSeek 등 저가 모델) 호출 — quick 티어의 대체 provider.

Anthropic 호출(`llm_client.py`)과 같은 계약을 지킨다: (system, document, request_text, schema) → dict.
차이는 세 가지다.
- 구조화 출력이 스키마 강제가 아니라 JSON 모드다. 스키마를 요청문에 붙여 보내고, 검증은 추출기가
  provider 공통으로 한다(`response_check.py`).
- PDF 문서 블록이 없다. 원문은 텍스트로만 넣는다.
- 컨텍스트가 128K 안팎인 경우가 많다 — 길이 초과는 엔드포인트가 400으로 알려주므로 그대로 올린다.

설정은 환경변수 세 개: COMPAT_LLM_BASE_URL(예: https://api.deepseek.com), COMPAT_LLM_API_KEY,
COMPAT_LLM_MODEL(예: deepseek-chat). 이름을 provider 중립으로 둔 이유는 DeepSeek 외 다른 호환
엔드포인트로 바꿀 때 코드를 건드리지 않기 위해서다.
"""

import json
import os

import openai

from collection.qualitative.sources import SourceDocument

ENV_BASE_URL: str = "COMPAT_LLM_BASE_URL"
ENV_API_KEY: str = "COMPAT_LLM_API_KEY"
ENV_MODEL: str = "COMPAT_LLM_MODEL"
REQUEST_TIMEOUT_SECONDS: float = 600.0
MAX_OUTPUT_TOKENS: int = 8000
# JSON 모드는 결정적 출력이 목적이라 온도를 0으로 둔다.
TEMPERATURE: float = 0.0

_JSON_ONLY_INSTRUCTION: str = (
    "\n\n반드시 아래 JSON 스키마를 만족하는 JSON 객체 하나만 출력하라. 설명 문장·코드펜스 없이 JSON만.\n"
    "스키마:\n"
)


class CompatError(RuntimeError):
    """OpenAI 호환 엔드포인트가 쓸 수 있는 결과를 내지 못했다."""


def create_compat_client() -> tuple[openai.OpenAI, str]:
    base_url, api_key, model = (os.getenv(name) for name in (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL))
    if not (base_url and api_key and model):
        raise CompatError(f".env에 {ENV_BASE_URL}, {ENV_API_KEY}, {ENV_MODEL} 세 개가 모두 있어야 한다")
    return openai.OpenAI(base_url=base_url, api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS), model


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


def compat_extract_structured(
    client: openai.OpenAI,
    model: str,
    system: str,
    document: SourceDocument,
    request_text: str,
    schema: dict,
) -> dict:
    if document.text is None:
        raise CompatError("호환 엔드포인트는 PDF를 받지 못한다 — txt/html 원문을 쓰거나 Anthropic provider를 써라")
    user_text = (
        f"[원문: {document.title}]\n{document.text}\n\n[요청]\n{request_text}"
        f"{_JSON_ONLY_INSTRUCTION}{json.dumps(schema, ensure_ascii=False)}"
    )
    try:
        completion = client.chat.completions.create(
            model=model,
            temperature=TEMPERATURE,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user_text}],
        )
    except openai.AuthenticationError as error:
        raise CompatError(f"호환 엔드포인트 인증 실패 — {ENV_API_KEY}를 확인하라") from error
    except openai.BadRequestError as error:
        raise CompatError(f"호환 엔드포인트가 요청을 거부했다(컨텍스트 초과일 수 있다 — --sections를 줄여라): {error.message}") from error
    except openai.APIStatusError as error:
        raise CompatError(f"호환 엔드포인트 오류 {error.status_code}: {error.message}") from error
    except openai.APIConnectionError as error:
        raise CompatError(f"호환 엔드포인트 연결 실패 — {ENV_BASE_URL}를 확인하라") from error

    choice = completion.choices[0]
    if choice.finish_reason == "length":
        raise CompatError(f"출력이 {MAX_OUTPUT_TOKENS} 토큰 상한에서 잘렸다 — 항목을 나눠 요청하라")
    usage = completion.usage
    if usage is not None:
        print(f"[qualitative] {completion.model} 입력 {usage.prompt_tokens:,} / 출력 {usage.completion_tokens:,} 토큰")

    try:
        return json.loads(_strip_code_fence(choice.message.content or ""))
    except json.JSONDecodeError as error:
        raise CompatError("호환 엔드포인트 응답이 JSON이 아니다") from error

"""Anthropic API 호출을 이 파일 하나에 가둔다 — 프로젝트의 유일한 LLM 의존 지점.

키는 다른 수집 소스(FRED·ECOS)와 같은 방식으로 환경변수(ANTHROPIC_API_KEY)에서 읽되,
SDK가 스스로 해석하게 둔다(`ant auth login` 프로필도 인식하므로 키를 직접 검사하지 않는다).
로컬은 .env(python-dotenv, grade_qualitative.py), GitHub Actions는 Secrets로 주입한다.

호출 형태의 근거:
- 구조화 출력(output_config.format): 관측값 JSON이 스키마대로 오게 강제한다. 출력 스키마는
  `prompts.build_output_schema`(공통 항목 1벌의 배열) — 항목별 스키마는 nullable 16개·문법 크기 한도에
  걸린다. 그마저 거부되면 스키마를 프롬프트에 넣는 모드로 재시도한다.
- 스트리밍: 사업보고서 한 편이 수십만 토큰이라 비스트리밍은 타임아웃 위험이 있다.
- 프롬프트 캐시: 시스템 프롬프트와 원문 블록에 경계를 둔다(같은 원문을 다시 요청할 때 대비).
- 서버측 폴백: 안전 분류기가 요청을 거절하면 같은 호출 안에서 대체 모델로 재시도한다(Opus만).
quick 티어의 대체 provider(OpenAI 호환 엔드포인트)는 `compat_client.py`에 따로 있다.
"""

import json

import anthropic

from collection.qualitative.sources import SourceDocument, document_block

# 기본은 deep 티어 값. 티어별 모델·effort는 `tiers.py`가 정하고 호출 시 넘긴다.
MODEL_ID: str = "claude-opus-5"
EFFORT: str = "high"
MAX_OUTPUT_TOKENS: int = 16000
# 서버측 폴백(안전 분류기 거절 시 대체 모델 재시도)은 Opus 계열에서만 쓴다.
FALLBACK_BETA: str = "server-side-fallback-2026-07-01"
FALLBACKS: str = "default"
FALLBACK_MODELS: tuple[str, ...] = ("claude-opus-5",)

STOP_REASON_REFUSAL: str = "refusal"
STOP_REASON_MAX_TOKENS: str = "max_tokens"


class ExtractionError(RuntimeError):
    """LLM 추출이 쓸 수 있는 결과를 내지 못했다."""


def create_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _first_text(message: anthropic.types.Message) -> str:
    return next(block.text for block in message.content if block.type == "text")


GRAMMAR_ERROR_MARKER: str = "grammar"
_JSON_ONLY_INSTRUCTION: str = "\n\n반드시 아래 JSON 스키마를 만족하는 JSON 객체 하나만 출력하라. 설명 문장·코드펜스 없이 JSON만.\n스키마:\n"


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        stripped = stripped.rsplit("```", 1)[0]
    return stripped.strip()


def _stream(client, model, effort, system, document, request_text, schema, use_format: bool):
    output_config = {"effort": effort}
    if use_format:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    else:
        request_text = f"{request_text}{_JSON_ONLY_INSTRUCTION}{json.dumps(schema, ensure_ascii=False)}"
    fallback_options = {"betas": [FALLBACK_BETA], "fallbacks": FALLBACKS} if model in FALLBACK_MODELS else {}
    with client.beta.messages.stream(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": [document_block(document), {"type": "text", "text": request_text}],
        }],
        output_config=output_config,
        **fallback_options,
    ) as stream:
        return stream.get_final_message()


def extract_structured(
    client: anthropic.Anthropic,
    system: str,
    document: SourceDocument,
    request_text: str,
    schema: dict,
    model: str = MODEL_ID,
    effort: str = EFFORT,
) -> dict:
    """원문 + 요청문 → 스키마 형태의 JSON dict. 구조화 출력이 문법 크기 한도로 거부되면 스키마를
    프롬프트에 넣는 방식으로 한 번 더 시도한다(검증은 추출기가 사후에 한다)."""
    try:
        try:
            message = _stream(client, model, effort, system, document, request_text, schema, use_format=True)
        except anthropic.BadRequestError as error:
            if GRAMMAR_ERROR_MARKER not in error.message:
                raise
            print("[qualitative] 구조화 출력 문법 한도 초과 — 프롬프트 JSON 모드로 재시도")
            message = _stream(client, model, effort, system, document, request_text, schema, use_format=False)
    except anthropic.AuthenticationError as error:
        raise ExtractionError(
            "Anthropic 인증 실패 — .env의 ANTHROPIC_API_KEY 또는 `ant auth login` 프로필을 확인하라"
        ) from error
    except anthropic.APIStatusError as error:
        raise ExtractionError(f"Anthropic API 오류 {error.status_code}: {error.message}") from error
    except anthropic.APIConnectionError as error:
        raise ExtractionError("Anthropic API 연결 실패") from error

    if message.stop_reason == STOP_REASON_REFUSAL:
        details = message.stop_details
        category = details.category if details else None
        raise ExtractionError(f"모델이 요청을 거부했다 (category={category})")
    if message.stop_reason == STOP_REASON_MAX_TOKENS:
        raise ExtractionError(f"출력이 {MAX_OUTPUT_TOKENS} 토큰 상한에서 잘렸다 — 항목을 나눠 요청하라")

    usage = message.usage
    print(
        f"[qualitative] {message.model} 입력 {usage.input_tokens:,} / 캐시 생성 "
        f"{usage.cache_creation_input_tokens or 0:,} / 캐시 읽기 {usage.cache_read_input_tokens or 0:,} "
        f"/ 출력 {usage.output_tokens:,} 토큰"
    )
    try:
        return json.loads(_strip_code_fence(_first_text(message)))
    except json.JSONDecodeError as error:
        raise ExtractionError("응답이 JSON이 아니다") from error

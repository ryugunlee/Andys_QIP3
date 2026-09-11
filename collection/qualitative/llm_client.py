"""Anthropic API 호출을 이 파일 하나에 가둔다 — 프로젝트의 유일한 LLM 의존 지점.

키는 다른 수집 소스(FRED·ECOS)와 같은 방식으로 환경변수(ANTHROPIC_API_KEY)에서 읽되,
SDK가 스스로 해석하게 둔다(`ant auth login` 프로필도 인식하므로 키를 직접 검사하지 않는다).
로컬은 .env(python-dotenv, grade_qualitative.py), GitHub Actions는 Secrets로 주입한다.

호출 형태의 근거:
- 구조화 출력(output_config.format): 관측값 JSON이 스키마대로 오게 강제한다.
- 스트리밍: 사업보고서 한 편이 수십만 토큰이라 비스트리밍은 타임아웃 위험이 있다.
- 프롬프트 캐시: 시스템 프롬프트와 원문 블록에 경계를 둔다. 같은 원문에 축별로 6번 이상
  질문하므로 원문 토큰은 첫 호출에만 정가로 든다.
- 서버측 폴백: 안전 분류기가 요청을 거절하면 같은 호출 안에서 대체 모델로 재시도한다.
"""

import json

import anthropic

from collection.qualitative.sources import SourceDocument, document_block

MODEL_ID: str = "claude-opus-5"
# 추출은 판단 오류 비용이 크고 호출 횟수가 적어(종목당 ~8회) 상위 effort를 기본으로 둔다.
EFFORT: str = "high"
MAX_OUTPUT_TOKENS: int = 16000
FALLBACK_BETA: str = "server-side-fallback-2026-07-01"
FALLBACKS: str = "default"

STOP_REASON_REFUSAL: str = "refusal"
STOP_REASON_MAX_TOKENS: str = "max_tokens"


class ExtractionError(RuntimeError):
    """LLM 추출이 쓸 수 있는 결과를 내지 못했다."""


def create_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _first_text(message: anthropic.types.Message) -> str:
    return next(block.text for block in message.content if block.type == "text")


def extract_structured(
    client: anthropic.Anthropic,
    system: str,
    document: SourceDocument,
    request_text: str,
    schema: dict,
) -> dict:
    """원문 + 요청문 → 스키마를 만족하는 JSON dict."""
    try:
        with client.beta.messages.stream(
            model=MODEL_ID,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": [document_block(document), {"type": "text", "text": request_text}],
            }],
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks=FALLBACKS,
        ) as stream:
            message = stream.get_final_message()
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
        raise ExtractionError(f"출력이 {MAX_OUTPUT_TOKENS} 토큰 상한에서 잘렸다 — 축을 나눠 요청하라")

    usage = message.usage
    print(
        f"[qualitative] {message.model} 입력 {usage.input_tokens:,} / 캐시 생성 "
        f"{usage.cache_creation_input_tokens or 0:,} / 캐시 읽기 {usage.cache_read_input_tokens or 0:,} "
        f"/ 출력 {usage.output_tokens:,} 토큰"
    )
    return json.loads(_first_text(message))

"""정성 채점 티어 — quick(싸고 넓게)과 deep(비싸고 깊게)의 설정 단일 소스.

`.claude/정성 평가 규칙.md` 6절. 비용은 항목 수가 아니라 원문 토큰이 정하므로 티어의 차이는
① 모델·effort ② 사업보고서 섹션 범위다. quick은 상위 10% 선별 종목 전체를 훑는 용도, deep은 그중
관심 종목만 III(재무·주석)까지 읽어 Q7·Q8·Q9를 채우는 용도.

quick의 provider는 둘 중 하나: Anthropic(Sonnet 5) 또는 OpenAI 호환 엔드포인트(DeepSeek 등,
`compat_client.py`). 호환 엔드포인트는 컨텍스트가 128K 안팎인 경우가 많아 quick 섹션을 더 좁게 둔다.
"""

from dataclasses import dataclass

TIER_QUICK: str = "quick"
TIER_DEEP: str = "deep"
PROVIDER_ANTHROPIC: str = "anthropic"
PROVIDER_COMPAT: str = "compat"


@dataclass(frozen=True)
class Tier:
    name: str
    anthropic_model: str
    effort: str
    sections: tuple[str, ...]


TIERS: dict[str, Tier] = {
    # 삼성전자 실측: II 4만·VI 3.8만·X 0.8만 + III 핵심 주석 2.5만 ≈ 11만 자. III*가 Q7·Q8·Q9의 근거를 준다.
    TIER_QUICK: Tier(TIER_QUICK, "claude-sonnet-5", "low", ("II", "VI", "X", "III*")),
    # III(재무·주석 27만 자)을 더해 Q7·Q8·Q9 근거까지. 삼성전자 기준 41만 자 ≈ 33.5만 토큰.
    TIER_DEEP: Tier(TIER_DEEP, "claude-opus-5", "high", ("I", "II", "III", "VI", "VII", "X", "XI")),
}

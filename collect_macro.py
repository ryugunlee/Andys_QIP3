"""경제지표(매크로) 수집 진입점.

야후·FRED·ECOS·네이버(KRX 금현물)에서 지표를 수집하고 파생 지표(금 괴리율,
장단기 금리차)를 계산해 DuckDB의 macro_daily 테이블에 upsert한다.
(indicator, date) 기준 upsert라서 초회 히스토리 적재와 이후 증분 갱신을
같은 명령으로 처리한다. 주식 파이프라인(Andys_QIP2.py)과는 독립적으로 실행한다.

FRED_API_KEY/BOK_API_KEY는 로컬에서는 .env(python-dotenv)로, GitHub Actions에서는
리포지토리 Secrets(collect-macro.yml의 env)로 주입된다. 키가 없으면 해당 소스만
경고 후 건너뛴다.

사용법:
    python collect_macro.py

지표 목록/소스 정의: collection/macro/indicators.py
"""

import pandas as pd
from dotenv import load_dotenv

import storage
from collection.macro.derived import compute_derived_indicators
from collection.macro.ecos_source import fetch_ecos_macro
from collection.macro.fred_source import fetch_fred_macro
from collection.macro.naver_gold_source import fetch_naver_gold_macro
from collection.macro.yahoo_source import fetch_yahoo_macro

load_dotenv()  # 로컬 .env 파일이 있으면 BOK_API_KEY/FRED_API_KEY 등을 환경변수로 읽어들인다


def collect_macro() -> pd.DataFrame:
    """모든 소스를 수집하고 파생 지표까지 합친 long DataFrame을 반환한다."""
    collected = pd.concat(
        [fetch_yahoo_macro(), fetch_fred_macro(), fetch_ecos_macro(), fetch_naver_gold_macro()],
        ignore_index=True,
    )
    derived = compute_derived_indicators(collected)
    return pd.concat([collected, derived], ignore_index=True)


def main() -> None:
    values = collect_macro()
    if values.empty:
        print("[macro] 수집된 지표가 없습니다.")
        return

    conn = storage.connect(storage.MACRO_DB_PATH)
    try:
        storage.upsert_macro_values(conn, values)
        summary = (
            values.groupby("indicator")
            .agg(rows=("value", "size"), latest=("date", "max"))
            .sort_index()
        )
        print(f"[macro] {len(summary)}개 지표, {len(values):,}행 저장 완료")
        print(summary.to_string())
    finally:
        conn.close()


if __name__ == "__main__":
    main()

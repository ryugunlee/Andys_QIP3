# Andy`s Quantitative Investment Program II
#
# 시장 하나를 통째로 수집·저장·채점하는 진입점.
# 실제 단계(수집 → 스냅샷 → 지수 → 채점 → 커트라인 → 그룹요약)는 `pipeline/market_run.py`가
# 갖고 있다 — 조각 수집(`collect_chunk.py`)·확정(`finalize_run.py`) 진입점이 같은 단계를
# 재사용해야 해서 분리했다 (`.claude/PROBLEMS.md` #42).
#
# 사용법:
#   python Andys_QIP2.py KOSPI                    # 1회 실행 후 종료 (GitHub Actions 등 비대화형)
#   python Andys_QIP2.py KOSPI --allow-partial    # 종목 수 급감 가드를 무시하고 기록
#   python Andys_QIP2.py                          # 시장을 입력받아 실행한 뒤 매일 09:00 재실행 스케줄

import sys
import time

import pandas as pd
import schedule

from pipeline import PartialRunError, run_market

# 종목 수 급감 가드를 끄는 플래그 (소스 장애가 아님을 사람이 확인했을 때만 쓴다).
ALLOW_PARTIAL_FLAG = "--allow-partial"

# 현재 KRX, KOSPI, KOSDAQ, KONEX, NASDAQ, NYSE, AMEX, S&P500, DJI 중 하나를 선택할 수 있습니다.
# AMERICAN을 선택하면 AMEX, NASDAQ, NYSE의 종목을 모두 가져옵니다.(ETF 제외)

# 시장 하나를 통째로 수집·채점한다. 하위 호환을 위한 별칭 — 기존 호출부가 main()을 쓴다.
main = run_market

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.max_colwidth", None)

if __name__ == "__main__":
    arguments = sys.argv[1:]
    allow_partial = ALLOW_PARTIAL_FLAG in arguments
    markets = [value for value in arguments if value != ALLOW_PARTIAL_FLAG]
    if markets:
        # 명령줄 인자로 시장을 넘기면 (GitHub Actions 등 비대화형 실행) 1회만 실행하고 종료한다.
        try:
            main(markets[0].upper(), allow_partial=allow_partial)
        except PartialRunError as error:
            # 반쪽 run을 기록하지 않고 실패로 끝낸다 — 스냅샷을 남기는 것보다 이번 회차를
            # 건너뛰는 편이 사이트에 안전하다. 일봉·재무제표는 이미 누적돼 있다.
            raise SystemExit(f"[Andys_QIP2] 수집 중단: {error}")
    else:
        stockmarket = input(
            "Enter the stock market (e.g., NASDAQ, NYSE, KRX, AMERICAN): "
        ).upper()
        main(stockmarket)
        # Schedule the main function to run every day at 9:00 AM
        schedule.every().day.at("09:00").do(main, stockmarket)
        # Keep the script running to execute the scheduled task
        while True:
            schedule.run_pending()
            time.sleep(1)

# Andy`s Quantitative Investment Program II
#
# 시장 하나를 통째로 수집·저장·채점하는 진입점.
# 실제 단계(수집 → 스냅샷 → 지수 → 채점 → 커트라인 → 그룹요약)는 `pipeline/market_run.py`가
# 갖고 있다 — 조각 수집(`collect_chunk.py`)·확정(`finalize_run.py`) 진입점이 같은 단계를
# 재사용해야 해서 분리했다 (`.claude/PROBLEMS.md` #42).
#
# 사용법:
#   python Andys_QIP2.py KOSPI    # 1회 실행 후 종료 (GitHub Actions 등 비대화형)
#   python Andys_QIP2.py          # 시장을 입력받아 실행한 뒤 매일 09:00 재실행 스케줄

import sys
import time

import pandas as pd
import schedule

from pipeline import run_market

# 현재 KRX, KOSPI, KOSDAQ, KONEX, NASDAQ, NYSE, AMEX, S&P500, DJI 중 하나를 선택할 수 있습니다.
# AMERICAN을 선택하면 AMEX, NASDAQ, NYSE의 종목을 모두 가져옵니다.(ETF 제외)

# 시장 하나를 통째로 수집·채점한다. 하위 호환을 위한 별칭 — 기존 호출부가 main()을 쓴다.
main = run_market

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.max_colwidth", None)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 명령줄 인자로 시장을 넘기면 (GitHub Actions 등 비대화형 실행) 1회만 실행하고 종료한다.
        main(sys.argv[1].upper())
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

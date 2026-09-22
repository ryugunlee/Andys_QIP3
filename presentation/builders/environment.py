"""Jinja2 환경 생성: 템플릿 로더 + 필터 + 공통 전역값.

모든 빌더가 같은 환경을 공유하도록 이 팩토리 하나만 쓴다.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from presentation import config
from presentation.formatters import MISSING, is_kr_market, register_filters

TEMPLATES_DIR: Path = Path(__file__).resolve().parent.parent / "templates"


def create_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(("html",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    register_filters(env)
    env.globals["site_title"] = config.SITE_TITLE
    env.globals["site_description"] = config.SITE_DESCRIPTION
    env.globals["disclaimer"] = config.DISCLAIMER
    env.globals["missing"] = MISSING
    env.globals["app_short_name"] = config.APP_SHORT_NAME
    env.globals["app_theme_color"] = config.APP_THEME_COLOR
    env.globals["app_background_color"] = config.APP_BACKGROUND_COLOR
    env.globals["news_featured_limit"] = config.NEWS_FEATURED_LIMIT
    env.globals["news_list_limit"] = config.NEWS_LIST_LIMIT
    # 종목 상세 페이지의 정성 평가 실행 위젯을 한국 종목에만 보이려고 템플릿에서 직접 쓴다
    # (미국 종목은 실행 서버 IP가 SEC EDGAR에 막혀 웹 실행 자체가 안 됨).
    env.globals["is_kr_market"] = is_kr_market
    return env

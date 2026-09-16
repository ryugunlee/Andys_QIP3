"""관리자 화면(admin/index.html) 빌더.

정성 평가를 웹에서 실행하고, 누가 실행할 수 있는지를 관리하는 한 페이지다.
데이터를 읽지 않으므로 repository를 받지 않는다 — 화면의 모든 내용은 브라우저가 로그인한 뒤
Supabase에서 직접 받아 채운다(static/admin.js). 여기서 만드는 것은 빈 껍데기와 상수뿐이다.

권한 판정은 이 파일도 브라우저도 아니고 데이터베이스가 한다(supabase/schema_qip3.sql).
화면이 버튼을 감추는 것은 편의일 뿐이며, 감춘 버튼을 되살려 눌러도 RLS가 막는다.
"""

from pathlib import Path

from jinja2 import Environment

from presentation import config

ADMIN_DIRNAME: str = "admin"


def build_admin_page(env: Environment, output_dir: Path, updated_date: str | None) -> None:
    admin_dir = output_dir / ADMIN_DIRNAME
    admin_dir.mkdir(parents=True, exist_ok=True)

    template = env.get_template("admin.html")
    html = template.render(
        root="..",
        active_page="admin",
        updated_date=updated_date,
        dispatch_function_name=config.DISPATCH_FUNCTION_NAME,
        cost_hints=config.QUALITATIVE_COST_HINTS,
    )
    (admin_dir / "index.html").write_text(html, encoding="utf-8")

from app.main import health_check


def test_health_check_reports_ok() -> None:
    assert health_check() == {"status": "ok"}

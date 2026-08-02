from pathlib import Path


def test_hosted_mcp_is_stateless_across_gunicorn_workers():
    source = (Path(__file__).parents[1] / "asgi.py").read_text()

    assert 'mcp.http_app(path="/", stateless_http=True)' in source
    assert "--workers 3" in (Path(__file__).parents[2] / "deployment/entrypoint.sh").read_text()

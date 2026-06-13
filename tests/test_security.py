from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from api.middleware.security_headers import SecurityHeadersMiddleware


async def homepage(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def test_security_headers_middleware_adds_headers() -> None:
    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(SecurityHeadersMiddleware)

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from sre_agent.config import Settings

app = FastAPI()


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def create_app() -> FastAPI:
    try:
        settings = Settings()
    except Exception:
        return app
    if settings.feishu_app_secret:
        from sre_agent.channels import feishu

        feishu.register(app, settings)
    from sre_agent.channels import dingtalk

    if dingtalk.dingtalk_routes_enabled(settings):
        dingtalk.register(app, settings)
    return app


create_app()

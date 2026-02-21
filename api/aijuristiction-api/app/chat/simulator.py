from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["chat-simulator"])
_templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))


@router.get("/chat-simulator")
def chat_simulator(request: Request):
    return _templates.TemplateResponse(
        request=request,
        name="chat_simulator.html",
        context={"page_title": "AI Juristiction Chat Simulator"},
    )

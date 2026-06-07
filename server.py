"""Hermes Agent — FastAPI SSE streaming server."""

import json
import logging
import os
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hermes_core import AIAgent

logger = logging.getLogger(__name__)

app = FastAPI(title="Hermes Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: dict[str, AIAgent] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    response: str


@app.post("/api/chat")
async def chat(req: ChatRequest) -> ChatResponse:
    session_id = req.session_id or str(uuid.uuid4())[:8]

    if session_id not in sessions:
        sessions[session_id] = AIAgent(
            model=req.model,
            platform="web",
            session_id=session_id,
        )

    agent = sessions[session_id]
    result = agent.chat(req.message)

    return ChatResponse(session_id=session_id, response=result)


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())[:8]

    if session_id not in sessions:
        sessions[session_id] = AIAgent(
            model=req.model,
            platform="web",
            session_id=session_id,
        )

    agent = sessions[session_id]

    async def generate():
        try:
            result = agent.run_conversation(req.message)
            response_text = result.get("final_response", "")
            yield f"data: {json.dumps({'session_id': session_id, 'response': response_text})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id in sessions:
        sessions[session_id].close()
        del sessions[session_id]
    return {"status": "deleted"}


app.mount("/", StaticFiles(directory="web", html=True), name="static")

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
import threading
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from runtime import InferenceError, Runtime


runtime = Runtime(Path(os.getenv("DISCOVERY_MODEL_ROOT", "/models/discovery/v308-fp32-v1")))


@asynccontextmanager
async def lifespan(_app):
    runtime.prepare()
    yield


app = FastAPI(title="STL local discovery inference", version="3.0.8.1", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


class AdmissionLimit:
    """Bound requests before parsing a body or occupying the sync worker pool."""
    def __init__(self, app):
        self.app = app
        self.slots = threading.BoundedSemaphore(3)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        if not self.slots.acquire(blocking=False):
            return await JSONResponse({"detail": {"code": "inference_busy", "message": "本地推理正在处理其他请求。"}},
                                      429, headers={"Retry-After": "3"})(scope, receive, send)
        try:
            size, messages = 0, []
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > 1_000_000:
                    return await JSONResponse({"detail": {"code": "body_too_large", "message": "推理请求超过大小限制。"}}, 413)(scope, receive, send)
                messages.append(message)
                if not message.get("more_body", False):
                    break
            async def bounded_receive():
                if messages:
                    return messages.pop(0)
                return await receive()
            await self.app(scope, bounded_receive, send)
        finally:
            self.slots.release()


app.add_middleware(AdmissionLimit)


class TextBatch(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)

    @field_validator("texts")
    @classmethod
    def bounded(cls, value):
        if sum(len(text) for text in value) > 192_000 or any(len(text) > 100_000 for text in value):
            raise ValueError("文字超过分批上限")
        return value


class EmbedRequest(TextBatch):
    kind: Literal["query", "passage"] = "passage"
    expected_artifact: str = Field(default="", max_length=100)


class ChunkRequest(BaseModel):
    text: str = Field(max_length=100_000)
    title: str = Field(default="", max_length=2000)
    max_tokens: int = Field(default=320, ge=128, le=448)
    overlap_tokens: int = Field(default=40, ge=0, le=64)


class RerankRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    documents: list[str] = Field(min_length=1, max_length=64)
    top_n: int = Field(default=20, ge=1, le=64)
    expected_artifact: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=160)
    return_documents: bool = False

    @field_validator("documents")
    @classmethod
    def bounded(cls, value):
        if sum(len(text) for text in value) > 192_000 or any(len(text) > 16_000 for text in value):
            raise ValueError("重排候选超过分批上限")
        return value


def serialized(function):
    if not runtime.lock.acquire(timeout=3):
        raise HTTPException(429, detail={"code": "inference_busy", "message": "本地推理正在处理其他请求。"},
                            headers={"Retry-After": "3"})
    try:
        return function()
    except InferenceError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
    finally:
        runtime.lock.release()


@app.get("/health")
def health():
    value = runtime.health()
    return JSONResponse(value, 200 if value["manifest_ready"] else 503)


@app.post("/normalize")
def normalize(request: TextBatch):
    return serialized(lambda: {"texts": [runtime.normalize(text) for text in request.texts],
                               "normalization": "stl-t2s-dehyphen-nfkc-v1"})


@app.post("/chunk")
def chunk(request: ChunkRequest):
    return serialized(lambda: runtime.chunk(request.text, request.title, request.max_tokens, request.overlap_tokens))


@app.post("/embed")
def embed(request: EmbedRequest):
    return serialized(lambda: runtime.embed(request.texts, request.kind, request.expected_artifact))


@app.post("/rerank")
def rerank(request: RerankRequest):
    def operation():
        runtime.require("reranker", request.expected_artifact)
        if request.model and request.model != runtime.models["reranker"]["repo_id"]:
            raise InferenceError("model_mismatch", "重排模型身份不一致。", 409)
        return runtime.rerank(request.query, request.documents, min(request.top_n, len(request.documents)), request.expected_artifact)
    return serialized(operation)

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
import threading
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from runtime import InferenceError, Runtime


runtime = Runtime(Path(os.getenv("DISCOVERY_MODEL_ROOT", "/models/discovery/v308-fp32-v1")))


@asynccontextmanager
async def lifespan(_app):
    runtime.prepare()
    yield


app = FastAPI(title="STL local discovery inference", version=os.getenv("DISCOVERY_SERVICE_VERSION", "4.0"), lifespan=lifespan,
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


class RerankContext(BaseModel):
    before: str = Field(default="", max_length=1000)
    after: str = Field(default="", max_length=1000)


class RerankRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    documents: list[str] = Field(min_length=1, max_length=64)
    top_n: int = Field(default=20, ge=1, le=64)
    expected_artifact: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=160)
    generation: str = Field(default="", max_length=160)
    return_documents: bool = False
    contexts: list[RerankContext] | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def matching_contexts(self):
        if self.contexts is not None and len(self.contexts) != len(self.documents):
            raise ValueError("邻文数量必须与候选相同")
        return self

    @field_validator("documents")
    @classmethod
    def bounded(cls, value):
        if sum(len(text) for text in value) > 192_000 or any(len(text) > 16_000 for text in value):
            raise ValueError("重排候选超过分批上限")
        return value


class DeepRerankRequest(RerankRequest):
    """Explicitly opt into the isolated BGE deep lane."""
    model: str = Field(default="BAAI/bge-reranker-v2-m3", max_length=160)


class ContextOrganizeHit(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=16_000)
    before: str = Field(default="", max_length=1000)
    after: str = Field(default="", max_length=1000)
    title: str = Field(default="", max_length=1000)
    page: int | None = Field(default=None, ge=1, le=100_000)


class ContextOrganizeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    hits: list[ContextOrganizeHit] = Field(min_length=1, max_length=10)
    model: str = Field(default="ConvMemory-v2", max_length=160)
    expected_artifact: str = Field(default="", max_length=100)
    generation: str = Field(default="", max_length=160)


def serialized(function):
    if not runtime.lock.acquire(timeout=3):
        raise HTTPException(429, detail={"code": "inference_busy", "message": "本地推理正在处理其他请求。"},
                            headers={"Retry-After": "3"})
    try:
        return function()
    except InferenceError as exc:
        detail = {"code": exc.code, "message": str(exc)}
        if exc.code in {"deep_unavailable", "deep_pending"}:
            detail["status"] = "pending" if exc.code == "deep_pending" else "unavailable"
            detail["stage"] = "deep"
        raise HTTPException(exc.status, detail=detail) from exc
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
        runtime.require("reranker", request.expected_artifact, model=request.model,
                        generation=request.generation)
        if request.contexts is not None:
            return runtime.rerank(request.query, request.documents, min(request.top_n, len(request.documents)),
                                  request.expected_artifact, contexts=[item.model_dump() for item in request.contexts])
        return runtime.rerank(request.query, request.documents, min(request.top_n, len(request.documents)), request.expected_artifact)
    return serialized(operation)


@app.get("/deep/status")
def deep_status():
    return JSONResponse(runtime.deep_health(), 200)


@app.post("/deep-rerank")
def deep_rerank(request: DeepRerankRequest):
    def operation():
        return runtime.deep_rerank(
            request.query,
            request.documents,
            min(request.top_n, len(request.documents)),
            model=request.model,
            artifact=request.expected_artifact,
            generation=request.generation,
            contexts=[item.model_dump() for item in request.contexts] if request.contexts is not None else None,
        )
    return serialized(operation)


@app.post("/context-organize")
def context_organize(request: ContextOrganizeRequest):
    # This endpoint deliberately returns a typed 200 envelope for unavailable
    # context models. The caller can keep the original EvidenceSpan ordering
    # without interpreting an unavailable ConvMemory lane as a success.
    return serialized(lambda: runtime.organize_context(
        model=request.model,
        artifact=request.expected_artifact,
        generation=request.generation,
        hits=[item.model_dump() for item in request.hits],
        query=request.query,
    ))

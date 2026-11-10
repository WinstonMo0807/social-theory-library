"""Official MCP 2.3 stdio adapter. Identity is bound by the trusted launcher."""
from importlib.metadata import version
from functools import wraps
import json
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from catalog import models as m
from catalog.services import intelligence, intelligence_changes, intelligence_queries
from catalog.services.knowledge_core import entity_data
from catalog.services.knowledge_public import page_data, assertion_data
from catalog.services.knowledge_sources import locator, context
from catalog.services.publication_eligibility import public_editions


def build_server(actor_id):
    if version("mcp") != "2.3.0":
        raise RuntimeError("需要官方 MCP SDK 2.3.0。")
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    server = MCPServer("STL Knowledge & Intelligence")

    def tool(fn):
        @wraps(fn)
        def invoke(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except APIException as exc:
                # SDK 2 hides unexpected exception text. Business failures must
                # remain actionable while transport/internal crashes stay private.
                detail = exc.detail
                raise ToolError(f"{exc.status_code}: " + (detail if isinstance(detail, str)
                    else json.dumps(detail, ensure_ascii=False))) from exc
            except Http404 as exc:
                raise ToolError("404: 对象不存在或当前不可访问。") from exc
        return server.tool()(invoke)

    def actor():
        # Recheck on every call; tools cannot choose a different user or acquire
        # the compute executor's lease capability.
        user = get_user_model().objects.filter(pk=actor_id, is_active=True).first()
        if not user:
            raise PermissionDenied("MCP绑定账户已停用。")
        return user

    @tool
    def catalog_search(query: str = "", limit: int = 20) -> dict:
        """Find accessible published editions. Returns bibliography, never private notes."""
        actor()
        rows = public_editions().filter(active_catalog_revision__snapshot__work__title__icontains=query[:300]).select_related("active_catalog_revision").order_by("pk")[:max(1,min(limit,50))]
        return {"editions": [{"work_id":str(r.work_id),"edition_id":str(r.pk),"title":r.active_catalog_revision.snapshot.get("work", {}).get("title", "")} for r in rows]}

    @tool
    def knowledge_search(query: str = "", limit: int = 20) -> dict:
        """Find published knowledge identities; names never imply the same identity."""
        actor()
        from catalog.services.knowledge_public import public_entities
        from catalog.services.knowledge_entity_queries import entity_query
        return {"entities":[entity_data(e, public=True) for e in entity_query(
            public_entities(), query=query[:300], public=True)[:max(1,min(limit,50))]]}

    @tool
    def unified_search(query: str, source_types: list[str] | None = None, work_id: str | None = None, limit: int = 20) -> dict:
        """Search original text, bibliography, identities and Wiki pages with explicit source types.

        Wiki compilations are never verbatim source quotes. Original text uses
        keyword recall; optional deep retrieval remains in the existing sessions.
        """
        from catalog.services.retrieval.objects import search
        return search(query, actor(), source_types=source_types, work_id=work_id, limit=limit)

    @tool
    def original_search(query: str, filters: dict | None = None, limit: int = 20) -> dict:
        """Search source text using STL recall, permissions, version checks and locator DTO."""
        from catalog.services.discovery_sessions import request_access, normalize_filters
        from catalog.services.retrieval.search import retrieve_channel
        user = actor()
        if not 2 <= len(query.strip()) <= 1200:
            raise ValidationError("检索词须为2至1200字符。")
        return retrieve_channel(query.strip(), "passages", normalize_filters(filters), request_access(SimpleNamespace(user=user)), limit=max(1,min(limit,50)))

    @tool
    def source_context(node_id: str, budget: int = 12000) -> dict:
        """Read a bounded logical source range, with explicit coverage and footnote references."""
        return context(get_object_or_404(m.DocumentNode,pk=node_id), actor(), budget=budget)

    @tool
    def evidence_anchor(anchor_id: str) -> dict:
        """Resolve all page segments of an exact historical source, under current permissions."""
        return locator(get_object_or_404(m.EvidenceAnchor,pk=anchor_id), actor())

    @tool
    def knowledge_page(page_id: str) -> dict:
        """Read a published knowledge page."""
        return page_data(get_object_or_404(m.KnowledgePage,pk=page_id), actor())

    @tool
    def assertion(assertion_id: str) -> dict:
        """Read a published source-specific scholarly assertion and its evidence."""
        return assertion_data(get_object_or_404(m.Assertion,pk=assertion_id), actor())

    @tool
    def create_run(document_revision_id: str, request_id: str, scope: dict | None = None) -> dict:
        """Create an asynchronous curation run. Requires editorial permission; returns its ID."""
        user = actor()
        return intelligence_queries.run_data(intelligence.create_run(get_object_or_404(m.DocumentRevision,pk=document_revision_id),
            user, request_id=request_id, scope=scope), user)

    @tool
    def run_status(run_id: str, include_artifacts: bool = False) -> dict:
        """Read real stages, coverage, errors and optional chapter artifacts."""
        return intelligence_queries.run_data(get_object_or_404(m.CurationRun,pk=run_id), actor(), detail=include_artifacts)

    @tool
    def submit_draft(document_revision_id: str, request_id: str, items: list[dict]) -> dict:
        """Submit entity/assertion/Wiki patch proposals to the SAME administrator ChangeSet queue.

        Each item has UUID id, kind, payload and dependencies. This tool cannot
        confirm, apply, publish or enable a model. Evidence is validated by STL.
        """
        user = actor()
        value = intelligence_changes.submit_draft(get_object_or_404(m.DocumentRevision,pk=document_revision_id), items,
            user, request_id=request_id, origin="mcp")
        return intelligence_queries.changeset_data(value,user)

    return server

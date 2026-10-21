"""Author identities for one activated edition or an exact source page range.

Instances are request/job-local: validate chapter provenance once per edition,
never cache publication or permission decisions across requests.
"""
from uuid import UUID

from django.db.models import BooleanField, F, Func, Q
from rest_framework.exceptions import ValidationError

from .contribution_scope import ContributionScopeError, validate_contribution_scope, whole_edition_contribution


def _id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return ""


def _authors(rows):
    names, identifiers = [], []
    for row in rows:
        person = row.get("person") if isinstance(row.get("person"), dict) else {}
        name = person.get("preferred_name") or row.get("name") or ""
        identifier = _id(row.get("person_id") or person.get("id"))
        if isinstance(name, str) and name.strip() and name not in names:
            names.append(name)
        if identifier and identifier not in identifiers:
            identifiers.append(identifier)
    return {"authors": names, "author_ids": identifiers}


def edition_author_projection(snapshot):
    rows = snapshot.get("contributions", []) if isinstance(snapshot, dict) else []
    return _authors(row for row in rows if isinstance(row, dict) and row.get("role") == "author" and whole_edition_contribution(row))


class ContributionProjection:
    def __init__(self, edition, *, snapshot=None, public=True, access_statuses=None):
        self.edition = edition
        self.access_statuses = frozenset({"public", "inherit"} if access_statuses is None else access_statuses)
        self.asset_id = self.document_revision_id = ""
        revision = getattr(edition, "active_catalog_revision", None)
        if public:
            valid = bool(revision and edition.state == "published" and revision.edition_id == edition.pk
                and revision.status == "active" and revision.metadata_ready)
            snapshot = revision.snapshot if valid else {}
            asset, document = (revision.reader_asset, revision.document_revision) if valid and revision.fulltext_ready else (None, None)
            if (asset and document and asset.edition_id == edition.pk and document.asset_id == asset.pk
                    and asset.sha256 and document.source_checksum == asset.sha256 and document.is_active
                    and asset.kind == "normalized" and asset.status == "ready" and asset.validation_status == "valid"
                    and asset.access_status in self.access_statuses and asset.file):
                self.asset_id, self.document_revision_id = _id(asset.pk), _id(document.pk)
        elif snapshot is None:
            snapshot = {"contributions": [{"role": row.role, "person_id": str(row.person_id),
                "name": row.person.preferred_name, "scope": row.scope}
                for row in edition.contributions.select_related("person").filter(approved=True, role="author")]}
        rows = snapshot.get("contributions", []) if isinstance(snapshot, dict) else []
        self.whole, self.chapters = [], []
        validated = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("role") != "author":
                continue
            if whole_edition_contribution(row):
                self.whole.append(row)
                continue
            # Invalid scopes remain unassigned; they can never become edition authors.
            scope = row.get("scope")
            key = repr(scope)
            if key not in validated:
                try:
                    validated[key] = validate_contribution_scope(edition, scope, public=public, allowed_access_statuses=self.access_statuses)
                except ContributionScopeError:
                    validated[key] = None
            normalized = validated[key]
            if normalized and normalized["kind"] == "chapter":
                self.chapters.extend((row, chapter) for chapter in normalized["chapters"])
        self.public = public

    def for_range(self, asset_id, document_revision_id, page_start, page_end=None):
        asset_id, document_revision_id = _id(asset_id), _id(document_revision_id)
        page_end = page_start if page_end is None else page_end
        if (not asset_id or not document_revision_id or type(page_start) is not int or type(page_end) is not int
                or not 1 <= page_start <= page_end or self.public and (asset_id != self.asset_id or document_revision_id != self.document_revision_id)):
            return {"authors": [], "author_ids": []}
        return _authors([*self.whole, *(row for row, chapter in self.chapters
            if chapter["asset_id"] == asset_id and chapter["document_revision_id"] == document_revision_id
            and chapter["page_start"] <= page_start <= page_end <= chapter["page_end"])])

    def matching_ranges(self, author_ids):
        """None means the whole activated edition; [] means no eligible source."""
        selected = {_id(value) for value in author_ids} - {""}
        if selected.intersection(_authors(self.whole)["author_ids"]):
            return None
        return [chapter for row, chapter in self.chapters if selected.intersection(_authors([row])["author_ids"])]


def contribution_projection(edition, *, cache=None, snapshot=None, public=True, access_statuses=None):
    if cache is None:
        return ContributionProjection(edition, snapshot=snapshot, public=public, access_statuses=access_statuses)
    key = (str(edition.pk), str(edition.active_catalog_revision_id), public, tuple(sorted({"public", "inherit"} if access_statuses is None else access_statuses)))
    if key not in cache:
        cache[key] = ContributionProjection(edition, snapshot=snapshot, public=public, access_statuses=access_statuses)
    return cache[key]


class SnapshotAuthorCandidate(Func):
    """Candidate editions include chapter authors; the range check follows later."""
    output_field = BooleanField()

    def __init__(self, author_ids):
        self.identifiers = sorted({_id(value) for value in author_ids} - {""})
        super().__init__(F("active_catalog_revision__snapshot"))

    def as_sql(self, compiler, connection, **extra_context):
        from .catalog_search import _rows_sql
        if not self.identifiers:
            return "0 = 1", []
        snapshot, params = compiler.compile(self.source_expressions[0])
        rows, identifier, _label, _whole, _text = _rows_sql(connection, snapshot, "author")
        role = "item.value->>'role'" if connection.vendor == "postgresql" else "json_extract(item.value, '$.role')"
        if connection.vendor == "sqlite":
            identifier = f"replace({identifier}, '-', '')"
            values = [value.replace("-", "") for value in self.identifiers]
        else:
            values = self.identifiers
        return f"EXISTS (SELECT 1 FROM {rows} WHERE {role} = 'author' AND {identifier} IN ({', '.join(['%s'] * len(values))}))", [*params, *params, *values]


def author_range_q(author_ids, *, asset_field, revision_field=None, page_field, end_field=None, editions=None, access_statuses=None):
    """A bounded SQL condition; exact chapter ranges never filter a whole Work."""
    from .publication_eligibility import public_editions
    rows = editions if editions is not None else public_editions(require_fulltext=True).filter(is_primary=True)
    condition = Q(pk__in=[])
    branches = 0
    for edition in rows.filter(SnapshotAuthorCandidate(author_ids)):
        projection = contribution_projection(edition, access_statuses=access_statuses)
        if not projection.asset_id or not projection.document_revision_id:
            continue
        ranges = projection.matching_ranges(author_ids)
        branches += 1 if ranges is None else len(ranges)
        if branches > 400:
            raise ValidationError("作者范围超过 400 个版本或章节，请缩小馆藏范围后重试。")
        identity = {asset_field: projection.asset_id}
        if revision_field:
            identity[revision_field] = projection.document_revision_id
        if ranges is None:
            condition |= Q(**identity)
        else:
            for chapter in ranges:
                condition |= Q(**{**identity, page_field + "__gte": chapter["page_start"],
                    (end_field or page_field) + "__lte": chapter["page_end"]})
    return condition

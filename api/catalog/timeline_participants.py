"""Explicit event roles and edition responsibility, with their separate provenance."""
from uuid import UUID

from catalog.models import Contribution, TimelineEventRelation
from catalog.services.contribution_scope import whole_edition_contribution


def participant_identity_ids(snapshot):
    result = set()
    for item in snapshot.get("contributions") or []:
        if not isinstance(item, dict) or not whole_edition_contribution(item):
            continue
        person = item.get("person") or {}
        if not isinstance(person, dict):
            continue
        try:
            result.add(UUID(str(item.get("person_id") or person.get("id"))))
        except (ValueError, TypeError):
            continue
    return result


def snapshot_participants(edition, profiles):
    if edition is None:
        return []
    snapshot = edition.active_catalog_revision.snapshot or {}
    result = []
    for item in snapshot.get("contributions") or []:
        if not isinstance(item, dict) or not whole_edition_contribution(item):
            continue
        person = item.get("person") or {}
        if not isinstance(person, dict):
            continue
        try:
            identifier = UUID(str(item.get("person_id") or person.get("id")))
        except (ValueError, TypeError):
            continue
        name, role = person.get("preferred_name") or item.get("name", ""), item.get("role", "other")
        if not isinstance(name, str) or not name.strip() or not isinstance(role, str) or role not in dict(Contribution.Role.choices):
            continue
        profile = profiles.get(identifier)
        result.append({"key": f"edition:{edition.pk}:{identifier}:{role}", "kind": "person",
            "person_id": str(identifier), "scholar_id": str(profile.pk) if profile else None,
            "name": name, "role": role, "role_label": dict(Contribution.Role.choices)[role],
            "href": f"/scholars/{profile.slug}" if profile else "", "source": "edition", "edition_id": str(edition.pk)})
    version = snapshot.get("edition") or {}
    publisher = version.get("publisher") if isinstance(version, dict) else None
    if isinstance(publisher, str) and publisher.strip():
        try:
            publisher_id = str(UUID(str(version.get("publisher_authority_id"))))
        except (ValueError, TypeError):
            publisher_id = None
        result.append({"key": f"edition:{edition.pk}:publisher", "kind": "publisher", "person_id": None,
            "publisher_authority_id": publisher_id,
            "scholar_id": None, "name": publisher, "role": "publisher", "role_label": "出版方",
            "href": "", "source": "edition", "edition_id": str(edition.pk)})
    return list({row["key"]: row for row in result}.values())


def event_participants(event, edition, profiles):
    result = snapshot_participants(edition, profiles)
    for relation in event.normalized_relations.all():
        if not relation.scholar_id:
            continue
        profile = profiles.get(relation.scholar.person_id)
        if profile is None:
            continue
        role = relation.participant_role
        result.append({"key": f"event:{event.pk}:{profile.pk}:{relation.relation_type}:{role}", "kind": "person",
            "person_id": str(profile.person_id), "scholar_id": str(profile.pk), "name": profile.person.preferred_name,
            "role": role, "role_label": dict(TimelineEventRelation.ParticipantRole.choices).get(role, "相关人物"),
            "href": f"/scholars/{profile.slug}", "source": "event", "edition_id": None})
    if event.scholar_id:
        profile = profiles.get(event.scholar.person_id)
        if profile and not any(row["source"] == "event" and row["scholar_id"] == str(profile.pk) and row["role"] == "subject" for row in result):
            result.append({"key": f"event:{event.pk}:{profile.pk}:subject", "kind": "person",
                "person_id": str(profile.person_id), "scholar_id": str(profile.pk), "name": profile.person.preferred_name,
                "role": "subject", "role_label": "事件主体", "href": f"/scholars/{profile.slug}", "source": "event", "edition_id": None})
    return list({row["key"]: row for row in result}.values())

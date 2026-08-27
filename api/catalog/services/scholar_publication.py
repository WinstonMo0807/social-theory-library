"""Keep ScholarProfile publication and Person authority eligibility aligned."""

from __future__ import annotations

from django.db import transaction

from catalog.models import Person, ScholarProfile


class ScholarPublicationError(ValueError):
    pass


PUBLICATION_REVIEWABLE_STATUSES = {
    Person.AuthorityStatus.DRAFT,
    Person.AuthorityStatus.NEEDS_REVIEW,
    Person.AuthorityStatus.VERIFIED,
}


def scholar_public_eligibility(profile: ScholarProfile) -> dict[str, object]:
    profile_published = profile.editorial_status == "published"
    person_verified = profile.person.authority_status == Person.AuthorityStatus.VERIFIED
    return {
        "eligible": profile_published and person_verified,
        "profile_published": profile_published,
        "person_authority_status": profile.person.authority_status,
        "reason": "" if profile_published and person_verified else (
            "person_authority_not_verified" if profile_published else "profile_not_published"
        ),
    }


@transaction.atomic
def ensure_scholar_public_authority(profile: ScholarProfile, *, actor=None) -> Person:
    """Verify a reviewable Person when an editor publishes its Scholar page.

    Rejected, merged and archived authority records require explicit authority
    resolution. Publishing a page must never revive one of those states.
    """

    person = Person.objects.select_for_update().get(pk=profile.person_id)
    if person.authority_status not in PUBLICATION_REVIEWABLE_STATUSES:
        raise ScholarPublicationError(
            "该人物的权威记录已拒绝、合并或归档，请先完成身份处理。"
        )
    if person.authority_status != Person.AuthorityStatus.VERIFIED:
        person.authority_status = Person.AuthorityStatus.VERIFIED
        person.save(update_fields=["authority_status", "updated_at"])
        from catalog.services.dependency_engine import record_canonical_change

        record_canonical_change(
            object_type="person",
            object_id=person.pk,
            change_kind="update",
            changed_fields=["authority_status"],
            actor=actor,
            idempotency_key=(
                f"scholar-public-authority:{person.pk}:{person.updated_at.isoformat()}"
            )[:200],
        )
    profile.person = person
    return person

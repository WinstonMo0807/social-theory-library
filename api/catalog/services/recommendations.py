from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    PublicationState,
    RecommendationItem,
    RecommendationOverride,
    RecommendationPolicy,
    RecommendationSnapshot,
    ScholarProfile,
    TheorySchool,
    Topic,
    Work,
)


PLACEMENT_TARGETS = {
    RecommendationPolicy.Placement.HOME_FEATURED: "work",
    RecommendationPolicy.Placement.HOME_RANDOM: "work",
    RecommendationPolicy.Placement.THEORY_WEEKLY: "work",
    RecommendationPolicy.Placement.HOME_THEORIES: "theory_school",
    RecommendationPolicy.Placement.HOME_SCHOLARS: "scholar",
    RecommendationPolicy.Placement.HOME_TOPICS: "topic",
}

DEFAULT_POLICIES = (
    (RecommendationPolicy.Placement.HOME_FEATURED, "首页精选馆藏", 4),
    (RecommendationPolicy.Placement.HOME_THEORIES, "首页理论传统", 4),
    (RecommendationPolicy.Placement.HOME_SCHOLARS, "首页学者", 4),
    (RecommendationPolicy.Placement.HOME_TOPICS, "首页问题主题", 4),
    (RecommendationPolicy.Placement.HOME_RANDOM, "首页随机推荐", 4),
    (RecommendationPolicy.Placement.THEORY_WEEKLY, "理论页本周馆藏", 4),
)


def ensure_default_policies():
    policies = []
    for placement, title, item_count in DEFAULT_POLICIES:
        policy, _ = RecommendationPolicy.objects.get_or_create(
            placement=placement,
            defaults={
                "title": title,
                "item_count": item_count,
                "rotation_days": 3,
                "rules": {
                    "exclude_previous_cycles": 2,
                    "published_only": True,
                    "shared_for_all_readers": True,
                },
                "enabled": True,
            },
        )
        policies.append(policy)
    return policies


def _target_key(instance):
    if isinstance(instance, Work):
        return "work", str(instance.pk)
    if isinstance(instance, TheorySchool):
        return "theory_school", str(instance.pk)
    if isinstance(instance, Topic):
        return "topic", str(instance.pk)
    if isinstance(instance, ScholarProfile):
        return "scholar", str(instance.pk)
    raise TypeError(f"Unsupported recommendation target: {type(instance)!r}")


def _target_kwargs(instance):
    field, _ = _target_key(instance)
    return {field: instance}


def _queryset_for_policy(policy):
    target = PLACEMENT_TARGETS.get(policy.placement)
    if target == "work":
        return (
            Work.objects.filter(editions__state=PublicationState.PUBLISHED)
            .prefetch_related("editions__contributions__person", "editions__assets")
            .distinct()
            .order_by("id")
        )
    if target == "theory_school":
        return TheorySchool.objects.filter(editorial_status="published").order_by("id")
    if target == "topic":
        return Topic.objects.filter(editorial_status="published").order_by("id")
    if target == "scholar":
        return ScholarProfile.objects.filter(editorial_status="published").select_related("person").order_by("id")
    return Work.objects.none()


def _override_targets(policy, action):
    targets = []
    overrides = (
        policy.overrides.filter(active=True, action=action)
        .select_related("work", "theory_school", "topic", "scholar__person")
        .order_by("position", "created_at")
    )
    for override in overrides:
        target = next(
            (
                value
                for value in (
                    override.work,
                    override.theory_school,
                    override.topic,
                    override.scholar,
                )
                if value is not None
            ),
            None,
        )
        if target is not None:
            targets.append((override, target))
    return targets


def _recent_target_keys(policy):
    cycle_count = max(0, int(policy.rules.get("exclude_previous_cycles", 2)))
    snapshots = policy.snapshots.order_by("-starts_at")[:cycle_count]
    keys = set()
    for item in RecommendationItem.objects.filter(snapshot__in=snapshots):
        for field in PLACEMENT_TARGETS.values():
            identifier = getattr(item, f"{field}_id", None)
            if identifier:
                keys.add((field, str(identifier)))
    return keys


def _diverse_work_order(candidates, rng):
    buckets = defaultdict(list)
    for work in candidates:
        buckets[work.document_type].append(work)
    for values in buckets.values():
        rng.shuffle(values)
    document_types = list(buckets)
    rng.shuffle(document_types)
    ordered = []
    while any(buckets.values()):
        for document_type in document_types:
            if buckets[document_type]:
                ordered.append(buckets[document_type].pop())
    return ordered


def _automatic_targets(policy, starts_at, *, preferred_targets=()):
    seed = hashlib.sha256(
        f"{policy.placement}:{starts_at.isoformat()}".encode("utf-8")
    ).hexdigest()
    rng = random.Random(seed)
    excluded = {_target_key(target) for _, target in _override_targets(policy, RecommendationOverride.Action.EXCLUDE)}
    recent = _recent_target_keys(policy)
    allowed = list(_queryset_for_policy(policy))
    allowed_by_key = {_target_key(target): target for target in allowed}
    prioritized = []
    prioritized_keys = set()
    preferred_keys = set()

    for target in preferred_targets:
        key = _target_key(target)
        if key not in allowed_by_key or key in prioritized_keys:
            continue
        prioritized.append(allowed_by_key[key])
        prioritized_keys.add(key)
        preferred_keys.add(key)

    for _, target in _override_targets(policy, RecommendationOverride.Action.PIN):
        key = _target_key(target)
        if key not in allowed_by_key or key in prioritized_keys:
            continue
        prioritized.append(allowed_by_key[key])
        prioritized_keys.add(key)

    candidates = [
        candidate
        for candidate in allowed
        if _target_key(candidate) not in excluded and _target_key(candidate) not in prioritized_keys
    ]
    fresh = [candidate for candidate in candidates if _target_key(candidate) not in recent]
    needed = max(0, policy.item_count - len(prioritized))
    pool = fresh if len(fresh) >= needed else candidates
    if PLACEMENT_TARGETS.get(policy.placement) == "work":
        pool = _diverse_work_order(pool, rng)
    else:
        rng.shuffle(pool)
    return (prioritized + pool)[: policy.item_count], seed, preferred_keys


@transaction.atomic
def generate_snapshot(policy, *, actor=None, selected_targets=None, source=None, now=None):
    now = now or timezone.now()
    policy = RecommendationPolicy.objects.select_for_update().get(pk=policy.pk)
    RecommendationSnapshot.objects.filter(policy=policy, is_current=True).update(is_current=False)
    if selected_targets is None:
        targets, seed, manual_keys = _automatic_targets(policy, now)
    elif policy.placement == RecommendationPolicy.Placement.HOME_SCHOLARS:
        targets, rotation_seed, manual_keys = _automatic_targets(
            policy,
            now,
            preferred_targets=selected_targets,
        )
        seed = f"manual-selection:{rotation_seed}"
    else:
        allowed_by_key = {
            _target_key(target): target
            for target in _queryset_for_policy(policy)
        }
        targets = []
        manual_keys = set()
        for target in selected_targets:
            key = _target_key(target)
            if key not in allowed_by_key or key in manual_keys:
                continue
            targets.append(allowed_by_key[key])
            manual_keys.add(key)
            if len(targets) >= policy.item_count:
                break
        seed = "manual-selection"
    source = source or (
        RecommendationSnapshot.Source.MANUAL
        if actor is not None or selected_targets is not None
        else RecommendationSnapshot.Source.AUTOMATIC
    )
    expires_at = now + timedelta(days=max(1, policy.rotation_days))
    snapshot = RecommendationSnapshot.objects.create(
        policy=policy,
        starts_at=now,
        expires_at=expires_at,
        source=source,
        seed=seed,
        is_current=True,
        created_by=actor,
    )
    RecommendationItem.objects.bulk_create(
        [
            RecommendationItem(
                snapshot=snapshot,
                position=index,
                reason=(
                    "管理员策展"
                    if _target_key(target) in manual_keys
                    else "三天自动补足"
                    if selected_targets is not None
                    else "三天自动轮换"
                ),
                **_target_kwargs(target),
            )
            for index, target in enumerate(targets)
        ]
    )
    policy.last_generated_at = now
    policy.next_refresh_at = expires_at
    policy.updated_by = actor or policy.updated_by
    policy.save(update_fields=["last_generated_at", "next_refresh_at", "updated_by", "updated_at"])
    return snapshot


def _active_snapshot(policy, now):
    return (
        policy.snapshots.filter(is_current=True, starts_at__lte=now, expires_at__gt=now)
        .prefetch_related(
            "items__work__editions__contributions__person",
            "items__work__editions__assets",
            "items__theory_school",
            "items__topic",
            "items__scholar__person",
        )
        .first()
    )


def _snapshot_scholars_are_public(policy, snapshot):
    if policy.placement != RecommendationPolicy.Placement.HOME_SCHOLARS:
        return True
    scholar_ids = [item.scholar_id for item in snapshot.items.all()]
    if any(identifier is None for identifier in scholar_ids):
        return False
    published_ids = set(
        ScholarProfile.objects.filter(
            pk__in=scholar_ids,
            editorial_status="published",
        ).values_list("pk", flat=True)
    )
    return all(identifier in published_ids for identifier in scholar_ids)


def _valid_manual_scholars(snapshot):
    if snapshot.source != RecommendationSnapshot.Source.MANUAL:
        return []
    scholar_ids = [
        item.scholar_id
        for item in snapshot.items.all()
        if item.scholar_id and item.reason == "管理员策展"
    ]
    published_ids = set(
        ScholarProfile.objects.filter(
            pk__in=scholar_ids,
            editorial_status="published",
        ).values_list("pk", flat=True)
    )
    return [
        item.scholar
        for item in snapshot.items.all()
        if item.scholar_id in published_ids and item.reason == "管理员策展"
    ]


@transaction.atomic
def _generate_due_snapshot(policy, requested_at):
    policy = RecommendationPolicy.objects.select_for_update().get(pk=policy.pk)
    checked_at = max(requested_at, timezone.now())
    snapshot = _active_snapshot(policy, checked_at)
    if snapshot is not None and _snapshot_scholars_are_public(policy, snapshot):
        return snapshot
    selected_targets = _valid_manual_scholars(snapshot) if snapshot is not None else []
    return generate_snapshot(
        policy,
        now=checked_at,
        selected_targets=selected_targets or None,
        source=(
            RecommendationSnapshot.Source.MANUAL
            if selected_targets
            else RecommendationSnapshot.Source.AUTOMATIC
        ),
    )


def current_snapshot(policy, *, now=None):
    now = now or timezone.now()
    snapshot = _active_snapshot(policy, now)
    if snapshot is not None and _snapshot_scholars_are_public(policy, snapshot):
        return snapshot
    return _generate_due_snapshot(policy, now)


def current_recommendations():
    payload = {}
    for policy in ensure_default_policies():
        if policy.enabled:
            payload[policy.placement] = current_snapshot(policy)
    return payload

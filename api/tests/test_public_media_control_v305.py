import pytest

from catalog.services.public_knowledge_control import (
    _module_state,
    admin_field_usage,
    page_contracts,
)


@pytest.mark.parametrize(
    ("object_type", "field", "module_id"),
    (
        ("scholar", "portrait_selection", "scholar-identity"),
        ("theory", "image_selection", "theory-identity"),
    ),
)
def test_media_selection_reports_its_real_public_module_as_draft(object_type, field, module_id):
    usage = next(row for row in admin_field_usage(object_type) if row["field"] == field)
    assert usage["consumers"] == [module_id]
    module = next(
        module
        for page in page_contracts(object_type)
        for module in page.modules
        if module.module_id == module_id
    )
    state = _module_state(
        module,
        {},
        changed_fields={field},
        candidate_available=False,
        evidence_available=False,
    )
    assert state["status"] == "draft"
    assert state["has_draft"] is True

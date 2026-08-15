from datetime import date

from django.core.exceptions import ValidationError
import pytest

from catalog.models import (
    Asset,
    DocumentType,
    Edition,
    KnowledgeNode,
    Person,
    PublisherAuthority,
    Work,
)
from catalog.serializers import EditionCompactSerializer, WorkCardSerializer
from catalog.theory_serializers import AdminKnowledgeNodeSerializer, KnowledgeNodeListSerializer


@pytest.mark.django_db
def test_bibliographic_foundation_reuses_legacy_verbatim_fields():
    publisher = PublisherAuthority.objects.create(canonical_name="生活·读书·新知三联书店")
    original = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="The Sociological Imagination",
        language="en",
        original_language="en",
        first_publication_date=date(1959, 1, 1),
    )
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="社会学的想象力",
        original_title="The Sociological Imagination",
        uniform_title="Sociological imagination. Chinese",
        language="zh-CN",
        original_language="en",
        translation_of=original,
    )
    edition = Edition.objects.create(
        work=work,
        version_label="第 2 版",
        publisher="生活·读书·新知三联书店",
        publication_place="北京",
        publisher_authority=publisher,
        distribution_place="北京",
        distributor="新华书店",
        manufacture_place="河北",
        manufacturer="某印刷厂",
        isbn="9787108009826",
        isbn13="9787108009826",
        series="社会学译丛",
        extent="320 页",
        responsibility_statement="C. 赖特·米尔斯著；陈强、张永强译",
    )

    assert edition.edition_statement == "第 2 版"
    assert edition.publisher_verbatim == edition.publisher
    assert edition.publication_place_verbatim == edition.publication_place
    assert "the sociological imagination" in work.search_aliases

    serialized = WorkCardSerializer(work).data
    assert serialized["translation_of"] == original.id
    edition_data = EditionCompactSerializer(edition).data
    assert edition_data["edition_statement"] == "第 2 版"
    assert edition_data["publisher_verbatim"] == "生活·读书·新知三联书店"
    assert edition_data["publisher_authority"] == publisher.id


@pytest.mark.django_db
def test_asset_provenance_and_access_fields_are_additive():
    work = Work.objects.create(document_type=DocumentType.BOOK, title="数字文件测试")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file="archive/test/original.pdf",
        original_filename="原始扫描件.pdf",
        mime_type="application/pdf",
        sha256="a" * 64,
        text_layer_quality=0.35,
        language_guess="zh-Hans",
        access_status=Asset.AccessStatus.RESTRICTED,
        rights_note="仅限馆内访问",
    )

    assert asset.original_filename == "原始扫描件.pdf"
    assert asset.access_status == Asset.AccessStatus.RESTRICTED
    assert asset.text_layer_quality == pytest.approx(0.35)

    asset.text_layer_quality = 1.1
    with pytest.raises(ValidationError):
        asset.full_clean()


@pytest.mark.django_db
def test_authority_status_defaults_to_draft():
    person = Person.objects.create(preferred_name="待消歧人物")
    assert person.authority_status == Person.AuthorityStatus.DRAFT


@pytest.mark.django_db
def test_work_translation_cycle_is_rejected_before_save():
    first = Work.objects.create(document_type=DocumentType.BOOK, title="原作")
    second = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="译作",
        translation_of=first,
    )
    first.translation_of = second

    with pytest.raises(ValidationError, match="译作关系不能形成循环"):
        first.full_clean()


@pytest.mark.django_db
def test_knowledge_node_parent_cycle_is_rejected_and_public_parent_is_controlled():
    root = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.DISCIPLINE,
        canonical_name_zh="社会科学",
        slug="social-sciences-foundation",
        status="published",
    )
    child = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.TOPIC,
        canonical_name_zh="社会分层",
        slug="social-stratification-foundation",
        parent=root,
        status="published",
    )

    public_data = KnowledgeNodeListSerializer(child).data
    assert public_data["parent"] == root.id

    serializer = AdminKnowledgeNodeSerializer(
        root,
        data={"parent": str(child.id)},
        partial=True,
    )
    assert not serializer.is_valid()
    assert "不能形成循环" in str(serializer.errors["parent"][0])

    root.parent = child
    with pytest.raises(ValidationError, match="知识节点层级不能形成循环"):
        root.full_clean()

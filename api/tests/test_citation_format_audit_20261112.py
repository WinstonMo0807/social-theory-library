"""Book-format comparisons against identified publisher/standard examples.

These exercise text fields and punctuation, not Word typography or metadata
completeness. Fixture names are already bibliographically ordered; unstructured
live names cannot establish surname/initial correctness.
"""
from types import SimpleNamespace
from copy import deepcopy

import pytest

from catalog.services.citations import citation_bundle, citation_edition


def book(title, author, year, publisher, place="", version="", translators=()):
    return {"work": {"title": title, "document_type": "book"},
            "edition": {"publication_year": year, "publisher": publisher,
                        "publication_place": place, "version_label": version},
            "contributions": [{"role": role, "person": {"preferred_name": name}}
                              for role, names in (("author", [author] if author else []), ("translator", translators))
                              for name in names]}


def bundle(snapshot, page=""):
    return citation_bundle(SimpleNamespace(id="example"), page, snapshot=snapshot)


@pytest.mark.parametrize(("raw", "expected"), [
    ("2016年4月第1版，北京第1次印刷", ""), ("第一版", ""),
    ("2016年4月第一版 2018年北京第3次印刷", ""),
    ("2019年6月第二版，北京第3次印刷", "2版"), ("第十二版", "12版"),
    ("新1版", "新1版"), ("修订版", "修订版"), ("影印本", "影印本"),
    ("1st ed., 3rd printing", ""), ("2nd ed., 3rd printing", "2nd ed."),
    ("Rev. ed.", "Rev. ed."), ("第零版", "第零版"),
])
def test_edition_is_not_printing_or_first_edition(raw, expected):
    assert citation_edition(raw) == expected


def test_gbt_standard_appendix_b1_translated_book():
    # GB/T 7714-2025 B.1 [10]; template punctuation normalized to ASCII.
    sample = book("经济数学与金融数学", "哈里森", 2012, "中国人民大学出版社", "北京", translators=["谢远涛"])
    sample["contributions"].insert(1, {"role": "author", "name": "沃尔德伦"})
    assert bundle(sample, "235-236")["gbt7714-2025"] == "哈里森, 沃尔德伦. 经济数学与金融数学[M]. 谢远涛, 译. 北京: 中国人民大学出版社, 2012: 235-236."


def test_apa_official_authored_book_edition_and_doi():
    # apastyle.apa.org/style-grammar-guidelines/references/examples/book-references
    sample = book("The psychology of prejudice: From attitudes to social action", "Jackson, L. M.", 2019, "American Psychological Association", version="2nd ed.")
    sample["edition"]["doi"] = "10.1037/0000168-000"
    assert bundle(sample)["apa"] == "Jackson, L. M. (2019). The psychology of prejudice: From attitudes to social action (2nd ed.). American Psychological Association. https://doi.org/10.1037/0000168-000"
    assert bundle(sample, "12")["apa"].endswith("文内引用：(Jackson, 2019, p. 12)")


def test_mla_official_authored_book():
    # style.mla.org/works-cited/citations-by-format/books/
    sample = book("Wolf Hall", "Mantel, Hilary", 2010, "Picador")
    assert bundle(sample)["mla"] == "Mantel, Hilary. Wolf Hall. Picador, 2010."
    assert bundle(sample, "12")["mla"].endswith("文内引用：(Mantel 12)")


def test_chicago18_official_translation_and_note_location():
    # chicagomanualofstyle.org/tools_citationguide/citation-guide-1.html
    sample = book("The Wedding Party", "Liu Xinwu", 2021, "Amazon Crossing", translators=["Jeremy Tiang"])
    assert bundle(sample)["chicago"] == "Liu Xinwu. The Wedding Party. Translated by Jeremy Tiang. Amazon Crossing, 2021."
    assert bundle(sample, "279")["chicago"].endswith("脚注：Liu Xinwu, The Wedding Party, trans. Jeremy Tiang (Amazon Crossing, 2021), 279.")


def test_leeds_harvard_published_book_example_is_not_apa():
    # library.leeds.ac.uk/referencing-examples/9/leeds-harvard/73/book
    sample = book("Electric transmission of water power", "Adams, A.D.", 1906, "McGraw", "New York")
    assert bundle(sample)["harvard"] == "Adams, A.D. 1906. Electric transmission of water power. New York: McGraw."
    assert bundle(sample)["harvard"] != bundle(sample)["apa"]


def test_reported_book_and_all_formats_preserve_metadata_but_drop_print_run():
    sample = book("西太平洋上的航海者", "布罗尼斯拉夫·马林诺夫斯基", 2016, "商务印书馆", "北京", "2016年4月第1版，北京第1次印刷")
    original = deepcopy(sample)
    outputs = bundle(sample)
    assert outputs["gbt7714-2025"] == "布罗尼斯拉夫·马林诺夫斯基. 西太平洋上的航海者[M]. 北京: 商务印书馆, 2016."
    for style in ["gbt7714-2025", "apa", "mla", "chicago", "harvard"]:
        assert "印刷" not in outputs[style] and "4月" not in outputs[style] and "1版" not in outputs[style]
        assert "英国" not in outputs[style] and "波兰" not in outputs[style]
    assert sample == original
    assert outputs["csl"]["edition"] == ""


def test_translator_scope_and_revised_edition_across_all_styles():
    sample = book("测试书", "作者甲", 2020, "测试出版社", "北京", "第二版", ["译者甲"])
    sample["contributions"].append({"role": "translator", "name": "仅译章节", "scope": {"kind": "chapter", "chapters": []}})
    outputs = bundle(sample)
    for style in ["gbt7714-2025", "apa", "mla", "chicago", "harvard"]:
        assert "2版" in outputs[style] and "译者甲" in outputs[style]
        assert "仅译章节" not in outputs[style]


def test_apa_and_mla_official_edited_book_examples():
    sample = book("Nanotechnology based approaches for tuberculosis treatment", "", 2020, "Academic Press")
    sample["contributions"] = [{"role": "editor", "name": "Kesharwani, P."}]
    assert bundle(sample)["apa"] == "Kesharwani, P. (Ed.). (2020). Nanotechnology based approaches for tuberculosis treatment. Academic Press."
    sample = book("Mexican Literature in Theory", "", 2018, "Bloomsbury")
    sample["contributions"] = [{"role": "editor", "name": "Sánchez Prado, Ignacio M."}]
    assert bundle(sample)["mla"] == "Sánchez Prado, Ignacio M., editor. Mexican Literature in Theory. Bloomsbury, 2018."
    assert bundle(sample)["csl"]["author"] == []
    assert bundle(sample)["csl"]["editor"] == [{"literal": "Sánchez Prado, Ignacio M."}]

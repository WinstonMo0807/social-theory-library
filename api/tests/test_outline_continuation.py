"""Continuation pages with split OCR labels must reach the same outline parser."""
import fitz
import pytest
from catalog.models import Asset, Edition, Page, Work
from catalog.services.document_outline import extract_outline, _split_contents_pairs


@pytest.mark.django_db
def test_split_label_contents_continues_across_pages(tmp_path):
    path = tmp_path / "split-contents.pdf"
    with fitz.open() as pdf:
        for _ in range(5):
            pdf.new_page()
        pdf.save(path)
    work = Work.objects.create(title="Split contents fixture")
    asset = Asset.objects.create(edition=Edition.objects.create(work=work), page_count=5)
    texts = ["Contents\nChapter One .... 1", "Chapter Two\n2\nSection A\n2\nSection B\n3",
             "Chapter One\nA normal sentence.\n1949\nAnother sentence.\n1950",
             "Chapter Two\nSection A", "Section B"]
    for number, text in enumerate(texts, 1):
        Page.objects.create(asset=asset, index=number, text=text, printed_label=str(number - 2) if number > 2 else "")
    nodes, diagnostics = extract_outline(asset, path)
    printed = [node for node in nodes if node["source"] == "printed_contents"]
    assert [(n["title"], n["pdf_page"]) for n in printed] == [
        ("Chapter One", 3), ("Chapter Two", 4), ("Section A", 4), ("Section B", 5)]
    assert {n["contents_page"] for n in printed} == {1, 2}


def test_numbers_and_body_sentences_are_not_contents_pairs():
    from catalog.services.outline_automatic import _body_key
    assert _split_contents_pairs(["Only one heading", "12", "13", "14"]) == 1
    assert _split_contents_pairs(["这是一段正文。", "12", "另一段正文；", "13", "是否如此？", "14"]) == 0
    assert _body_key("Chapter One") == "chapterone"


def test_wrapped_titles_and_alternating_margins_keep_chapter_scope():
    from types import SimpleNamespace
    from uuid import uuid4
    from catalog.services.outline_automatic import automatic_nodes

    class Rows(list):
        def order_by(self, *args): return self
        def prefetch_related(self, *args): return self
        def all(self): return self

    def page(number, label, rows):
        return SimpleNamespace(index=number, printed_label=label, label_segment="", width=1000,
            height=1000, geometry={}, text="\n\n".join(t for t,x,y,width in rows), blocks=Rows(SimpleNamespace(text=t, bbox=[x,y,x+width,y+20])
                for t,x,y,width in rows))

    pages = Rows([
        page(1,"",[("第 1 章 地方权力",100,200,350),("9",800,200,30),
                   ("常规与动员：",200,250,250),("制度关系",250,280,180),("10",800,280,30)]),
        page(2,"",[("第2章 官僚组织",150,200,350),("11",800,200,30),
                   ("正文范围",250,250,250),("12",800,250,30)]),
        page(3,"9",[("地方权力",100,200,300),("制度关系",100,400,200)]),
        page(4,"10",[("常规与动员：",100,200,300),("制度关系",120,230,240)]),
        page(5,"11",[("官僚组织",150,200,300),("对官僚组织的进一步讨论。",100,600,500)]),
        page(6,"12",[("正文范围",100,200,300)]),
    ])
    asset = SimpleNamespace(pk=uuid4(), pages=pages, validation_details={})
    nodes, diagnostics = automatic_nodes(asset,[{"contents_page":1},{"contents_page":2}])
    assert [(n["pdf_page"],n["level"]) for n in nodes] == [(3,1),(4,2),(5,1),(6,2)]
    assert nodes[1]["title"] == "常规与动员： 制度关系"
    assert nodes[1]["parent_id"] == nodes[0]["id"]
    assert nodes[3]["parent_id"] == nodes[2]["id"]
    assert not any(d["code"] == "unresolved_contents" for d in diagnostics)
    from catalog.services.knowledge_sources import _outline_heading
    assert _outline_heading(pages[4].text,nodes[2]) == ("官僚组织",0)
    assert _outline_heading("改变了页面正文。\n"+pages[4].text,nodes[2])[1] is None
    assert nodes[1]["source_locator"]["raw_text_range"]["exact"] == "常规与动员：\n\n制度关系"


def test_part_chapter_tree_with_single_dot_labels_and_reordered_ocr():
    from types import SimpleNamespace
    from uuid import uuid4
    from copy import deepcopy
    from catalog.services.outline_automatic import automatic_nodes
    from catalog.services.knowledge_sources import _outline_heading

    class Rows(list):
        def order_by(self, *args): return self
        def prefetch_related(self, *args): return self
        def all(self): return self

    def page(number, label, rows):
        return SimpleNamespace(index=number, printed_label=label, label_segment="", width=1000,
            height=1000, geometry={"schema":1,"coordinate_space":"pymupdf_unrotated",
                "page_rect":[0,0,1000,1000],"crop_box":[0,0,1000,1000],"rotation":0,
                "rotation_matrix":[1,0,0,1,0,0]},
            text="\n\n".join(t for t,x,y,w in rows), blocks=Rows(SimpleNamespace(text=t,bbox=[x,y,x+w,y+20]) for t,x,y,w in rows))

    # The body stores title fragments before the chapter number; it must stay
    # immutable even though the navigation label follows visual reading order.
    pages = Rows([
        page(1,"",[("帐目",100,100,100),("第一部分 理论",100,200,300),("第一章 方法",130,250,300),(".3",800,250,30),
                   ("第二部分 机制",100,310,300),("第一章 “权力”",130,360,300),(".5",800,360,30),
                   ("参考书目",100,420,300),("7",800,420,30),
                   ("译者后记",100,460,300),("8",800,460,30),
                   ("附录甲",100,500,300),("9",800,500,30),
                   ("附录乙",100,540,300),("10",800,540,30)]),
        page(2,"2",[("理论",450,200,100),("第一部分",100,200,200)]),
        page(3,"3",[("第一章 方法",100,200,300)]),
        page(4,"4",[("第二部分 机制",100,200,350)]),
        page(5,"5",[("“权",400,200,45),("力”",460,200,45),("第一章",100,200,200),
                    ("这是正文而非标题。",100,500,400)]),
        page(6,"6",[("第二部分 | 第一章 权力",100,40,500),("这是另一页正文。",100,200,400)]),
        page(7,"7",[("参考书目",100,200,300)]),
        page(8,"8",[("译者后记",100,200,300)]),
        page(9,"9",[("附录甲",100,200,300)]),
        page(10,"10",[("附录乙",100,200,300)]),
    ])
    asset=SimpleNamespace(pk=uuid4(),pages=pages,validation_details={})
    nodes, diagnostics=automatic_nodes(asset,[])
    assert [(n['pdf_page'],n['level']) for n in nodes]==[(2,1),(3,2),(4,1),(5,2),(7,1),(8,1),(9,1),(10,1)]
    assert any(d['code']=='contents_layout_observed' and d['pages']==[1] for d in diagnostics)
    assert nodes[1]['parent_id']==nodes[0]['id'] and nodes[3]['parent_id']==nodes[2]['id']
    assert not any(d['code']=='unresolved_contents' for d in diagnostics)
    assert _outline_heading(pages[4].text,nodes[3]) == ('第一章 “权力”',0)
    assert _outline_heading(pages[1].text,nodes[0]) == ('第一部分 理论',0)
    assert _outline_heading('X'+pages[4].text,nodes[3])[1] is None
    changed=deepcopy(nodes[3]);changed['source_locator']['raw_text_fragments'][0]['exact']='错误'
    assert _outline_heading(pages[4].text,changed)[1] is None
    from catalog.services.knowledge_sources import _heading_kind
    assert _heading_kind(nodes[3]['title'],2)=='chapter'
    assert _heading_kind('参考书目',1)=='references'
    assert _heading_kind('译者后记',1)=='appendix'

    # An English-only TOC part without a body title cannot alter chapter level.
    pages[0].blocks.append(SimpleNamespace(text='Part IV Unlocated',bbox=[100,600,500,620]))
    pages[0].text+='\n\nPart IV Unlocated'
    asset.pages=Rows([pages[0],pages[2],pages[4],*pages[6:]])
    nodes, diagnostics=automatic_nodes(asset,[])
    assert all(n['level']==1 for n in nodes)
    assert any(d['code']=='unresolved_contents' for d in diagnostics)

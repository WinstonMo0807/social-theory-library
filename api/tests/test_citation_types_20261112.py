"""Official style examples plus explicitly synthetic name/metadata cases.

APA: apastyle.apa.org/style-grammar-guidelines/references/examples/
MLA: style.mla.org/page-range-and-doi/
Chicago: chicagomanualofstyle.org/tools_citationguide/citation-guide-1.html
Leeds: library.leeds.ac.uk/directory_record/74/book-chapter-in-an-edited-book
GB/T 7714—2025: 7.1, 8.2, Appendix B (source links in audit record).
"""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from catalog.services.citations import citation_bundle, _name, citation_metadata_notes
from tests.test_citation_format_audit_20261112 import book, bundle


def item(kind, title, author, year, **values):
    s = book(title, author, year, values.pop('publisher', ''))
    s['work']['document_type'] = kind
    s['edition'].update(values)
    return s


def test_apa_official_article_and_quoted_page_do_not_overwrite_full_range():
    s = item('journal_article', 'Emotions in storybooks: A comparison of storybooks that represent ethnic and racial groups in the United States', 'Grady, J. S.', 2019,
             journal_title='Psychology of Popular Media Culture', volume='8', issue='3', page_range='207–217', doi='10.1037/ppm0000185')
    s['contributions'] += [{'role': 'author', 'name': name} for name in ['Her, M.', 'Moreno, G.', 'Perez, C.', 'Yelinek, J.']]
    expected = 'Grady, J. S., Her, M., Moreno, G., Perez, C., & Yelinek, J. (2019). Emotions in storybooks: A comparison of storybooks that represent ethnic and racial groups in the United States. Psychology of Popular Media Culture, 8(3), 207–217. https://doi.org/10.1037/ppm0000185'
    assert bundle(s)['apa'] == expected
    assert bundle(s, '210')['apa'] == expected + '\n\n文内引用：(Grady et al., 2019, p. 210)'
    assert bundle(s, '210')['csl']['page'] == '207–217'
    assert '[J/OL]' not in bundle(s)['gbt7714-2025']  # A DOI alone is not a carrier declaration.


def test_apa_official_edited_chapter():
    s = item('chapter', 'Currents in the study of persuasion', 'Dillard, J. P.', 2020, publisher='Routledge', container_title='Media effects: Advances in theory and research', version_label='4th ed.', page_range='115–129')
    s['contributions'] += [{'role': 'editor', 'name': n} for n in ['Oliver, M. B.', 'Raney, A. A.', 'Bryant, J.']]
    assert bundle(s)['apa'] == 'Dillard, J. P. (2020). Currents in the study of persuasion. In M. B. Oliver, A. A. Raney, & J. Bryant (Eds.), Media effects: Advances in theory and research (4th ed., pp. 115–129). Routledge.'
    assert '//Oliver M B, Raney A A, Bryant J. Media effects' in bundle(s)['gbt7714-2025']


def test_mla_official_online_article():
    s = item('journal_article', 'The Necessity of Language Learning', 'Berman, Russell', 2015, journal_title='ADFL Bulletin', volume='43', issue='2', page_range='11-14', doi='10.1632/adfl.43.2.11')
    assert bundle(s)['mla'] == 'Berman, Russell. “The Necessity of Language Learning.” ADFL Bulletin, vol. 43, no. 2, 2015, pp. 11-14, https://doi.org/10.1632/adfl.43.2.11.'


def test_chicago_official_article_note():
    s = item('journal_article', 'Inclusion Work: Children of Immigrants Claiming Membership in Everyday Life', 'Kwon, Hyeyoung', 2022, journal_title='American Journal of Sociology', volume='127', issue='6', page_range='1818–59', doi='10.1086/720277')
    assert bundle(s,'1842–43')['chicago'].split('脚注：')[1] == 'Hyeyoung Kwon, “Inclusion Work: Children of Immigrants Claiming Membership in Everyday Life,” American Journal of Sociology 127, no. 6 (2022): 1842–43, https://doi.org/10.1086/720277.'
    assert '1818–59' in bundle(s,'1842–43')['chicago'].split('脚注：')[0]


def test_leeds_official_chapter_and_thesis():
    s = item('chapter','Molecular biology of HIV','Coffin, J.M.',1999,container_title='The evolution of HIV',publisher='Johns Hopkins Press',publication_place='Baltimore',page_range='3-40')
    s['contributions'].append({'role':'editor','name':'Crandell, K.A.'})
    assert bundle(s)['harvard'] == 'Coffin, J.M. 1999. Molecular biology of HIV. In: Crandell, K.A. ed. The evolution of HIV. Baltimore: Johns Hopkins Press, pp.3-40.'
    s = item('thesis','Three essays in financial economics','Dang, V.A.',2007,degree_type='博士',degree_institution='University of Leeds')
    assert bundle(s)['harvard'] == 'Dang, V.A. 2007. Three essays in financial economics. Ph.D. thesis, University of Leeds.'
    assert '[D]' in bundle(s)['gbt7714-2025'] and 'University of Leeds' in bundle(s)['gbt7714-2025']


@pytest.mark.parametrize(('name','style','expected'),[
    ('de la Cruz, María-José','apa','de la Cruz, M.-J.'),
    ('Godard, Jean-Luc','gbt','Godard J-L'),
    ('Scott, James C.','gbt','Scott J C'),
    ('Sánchez Prado, Ignacio M.','apa','Sánchez Prado, I. M.'),
    ('King, Martin Luther, Jr.','apa','King, M. L., Jr.'),
    ('张三','apa','张三'),('American Chemical Society','apa','American Chemical Society'),
    ('伊本·凯西尔','gbt','伊本·凯西尔'),
])
def test_names_use_explicit_order_and_preserve_unstructured_names(name,style,expected):
    assert _name(name,style) == expected


def test_confirmed_citation_name_never_changes_display_name_or_draft_snapshot():
    s=book('西太平洋上的航海者','布罗尼斯拉夫·马林诺夫斯基',2016,'商务印书馆','北京',translators=['弓秀英'])
    s['contributions'][0]['person']['citation_name']='马林诺夫斯基'
    before=deepcopy(s)
    assert bundle(s,'93')['gbt7714-2025']=='马林诺夫斯基. 西太平洋上的航海者[M]. 弓秀英, 译. 北京: 商务印书馆, 2016: 93.'
    for style in ('apa', 'mla', 'chicago', 'harvard'):
        assert bundle(s,'93')[style].startswith('布罗尼斯拉夫·马林诺夫斯基')
    assert s==before
    assert citation_metadata_notes(SimpleNamespace(id='example'),s)==[]


def test_catalog_volume_identity_survives_printing_cleanup():
    upper = book('世界的苦难', '布尔迪厄', 2017, '中国人民大学出版社', '北京', version='2017年版（上卷）')
    lower = deepcopy(upper)
    lower['edition']['version_label'] = '2017年版（下卷）'
    for style in ('gbt7714-2025', 'apa', 'mla', 'chicago', 'harvard'):
        assert '上卷' in bundle(upper)[style]
        assert '下卷' in bundle(lower)[style]
        assert bundle(upper)[style] != bundle(lower)[style]
    assert upper['work']['title'] == '世界的苦难'


def test_apa_translation_original_year_and_many_authors():
    s=book('Example translation','Doe, Jane',2020,'Example Press',translators=['Roe, Richard'])
    s['work']['first_publication_date']='1900-01-01'
    assert '(R. Roe, Trans.)' in bundle(s)['apa']
    assert bundle(s,'5')['apa'].endswith('(Original work published 1900)\n\n文内引用：(Doe, 1900/2020, p. 5)')
    s['contributions']=[{'role':'author','name':f'Author{i}, Alice'} for i in range(21)]
    text=bundle(s)['apa']
    assert 'Author18, A., … Author20, A.' in text and 'Author19' not in text


def test_report_corporate_author_does_not_duplicate_publisher_in_apa():
    s=item('report','Example report','World Health Organization',2020,report_institution='World Health Organization',publication_place='Geneva')
    assert bundle(s)['apa']=='World Health Organization. (2020). Example report.'
    assert bundle(s)['gbt7714-2025']=='World Health Organization. Example report[R]. Geneva: World Health Organization, 2020.'


@pytest.mark.parametrize('kind',['journal_article','chapter','thesis','report','journal_issue','other'])
def test_all_catalog_types_keep_identity_without_invented_metadata(kind):
    s=item(kind,'测试资料','作者',2020)
    result=bundle(s,'xv')
    for style in ['gbt7714-2025','apa','mla','chicago','harvard']:
        assert '测试资料' in result[style] and 'None' not in result[style]
    assert result['csl']['type'] != 'book'


def test_leeds_official_translated_book():
    s = book('Metamorphosis and other stories', 'Kafka, F.', 2007, 'Penguin Books', 'New York', translators=['Hoffman, M.'])
    assert bundle(s)['harvard'] == 'Kafka, F. 2007. Metamorphosis and other stories. Translated by M. Hoffman. New York: Penguin Books.'


def test_gbt_translated_chapter_keeps_translator_container_edition_and_locator():
    # Synthetic metadata exercising the order in GB/T 7714—2025 §8.3.2.
    s = item('chapter', '示例章节', '作者', 2020, container_title='示例论文集',
             publisher='示例出版社', publication_place='北京', version_label='第2版', page_range='10-30')
    s['contributions'] += [{'role': 'translator', 'name': '译者'}, {'role': 'editor', 'name': '编者'}]
    assert bundle(s, '18')['gbt7714-2025'] == '作者. 示例章节[M]. 译者, 译//编者. 示例论文集. 2版. 北京: 示例出版社, 2020: 18.'
    assert '10-30' in bundle(s)['gbt7714-2025']


@pytest.mark.parametrize('kind', ['journal_article', 'chapter', 'thesis', 'report', 'journal_issue', 'other'])
def test_explicit_nonbook_translation_survives_each_format(kind):
    s = item(kind, '测试资料', 'Doe, Jane', 2020)
    s['contributions'].append({'role': 'translator', 'name': 'Roe, Richard'})
    for style in ['gbt7714-2025', 'apa', 'mla', 'chicago', 'harvard']:
        assert 'Roe' in bundle(s, '5')[style].split('\n\n')[0]


def test_apa_official_editor_translator_and_republished_chapter():
    s = book('Civilization and its discontents', 'Freud, S.', 2010, 'W. W. Norton & Company', translators=['Strachey, J.'])
    s['work']['first_publication_date'] = '1930-01-01'
    s['contributions'].append({'role': 'editor', 'name': 'Strachey, J.'})
    assert bundle(s)['apa'] == 'Freud, S. (2010). Civilization and its discontents (J. Strachey, Ed. & Trans.). W. W. Norton & Company. (Original work published 1930)'
    for style in ['mla', 'chicago', 'harvard']:
        assert 'Strachey' in bundle(s)[style]
    s = item('chapter', 'On the essence of truth', 'Heidegger, M.', 2008, container_title='Basic writings', page_range='111–138', publisher='Harper Perennial Modern Thought')
    s['work']['first_publication_date'] = '1961-01-01'
    s['contributions'] += [{'role': 'editor', 'name': 'Krell, D. F.'}, {'role': 'translator', 'name': 'Sallis, J.'}]
    assert bundle(s)['apa'] == 'Heidegger, M. (2008). On the essence of truth (J. Sallis, Trans.). In D. F. Krell (Ed.), Basic writings (pp. 111–138). Harper Perennial Modern Thought. (Original work published 1961)'
    assert '(Heidegger, 1961/2008, p. 115)' in bundle(s, '115')['apa']


@pytest.mark.parametrize('kind', ['journal_article', 'chapter', 'thesis', 'report', 'journal_issue', 'other'])
def test_nonbook_unknown_author_retains_year_without_inventing_author(kind):
    s = item(kind, '测试资料', '', 2020)
    result = bundle(s)
    for style in ['apa', 'harvard']:
        assert '2020' in result[style]
        assert result[style].startswith('测试资料')
        assert '佚名' not in result[style]

import unittest
class SampleImage:
    shape = (1000, 1000, 3)
    def __getitem__(self, key):
        return self

from toc_layout import repair_contents


def block(text, bbox, confidence=.98):
    return dict(text=text, bbox=bbox, confidence=confidence, type='paragraph')


class ContentsLayoutTests(unittest.TestCase):
    def test_same_row_number_joins_title_not_the_next_paragraph(self):
        rows = [block('目录',[400,30,500,60]), block('23',[830,101,860,122]),
                block('第一章 什么是社会事实……',[100,100,650,125]),
                block('这一定义的说明',[100,150,850,175])]
        result=repair_contents(SampleImage(), rows, lambda image: self.fail('Existing number must be reused'))
        self.assertEqual([b['text'] for b in result],['目录','第一章 什么是社会事实……  23','这一定义的说明'])

    def test_redetection_accepts_digits_without_character_substitution(self):
        rows=[block('目',[400,30,420,60]),block('录',[480,30,500,60]),block('引言',[100,100,300,125])]
        image=SampleImage()
        ambiguous=repair_contents(image,rows,lambda region:[block('ZI',[100,10,140,30])])
        self.assertEqual(ambiguous,rows)
        result=repair_contents(image,rows,lambda region:[block('00000000000',[0,10,80,30]),block('21',[100,10,140,30])])
        self.assertEqual(result[-1]['text'],'引言  21')
        self.assertGreater(result[-1]['bbox'][2],800)

    def test_body_page_and_completed_entry_are_not_reprocessed(self):
        image=SampleImage()
        for rows in [[block('第一章 什么是社会事实',[100,100,700,150])],
                     [block('目录',[400,30,500,60]),block('第一章……23',[100,100,850,125])]]:
            self.assertEqual(repair_contents(image,rows,lambda region:self.fail('No extra OCR needed')),rows)

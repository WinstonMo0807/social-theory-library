"""Deferred parser checks. These observations always need human calibration."""
from catalog.services.outline_headings import styled_headings


def line(text, size, box=(20, 30, 200, 50), direction=(1, 0)):
    return {"spans": [{"text": text, "size": size}], "bbox": box, "dir": direction}


def test_unnumbered_native_heading_keeps_geometry_and_observed_style():
    blocks = [{"type": 0, "lines": [line("正文内容" * 80, 10), line("社会结构与行动", 16, direction=(0, -1))]}]
    rows = styled_headings(blocks)
    assert len(rows) == 1 and rows[0]["text"] == "社会结构与行动"
    assert rows[0]["body_font_size"] == 10 and rows[0]["font_size"] == 16
    assert rows[0]["direction"] == [0, -1] and rows[0]["bbox"] == [20, 30, 200, 50]
    assert "confidence" not in rows[0] and "calibration_status" not in rows[0]


def test_sparse_cover_body_text_and_nonfinite_coordinates_are_not_headings():
    assert styled_headings([{"lines": [line("封面题名", 30)]}]) == []
    assert styled_headings([{"lines": [line("普通正文" * 80, 10), line("123", 16),
                                        line("无效位置", 16, (0, 0, float("nan"), 10)), line("普通小标题", 11)]}]) == []

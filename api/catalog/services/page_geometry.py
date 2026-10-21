"""Explicit coordinates for newly extracted pages; unknown legacy units stay unknown."""
from copy import deepcopy
import math



def _numbers(value, length):
    return (isinstance(value, (list, tuple)) and len(value) == length
            and all(isinstance(item, (int, float)) and not isinstance(item, bool)
                    and math.isfinite(item) and abs(item) <= 1e8 for item in value))


def native_geometry(page):
    return {"schema": 1, "coordinate_space": "pymupdf_unrotated",
            "page_rect": list(page.rect), "crop_box": list(page.cropbox),
            "rotation": page.rotation, "rotation_matrix": list(page.rotation_matrix)}


def validated_geometry(value, *, source_page=None):
    """Validate finite geometry and optionally bind provider metadata to the PDF.

    Rendered OCR uses an axis-aligned positive DPI scale. Other transforms require
    an explicit future contract; rejecting them only disables precise overlays.
    """
    import fitz
    if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1:
        return {}
    space = value.get("coordinate_space")
    rotation = value.get("rotation")
    if space not in {"pymupdf_unrotated", "rendered_pixels"} or type(rotation) is not int or rotation not in {0, 90, 180, 270}:
        return {}
    rect, crop = value.get("page_rect"), value.get("crop_box")
    if not _numbers(rect, 4) or not _numbers(crop, 4):
        return {}
    if rect[2] <= rect[0] or rect[3] <= rect[1] or crop[2] <= crop[0] or crop[3] <= crop[1]:
        return {}
    width, height = crop[2] - crop[0], crop[3] - crop[1]
    expected_size = (height, width) if rotation in {90, 270} else (width, height)
    if any(abs(left - right) > .02 for left, right in zip((rect[2] - rect[0], rect[3] - rect[1]), expected_size)):
        return {}
    if source_page is not None and (source_page.rotation != rotation or any(
            abs(left - right) > .02 for left, right in zip([*rect, *crop], [*source_page.rect, *source_page.cropbox]))):
        return {}
    result = {"schema": 1, "coordinate_space": space, "page_rect": list(rect), "crop_box": list(crop), "rotation": rotation}
    if space == "pymupdf_unrotated":
        expected = {0: [1, 0, 0, 1, 0, 0], 90: [0, 1, -1, 0, height, 0],
                    180: [-1, 0, 0, -1, width, height], 270: [0, -1, 1, 0, 0, width]}[rotation]
        matrix = value.get("rotation_matrix")
        if not _numbers(matrix, 6) or any(abs(a - b) > .02 for a, b in zip(matrix, expected)):
            return {}
        result["rotation_matrix"] = list(matrix)
    else:
        dpi, matrix, origin = value.get("render_dpi"), value.get("render_matrix"), value.get("pixmap_origin")
        dimensions = [value.get("render_width"), value.get("render_height")]
        if (not _numbers([dpi], 1) or dpi <= 0 or not _numbers(dimensions, 2) or min(dimensions) <= 0
                or not _numbers(matrix, 6) or not _numbers(origin, 2)):
            return {}
        expected = [dpi / 72, 0, 0, dpi / 72, 0, 0]
        if any(abs(a - b) > 1e-5 for a, b in zip(matrix, expected)):
            return {}
        bounds = (fitz.Rect(rect) * fitz.Matrix(matrix)).irect
        if any(abs(a - b) > .01 for a, b in zip([*origin, *dimensions], [bounds.x0, bounds.y0, bounds.width, bounds.height])):
            return {}
        result.update(render_dpi=dpi, render_matrix=list(matrix), pixmap_origin=list(origin),
                      render_width=dimensions[0], render_height=dimensions[1])
    return deepcopy(result)


def normalized_bbox(bbox, geometry):
    """Return [x0,y0,x1,y1] fractions of the displayed cropped/rotated page."""
    import fitz
    geometry = validated_geometry(geometry)
    if not geometry or not _numbers(bbox, 4) or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return []
    corners = [fitz.Point(x, y) for x in (bbox[0], bbox[2]) for y in (bbox[1], bbox[3])]
    if geometry["coordinate_space"] == "pymupdf_unrotated":
        matrix = fitz.Matrix(geometry["rotation_matrix"])
        corners = [point * matrix for point in corners]
    else:
        origin = fitz.Point(geometry["pixmap_origin"])
        inverse = ~fitz.Matrix(geometry["render_matrix"])
        corners = [(point + origin) * inverse for point in corners]
    page = fitz.Rect(geometry["page_rect"])
    rectangle = fitz.Rect(min(p.x for p in corners), min(p.y for p in corners),
                          max(p.x for p in corners), max(p.y for p in corners)) & page
    if rectangle.is_empty:
        return []
    return [round((rectangle.x0 - page.x0) / page.width, 8), round((rectangle.y0 - page.y0) / page.height, 8),
            round((rectangle.x1 - page.x0) / page.width, 8), round((rectangle.y1 - page.y0) / page.height, 8)]


def ocr_geometry(raw_page, source_page):
    geometry = validated_geometry(raw_page.get("geometry"), source_page=source_page)
    if geometry and (geometry["coordinate_space"] != "rendered_pixels"
            or raw_page.get("width") != geometry["render_width"]
            or raw_page.get("height") != geometry["render_height"]):
        return {}
    return geometry


def locator_geometry(bbox, geometry):
    rectangle = normalized_bbox(bbox, geometry)
    return {"normalized_bbox": rectangle, "geometry_status": "validated" if rectangle else "unknown"}

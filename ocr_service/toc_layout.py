"""Join printed TOC rows using coordinates, with bounded same-model re-detection."""
import re

HEADING = re.compile(r"^(?:第[一二三四五六七八九十百零\d]+[版编部篇章节]|引\s*言|序\s*言|前\s*言|后\s*记|附\s*录|chapter\b|part\b)", re.I)
LABEL = re.compile(r"^[\s.．·•…_]*(\d{1,5}|[ivxlcdmIVXLCDM]{1,8})[\s.．·•…_]*$")
CONTENTS = re.compile(r"^(?:目\s*[录錄]|contents|table\s+of\s+contents)$", re.I)


def same_row(left, right):
    a, b = left['bbox'], right['bbox']
    return abs((a[1]+a[3]-b[1]-b[3])/2) <= max(a[3]-a[1], b[3]-b[1])*.65


def repair_contents(image, blocks, recognize_region):
    height, width = image.shape[:2]
    valid = [b for b in blocks if len(b.get('bbox', [])) == 4]
    header = [b for b in valid[:8] if b['bbox'][1] < height*.3]
    has_header = any(CONTENTS.fullmatch(b['text'].strip()) for b in header)
    # The observed scan splits 目/录; continuation pages may retain one character.
    has_split = any(b['text'].strip() in {'目', '录', '錄'} for b in header)
    if not (has_header or has_split):
        return blocks
    result, consumed, attempts = [], set(), 0
    for index, block in enumerate(blocks):
        if index in consumed:
            continue
        title = block['text'].strip()
        box = block.get('bbox', [])
        if len(box) != 4 or len(title) > 140 or not (HEADING.match(title) or re.search(r'[.．·…_]{2,}', title)):
            result.append(block); continue
        if re.search(r'(?:[.．·…_]{2,}|\s{2,})\s*\d{1,5}$', title):
            result.append(block); continue
        candidates = [(other_index, other) for other_index, other in enumerate(blocks)
            if other_index != index and other_index not in consumed and len(other.get('bbox', [])) == 4
            and other['bbox'][0] >= max(width*.6, box[2]-10) and same_row(block, other)
            and LABEL.fullmatch(other['text'])]
        page_block = max(candidates, key=lambda item: item[1]['bbox'][0], default=None)
        if page_block:
            consumed.add(page_block[0]); number = page_block[1]
        elif box[0] < width*.6 and box[2] < width*.9 and attempts < 24:
            # A page-number crop is re-detected, not sent directly to recognition:
            # the actual scan otherwise reads 1/21 as I/ZI. Never substitute glyphs.
            pad = max(8, round((box[3]-box[1])*.35))
            x, top, right, bottom = round(width*.70), max(0, round(box[1])-pad), round(width*.97), min(height, round(box[3])+pad)
            attempts += 1
            found = recognize_region(image[top:bottom, x:right])
            numbers = [b for b in found if len(b.get('bbox', [])) == 4 and
                re.fullmatch(r'\d{1,5}', b['text'].strip()) and b.get('confidence', 0) >= .85]
            if not numbers:
                result.append(block); continue
            number = max(numbers, key=lambda b: b['bbox'][0])
            number = {**number, 'bbox': [number['bbox'][0]+x, number['bbox'][1]+top, number['bbox'][2]+x, number['bbox'][3]+top]}
        else:
            result.append(block); continue
        match = LABEL.fullmatch(number['text'])
        label = match.group(1) if match else number['text'].strip()
        number_box = number['bbox']
        result.append({**block, 'text': f"{title}  {label}",
            'bbox': [min(box[0],number_box[0]), min(box[1],number_box[1]), max(box[2],number_box[2]), max(box[3],number_box[3])],
            'confidence': min(block['confidence'], number['confidence'])})
    consumed_ids = {id(blocks[index]) for index in consumed}
    return [block for block in result if id(block) not in consumed_ids]

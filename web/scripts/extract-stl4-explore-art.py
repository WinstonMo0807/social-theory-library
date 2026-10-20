"""Extract only decorative picture regions from the sole final visual atlas.

Run from the repository root with the development PyMuPDF environment.
No page, header, interface, sample book cover, or sample text is shipped as UI.
Coordinates are pixels in each page's embedded reference image, not PDF points.
"""
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[2]
ATLAS = ROOT / "output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf"
DESTINATION = ROOT / "web/public/editorial"
REGIONS = (
    (23, (605, 80, 1284, 453), "stl4-explore-hero.png"),
    (23, (1320, 78, 1650, 233), "stl4-explore-hero-mobile.png"),
    (23, (75, 533, 454, 684), "stl4-explore-books.png"),
    (23, (482, 533, 855, 684), "stl4-explore-shelves.png"),
    (23, (881, 533, 1239, 684), "stl4-explore-desk.png"),
    (23, (1340, 526, 1435, 631), "stl4-explore-books-mobile.png"),
    (23, (1340, 653, 1435, 762), "stl4-explore-shelves-mobile.png"),
    (23, (1340, 784, 1435, 891), "stl4-explore-desk-mobile.png"),
    (24, (669, 61, 1179, 300), "stl4-catalog-hero.png"),
)


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    with fitz.open(ATLAS) as atlas:
        for number, coordinates, filename in REGIONS:
            page = atlas[number - 1]
            images = page.get_images()
            if len(images) != 1:
                raise ValueError(f"Unexpected reference structure on atlas page {number}")
            xref, _, width, height, *_ = images[0]
            image_rect = page.get_image_rects(xref)[0]
            left, top, right, bottom = coordinates
            clip = fitz.Rect(
                image_rect.x0 + left / width * image_rect.width,
                image_rect.y0 + top / height * image_rect.height,
                image_rect.x0 + right / width * image_rect.width,
                image_rect.y0 + bottom / height * image_rect.height,
            )
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(width / image_rect.width, height / image_rect.height),
                clip=clip, alpha=False,
            )
            pixmap.save(DESTINATION / filename)
            print(f"page {number}: {filename} ({pixmap.width} x {pixmap.height})")


if __name__ == "__main__":
    main()

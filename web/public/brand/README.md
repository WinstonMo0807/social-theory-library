# Final PDF brand assets

Source: `output/pdf/social-theory-library-visual-atlas-20261015-final-r2.pdf`, the user's sole final visual reference. The user expressly confirmed ownership of every visual asset on 2026-10-26. These files contain isolated brand artwork, not a page rendered as a website.

Coordinates are in the embedded reference image, before PDF page scaling:

| Asset | PDF page | Native image rectangle (x0, y0, x1, y1) |
| --- | --- | --- |
| stl-mark-final-r2.png | 208 | 51, 11, 112, 56 |
| stl-wordmark-desktop-final-r2.png | 208 | 118, 12, 377, 57 |
| stl-wordmark-mobile-final-r2.png | 208 | 1321, 43, 1396, 98 |
| stl-wordmark-home-final-r2.png | 10 | 160, 10, 352, 48 |

The home illustrations in `../editorial/stl4-home-desktop-final-r2.png` and `stl4-home-mobile-final-r2.png` are taken from page 10, rectangles `541,56,1184,334` and `1222,71,1513,204` respectively. They contain illustration and its original motto, with no overlaid interactive controls. Titles, search, cards and forms remain live HTML using actual application data.

Extraction uses PyMuPDF page clips. Brand crops were rendered at 4× (home wordmark at 2×); illustrations at 2×. This is raster reproduction, not recovery of vector originals or font files. Do not describe upsampling as added source detail. No external substitute artwork was used.

## About and support pages (PDF 13–16)

The complete brand combinations differ by page. Their source rectangles are:

| Asset | Page | Native rectangle |
| --- | --- | --- |
| stl-lockup-about-desktop-final-r2.png | 14 | 64,15,259,75 |
| stl-lockup-about-mobile-final-r2.png | 14 | 1285,52,1438,98 |
| stl-lockup-support-desktop-final-r2.png | 13 | 57,14,279,56 |
| stl-lockup-support-mobile-final-r2.png | 13 | 1284,23,1406,68 |
| stl-lockup-article-desktop-final-r2.png | 15 | 78,20,269,64 |
| stl-lockup-article-mobile-final-r2.png | 15 | 1235,24,1405,65 |

Illustrations under `../editorial/`, all 2× PDF clips:

| Asset | Page | Native rectangle |
| --- | --- | --- |
| stl4-about-desktop-final-r2.png | 14 | 550,80,1238,293 |
| stl4-about-mobile-final-r2.png | 14 | 1281,219,1550,296 |
| stl4-support-desktop-final-r2.png | 13 | 548,68,1251,285 |
| stl4-support-mobile-final-r2.png | 13 | 1277,213,1561,287 |
| stl4-article-desktop-final-r2.png | 15 | 524,76,1192,283 |
| stl4-article-mobile-final-r2.png | 15 | 1219,196,1511,295 |
| stl4-feedback-desktop-final-r2.png | 16 | 500,64,1166,264 |
| stl4-support-search-final-r2.png | 13 | 72,520,417,702 |
| stl4-support-reading-final-r2.png | 13 | 450,520,805,702 |

The last two are instructional illustration fragments. The search form and chapter selection above them remain native interactive HTML; the book page is an illustration, not a published library record. The help citation example uses explicit author/year/title placeholders and identifies itself as an example in copied/exported output. No page is substituted with a full screenshot.

Citation illustration backplates: `stl4-support-citation-stage-final-r2.png` is PDF15 rectangle `161,631,903,841`; `stl4-support-citation-card-final-r2.png` is PDF13 rectangle `840,520,1184,702`. The original sample panel is covered by the corresponding live HTML citation format/page/copy/export panel. These remain instructional samples, never catalog records.

## Explore, catalog and opinion entry (PDF23,24,28)

| Asset | Page | Native rectangle |
| --- | --- | --- |
| stl-lockup-explore-desktop-final-r2.png | 23 | 80,12,344,71 |
| stl-lockup-explore-mobile-final-r2.png | 23 | 1340,18,1542,65 |
| stl-lockup-catalog-desktop-final-r2.png | 24 | 77,8,370,52 |
| stl-lockup-catalog-mobile-final-r2.png | 24 | 1233,43,1385,110 |
| stl-lockup-opinion-desktop-final-r2.png | 28 | 80,18,196,56 |
| stl-lockup-opinion-mobile-final-r2.png | 28 | 1274,60,1373,91 |
| ../editorial/stl4-catalog-hero-top-final-r2.png | 24 | 520,60,1180,243 |
| ../editorial/stl4-catalog-hero-bottom-final-r2.png | 24 | 670,243,1180,302 |

All are 2× clips of the PDF. The catalog illustration is split at the search-control boundary so neither search buttons nor text are burned into the artwork. The live search form and opinion link remain HTML. The main shell follows replacement PDF24; advanced fields, multiversion expansion and state behavior inherit PDF25–27. PDF28 supplies opinion layout; PDF29 explicitly supplies the 500-character counter and account history state. Its saved-history description follows the actual opted-in account behavior instead of falsely claiming that server-retained records exist only on the device.

Evidence brand (PDF30, 2× clips): `stl-lockup-evidence-desktop-final-r2.png` at `51,19,271,73`; mobile at `1346,66,1462,114`. Header search and account controls are live HTML. The unimplemented EN control is recorded as an outstanding requirement; no inert language toggle is added.


PDF33/34/35文献详情品牌（2026-10-26）：`stl-lockup-work-{desktop,mobile}-final-r2.png`分别取33页原图(52,31,173,73)/(1007,31,1121,73)；journal取34页(73,10,320,48)/(1281,56,1395,93)；work-readable取35页(65,9,247,40)/(1253,24,1399,50)。2倍页面clip，仅提取原像素，不重画。footer-work取35页(43,997,169,1022)，footer-journal取34页(73,963,393,991)。三种头部由当前页面article/readable状态决定；所有业务封面/学者肖像仍来自真实馆藏，不把PDF示例书灌入数据库。

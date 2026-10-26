// Editable vector artwork for the final PDF's brand lockups. No raster tracing,
// embedded image, font download or new runtime dependency is involved.
// PNGs remain untouched as reference evidence; their dimensions preserve layout.
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const directory = fileURLToPath(new URL("../public/brand/", import.meta.url));
const serif = "'Times New Roman', 'Noto Serif', serif";
const chinese = "'Songti SC', SimSun, 'Noto Serif CJK SC', serif";
const navy = "#10283e";
const gold = "#c99443";
const cn = "社会理论书库";
const en = "SOCIAL THEORY LIBRARY";
// Standard Times Bold advances (em); fit the font size, never stretch glyphs.
const advances = {" ":.25,A:.722,B:.667,C:.722,D:.722,E:.667,F:.611,G:.778,H:.778,I:.389,J:.5,K:.778,L:.667,M:.944,N:.722,O:.778,P:.611,Q:.778,R:.722,S:.556,T:.667,U:.722,V:.722,W:1,X:.722,Y:.722,Z:.667,a:.5,b:.556,c:.444,d:.556,e:.444,f:.333,g:.5,h:.556,i:.278,j:.333,k:.556,l:.278,m:.833,n:.556,o:.5,p:.556,q:.556,r:.444,s:.389,t:.333,u:.556,v:.5,w:.722,x:.5,y:.5,z:.444};
const groups = (entries) => Object.fromEntries(entries.flatMap(([layout, names]) => names.split(" ").map((name) => [name, layout])));

const desktop = groups([
  ["full-caps", "explore scholars topics theory-directory theory-overview subdisciplines"],
  ["english-stack", "reader opinion work graph"],
  ["english-stack-cn", "about graph-topic research-directory subdiscipline-detail"],
  ["english-two-cn", "article confirmed-notes"],
  ["english-two-long-cn", "evidence reading-paths"],
  ["english-line-cn", "catalog reader-center reading-plan research-counter research-workspace"],
  ["short-inline", "booklists citation-issue citation-report editorial-directory notebook reading-path research-replay work-readable"],
  ["short-stacked", "theory-tradition"],
  ["bilingual-cn-first", "journal parallel parallel-manual reader-archive reader-notes scholar-profile"],
  ["bilingual-en-first", "privacy privacy-export privacy-status theory-concept topic-directory"],
  ["parse", "citation-parse"],
  ["short", "graph-scholar"],
]);
// Mobile artwork is a separately specified PDF arrangement, not a scaled desktop.
const mobile = groups([
  ["full", "admin-article admin-assistant admin-concept admin-curation admin-home admin-index admin-path admin-selection admin-storage admin-timeline theory-timeline topic-profile"],
  ["full-caps", "explore scholars topics subdisciplines theory-directory theory-overview"],
  ["english-stack", "graph work"],
  ["english-stack-cn", "about catalog confirmed-notes evidence graph-topic reader-center reading-plan research-counter research-directory research-workspace subdiscipline-detail"],
  ["english-two-cn", "article"],
  ["english-two-long-cn", "reading-paths"],
  ["short", "admin-accounts admin-files admin-mapping admin-ocr admin-outline admin-publication admin-services admin auth-recovery editorial-exhibit editorial-exhibition graph-scholar journal opinion reader-outline"],
  ["short-stacked", "admin-editor admin-ledger admin-processing admin-upload auth citation-issue parallel parallel-manual support theory-tradition topic-directory"],
  ["short-inline", "admin-media admin-placement admin-recovery admin-scholar admin-topic booklists citation-report editorial-directory notebook privacy-export privacy-status reader reader-archive reader-notes reader-search reading-path research-compare research-replay scholar-directory scholar-profile sharing theory-concept work-readable"],
  ["bilingual-en-first", "privacy"],
  ["mobile-small-en", "admin-intake admin-manual editorial-article"],
  ["short-below", "admin-people"],
  ["parse-mobile", "citation-parse"],
]);
const footer = groups([
  ["full", "auth"],
  ["short-inline", "booklists notebook reader-notes research-compare research-replay theory-timeline work"],
  ["footer-short", "citation-issue"],
  ["footer-editorial", "editorial"],
  ["footer-en-cn", "graph reader-center reading-plan research-workspace"],
  ["footer-en-stl", "reader"],
  ["footer-bilingual", "journal reading-path"],
  ["footer-sharing", "sharing"],
  ["footer-parallel", "parallel"],
]);

// Two readers above the leaves of an open book. Curves and circles are authored
// in a single coordinate system so all appearances use the same crisp emblem.
function emblem(x, y, height, ink, accent) {
  return `<g transform="translate(${x} ${y}) scale(${height / 181})">
  <g fill="${ink}">
    <circle cx="82" cy="32" r="13"/>
    <path d="M43 53C72 47 103 61 122 81C90 90 62 111 43 136Z"/>
    <path d="M15 79H21V163C49 153 70 155 91 164C62 149 39 146 15 153Z"/>
    <path d="M27 66H33V150C52 142 70 145 88 153C61 136 43 135 27 141Z"/>
    <path d="M38 58H44V137C59 133 72 137 86 145C64 129 51 125 38 129Z"/>
  </g>
  <g fill="${accent}">
    <circle cx="168" cy="32" r="13"/>
    <path d="M112 81C138 59 166 49 203 55V145C168 117 141 92 112 81Z"/>
    <path d="M210 67H216V147C198 142 181 145 164 154C188 139 201 135 210 138Z"/>
    <path d="M222 79H228V157C202 149 182 153 160 164C189 148 208 145 222 150Z"/>
    <path d="M233 87H239V169C210 160 183 159 151 169C182 154 211 153 233 161Z"/>
  </g>
  <path fill="${ink}" d="M48 130C71 103 94 86 119 83C151 84 177 106 200 135L193 149C165 119 142 101 119 99C94 97 71 112 48 130Z"/>
  </g>`;
}

function artwork(layout, w, h, name) {
  const H = 100, W = w / h * H;
  const ink = /^(explore|scholars|topics|subdisciplines|subdiscipline-detail|theory-directory|theory-overview)$/.test(name) ? "#151719" : navy;
  const accent = ink === navy ? gold : "#d58a24";
  const out = [];
  const text = (value, x, baseline, size, width, options = {}) => {
    const family = options.cn ? chinese : serif;
    const em = [...value].reduce((sum, char) => sum + (options.cn ? 1 : advances[char] ?? .5), 0);
    const fitted = Math.min(size, width / em);
    const length = Math.min(width, fitted * (em + .15 * (value.length - 1)));
    out.push(`<text x="${x}" y="${baseline}" font-family="${family}" font-size="${fitted}" font-weight="${options.weight ?? 700}" fill="${ink}" textLength="${Math.max(1, length)}" lengthAdjust="spacing">${value}</text>`);
  };
  const icon = (height = 100, x = 0, y = (H - height) / 2) => out.push(emblem(x, y, height, ink, accent));
  const stl = (x, baseline = 77, width = 170, size = 84) => text("STL", x, baseline, size, width);
  const chineseLine = (x, baseline, width, size = 31) => text(cn, x, baseline, size, width, { cn: true });
  const rule = (x) => out.push(`<path d="M${x} 15V90" stroke="${ink}" stroke-opacity=".35" stroke-width="1"/>`);
  const englishStack = (x, width, upper, withChinese) => {
    const lines = upper ? ["SOCIAL", "THEORY", "LIBRARY"] : ["Social", "Theory", "Library"];
    const max = upper ? 7 : 6.5;
    const textWidth = width * (withChinese ? (upper ? .83 : .58) : 1);
    lines.forEach((line, i) => text(line, x, (withChinese ? 23 : 30) + i * (withChinese ? 22 : 28), withChinese ? 25 : 29, textWidth * line.length / max));
    if (withChinese) chineseLine(x, 94, width, 25);
  };
  if (layout === "mark") return emblem(0, 0, H, ink, accent);
  if (layout === "wordmark" || layout === "wordmark-mobile") {
    if (layout === "wordmark-mobile") englishStack(0, W, true, true);
    else { text(en, 0, 40, 34, W); chineseLine(0, 85, W * .59, 37); }
  } else if (layout.startsWith("footer-") && !["footer-editorial", "footer-bilingual"].includes(layout)) {
    if (layout === "footer-en-stl") { stl(0, 71, W * .12, 60); text(en, W * .19, 70, 56, W * .81); }
    if (layout === "footer-short") { stl(0, 76, W * .23, 70); chineseLine(W * .32, 74, W * .68, 60); }
    if (layout === "footer-en-cn") { text(en, 0, 72, 58, W * .65); chineseLine(W * .71, 72, W * .29, 55); }
    if (layout === "footer-sharing") { stl(0, 73, W * .07, 60); text("Social Theory Library", W * .12, 72, 58, W * .51, { weight: 400 }); chineseLine(W * .69, 72, W * .31, 55); }
    if (layout === "footer-parallel") { stl(0, 70, W * .055, 51); chineseLine(W * .07, 70, W * .22, 48); rule(W * .34); text("Bridging Ideas for a More Open World", W * .39, 69, 45, W * .61, { weight: 400 }); }
  } else {
    icon();
    const x = 142, available = W - x;
    if (layout === "full" || layout === "full-caps") {
      const stlWidth = available * .43;
      stl(x, 78, stlWidth);
      const right = x + stlWidth + 16;
      if (name === "auth") rule(right - 7);
      englishStack(right, W - right, layout === "full-caps", true);
    } else if (layout === "short") stl(x, 80, available, 87);
    else if (layout === "short-stacked") { stl(x, 62, Math.min(available, 176), 74); chineseLine(x, 94, available, 28); }
    else if (layout === "short-below") {
      out.length = 0; icon(76, 0, 0); stl(116, 63, W - 116, 71); chineseLine(22, 98, W - 44, 27);
    } else if (layout === "short-inline") {
      const sw = available * .38; stl(x, 80, sw); chineseLine(x + sw + 24, 70, W - x - sw - 24, 42);
    } else if (layout === "mobile-small-en") {
      const sw = available * .45; stl(x, 80, sw); text("Social", x + sw + 20, 34, 24, W - x - sw - 20); chineseLine(x + sw + 20, 79, W - x - sw - 20, 31);
    } else if (layout === "english-stack" || layout === "english-stack-cn") englishStack(x, available, true, layout.endsWith("-cn"));
    else if (layout === "english-line-cn") { text(en, x, 42, 34, available); chineseLine(x, 85, available * .45, 36); }
    else if (layout === "english-two-cn" || layout === "english-two-long-cn") {
      const longFirst = layout === "english-two-long-cn";
      text(longFirst ? "SOCIAL THEORY" : "SOCIAL", x, 30, 29, available * (longFirst ? 1 : .46));
      text(longFirst ? "LIBRARY" : "THEORY LIBRARY", x, 62, 29, available * (longFirst ? .55 : 1));
      chineseLine(x, 94, available * .78, 27);
    } else if (layout === "parse" || layout === "parse-mobile") {
      const ew = available * .52;
      if (layout === "parse-mobile") englishStack(x, ew, true, false);
      else { text("SOCIAL", x, 43, 31, ew * .46); text("THEORY LIBRARY", x, 78, 31, ew); }
      rule(x + ew + 18); chineseLine(x + ew + 34, 66, W - x - ew - 34, 36);
    } else if (layout === "bilingual-cn-first" || layout === "bilingual-en-first" || layout === "footer-bilingual") {
      const sw = available * .28; stl(x, 81, sw);
      const right = x + sw + 24, rw = W - right;
      if (layout === "bilingual-cn-first" || layout === "footer-bilingual") {
        chineseLine(right, 48, rw * .68, 38); text(en, right, 83, 23, rw);
      } else { text(["theory-concept", "topic-directory"].includes(name) ? "Social Theory Library" : en, right, 40, 26, rw); chineseLine(right, 85, rw * .92, 38); }
    } else if (layout === "footer-editorial") {
      const sw = available * .16; stl(x, 78, sw); text("Social Theory Library", x + sw + 20, 68, 40, available * .44); chineseLine(x + available * .65, 69, available * .35, 39);
    } else throw new Error(`Unknown brand arrangement: ${layout}`);
  }
  return out.join("\n");
}

let count = 0;
for (const file of readdirSync(directory).filter((name) => /^stl-(lockup|footer|wordmark|mark)-.*-final-r2\.png$/.test(name) || name === "stl-mark-final-r2.png")) {
  const source = readFileSync(path.join(directory, file));
  const w = source.readUInt32BE(16), h = source.readUInt32BE(20);
  let name = "", layout;
  if (file.startsWith("stl-lockup-")) {
    const match = file.match(/^stl-lockup-(.+)-(desktop|mobile)-final-r2\.png$/);
    if (!match) throw new Error(file);
    name = match[1];
    layout = (match[2] === "mobile" ? mobile[name] : desktop[name]) ?? (match[2] === "desktop" ? "full" : undefined);
  } else if (file.startsWith("stl-footer-")) { name = file.slice(11, -13); layout = footer[name]; }
  else layout = file.startsWith("stl-mark-") ? "mark" : file.includes("mobile") ? "wordmark-mobile" : "wordmark";
  if (!layout) throw new Error(`Missing PDF arrangement for ${file} (${name})`);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w / h * 100} 100" width="${w}" height="${h}" role="img" aria-label="社会理论书库"><title>社会理论书库 · Social Theory Library</title>\n${artwork(layout, w, h, name)}\n</svg>\n`;
  writeFileSync(path.join(directory, file.replace(/\.png$/, ".svg")), svg);
  count++;
}
console.log(`Drew ${count} vector brand assets; original PDF crops retained.`);

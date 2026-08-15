import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  formatUploadBytes,
  formatUploadEta,
  formatUploadRate,
  UploadRateMeter,
} from "../lib/upload-metrics.ts";

test("upload meter separates current network rate from effective average rate", () => {
  const meter = new UploadRateMeter(10_000, 2_000, 1_000);
  const first = meter.sample(4_000, 2_000, 2_000);
  const retry = meter.sample(4_000, 1_000, 3_000);

  assert.equal(first.logicalBytes, 4_000);
  assert.equal(first.currentSpeedBps, 2_000);
  assert.equal(first.averageSpeedBps, 2_000);
  assert.equal(first.etaSeconds, 3);
  assert.equal(retry.logicalBytes, 4_000);
  assert.ok(retry.currentSpeedBps > retry.averageSpeedBps);
  assert.equal(retry.averageSpeedBps, 1_000);
  assert.equal(retry.etaSeconds, 6);
});

test("upload display formats capacity, rate and remaining time", () => {
  assert.equal(formatUploadBytes(8 * 1024 * 1024), "8.0 MB");
  assert.equal(formatUploadRate(2 * 1024 * 1024), "2.0 MB/s");
  assert.equal(formatUploadEta(61), "约 2 分钟");
  assert.equal(formatUploadEta(0), "即将完成");
});

test("public upload keeps legacy sessions while using larger chunks for new files", async () => {
  const source = await readFile(
    new URL("../components/admin-upload.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /const LEGACY_CHUNK_SIZE = MEBIBYTE/);
  assert.match(source, /const CHUNK_SIZE = 2 \* MEBIBYTE/);
  assert.match(source, /resume\.chunkSize \|\| LEGACY_CHUNK_SIZE/);
  assert.match(source, /服务器正在合并和校验/);
  assert.match(source, /当前 \$\{formatUploadRate\(item\.speedBps\)\}/);
  assert.match(source, /平均 \$\{formatUploadRate\(item\.averageSpeedBps\)\}/);
});

test("accepted uploads continue into live identification and publication actions", async () => {
  const source = await readFile(
    new URL("../components/admin-upload.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /\/ingestion\/items\/\$\{itemId\}\//);
  assert.match(source, /setTimeout\(refresh, 2500\)/);
  assert.match(source, /识别书目信息/);
  assert.match(source, /disciplines: "学科"/);
  assert.match(source, /theory_schools: "理论流派"/);
  assert.match(source, /subdisciplines: "子学科"/);
  assert.match(source, /\/admin\/review\/\$\{item\.id\}/);
  assert.match(source, /\/admin\/publication\?item=\$\{item\.id\}/);
});

test("new upload batches submit explicit intake policies without rewriting resumed sessions", async () => {
  const source = await readFile(
    new URL("../components/admin-upload.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /useState<AccessPolicy>\("public"\)/);
  assert.match(source, /useState<OcrStrategy>\("auto"\)/);
  assert.match(source, /useState<DuplicatePolicy>\("review"\)/);
  assert.match(source, /useState\(true\).*externalEnrichmentEnabled|\[externalEnrichmentEnabled, setExternalEnrichmentEnabled\] = useState\(true\)/s);
  assert.match(source, /useState\(false\).*aiSuggestionsEnabled|\[aiSuggestionsEnabled, setAiSuggestionsEnabled\] = useState\(false\)/s);
  assert.match(source, /label: batchLabel\.trim\(\)/);
  assert.match(source, /access_policy: accessPolicy/);
  assert.match(source, /ocr_strategy: ocrStrategy/);
  assert.match(source, /duplicate_policy: duplicatePolicy/);
  assert.match(source, /external_enrichment_enabled: externalEnrichmentEnabled/);
  assert.match(source, /ai_suggestions_enabled: aiSuggestionsEnabled/);
  assert.match(source, /自动检测（推荐）/);
  assert.match(source, /仅在模型服务已配置时产生候选。候选不会自动采用/);
  assert.match(source, /恢复文件继续使用原批次策略/);
  assert.match(source, /targetBatchId = useChunks && item\.resumeBatchId/);
});

test("one-stop upload pairs same-name structured metadata without blocking the PDF", async () => {
  const source = await readFile(
    new URL("../components/admin-upload.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /METADATA_FILE_EXTENSIONS = new Set\(\["ris", "bib", "bibtex", "json", "yaml", "yml"\]\)/);
  assert.match(source, /filename\.normalize\("NFKC"\)/);
  assert.match(source, /\(metadata\|sidecar\|csl\|zotero\)/);
  assert.match(source, /同名 PDF 或元数据文件不唯一，请改为一一对应的文件名/);
  assert.match(source, /\/ingestion\/items\/\$\{itemId\}\/metadata-import\//);
  assert.match(source, /PDF 已上传；配套元数据未导入/);
  assert.match(source, /配套文件只生成待审候选，不会直接覆盖馆藏/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  isTerminalResearchStatus,
  prefixedResearchChangedFields,
  researchRunSuggestions,
} from "../components/admin/research/research-suggestion-state.ts";

test("ResearchRun results flatten without losing discovery provenance", () => {
  const rows = researchRunSuggestions({
    status: "completed",
    local_results: {
      workflow: { suggestions: [{ id: "workflow", field_name: "title", source_tier: "in_library" }] },
      entities: [{ query: "Pierre Bourdieu", results: [{ id: "local", field: "contributors.contributors", candidate_group: "local", label: "Pierre Bourdieu" }] }],
    },
    external_results: {
      enrichment: [{ id: "enrichment", field: "abstract", source_tier: "structured_source" }],
      entities: [{ results: [{ id: "authority", field: "contributors.contributors", candidate_group: "authority", label: "Pierre Bourdieu" }] }],
      editorial_evidence: [{ suggestions: [{ id: "lead", field_name: "relations", source_tier: "research_lead" }] }],
    },
  });
  assert.deepEqual(rows.map((row) => row.id), ["workflow", "local", "enrichment", "authority", "lead"]);
  assert.equal(rows.find((row) => row.id === "local")?.field_name, "contributors");
  assert.equal(rows.find((row) => row.id === "local")?.source_name, "Pierre Bourdieu");
  assert.equal(rows.find((row) => row.id === "authority")?.source_tier, "structured_source");
  assert.equal(isTerminalResearchStatus("degraded"), true);
  assert.equal(isTerminalResearchStatus("running"), false);
});

test("field changes are qualified once and remain dependency-scoped", () => {
  assert.deepEqual(
    prefixedResearchChangedFields("work", ["title", "abstract", "work.title"]),
    ["work.title", "work.abstract"],
  );
  assert.deepEqual(
    prefixedResearchChangedFields("contributors", ["items", "work.title"]),
    ["contributors.items", "work.title"],
  );
});

test("research panel auto-runs, debounces draft changes, polls, and forces manual reruns", async () => {
  const panel = await readFile(new URL("../components/admin/research/research-suggestion-panel.tsx", import.meta.url), "utf8");
  assert.match(panel, /\/catalog\/admin\/intake\/\$\{encodeURIComponent\(itemId \?\? ""\)\}\/research\//);
  assert.match(panel, /trigger = changedFields\.length \? "field_change" as const : "auto_load" as const/);
  assert.match(panel, /trigger === "field_change" \? 800 : 0/);
  assert.match(panel, /include_background: false/);
  assert.match(panel, /draft: draftData/);
  assert.match(panel, /changed_fields: fields/);
  assert.match(panel, /edition_id: editionId/);
  assert.match(panel, /\?edition_id=\$\{encodeURIComponent\(editionId\)\}/);
  assert.match(panel, /runDetailEndpoint/);
  assert.match(panel, /trigger: "manual", fields: \[\], force: true/);
  assert.match(panel, /强制重跑本节/);
  assert.match(panel, /lastAutomaticRequest\.current = ""/);
  assert.match(panel, /hasAutomaticResearch\.current = false/);
  assert.match(panel, /setPayload\(null\)/);
  assert.match(panel, /attempt < maxAttempts/);
  assert.match(panel, /SLOW_POLL_INTERVAL_MS/);
  assert.match(panel, /MAX_CONSECUTIVE_POLL_FAILURES/);
  assert.match(panel, /requestInFlightRevision\.current !== null/);
  assert.match(panel, /未创建重复任务/);
  assert.match(panel, /nonTerminalRun \|\| !credential/);
  assert.match(panel, /仍在研究队列中等待/);
  assert.match(panel, /<ActionButton/);
  assert.match(panel, /<AsyncStatus/);
});

test("universal picker separates groups and requires explicit external decisions", async () => {
  const picker = await readFile(new URL("../components/admin/research/research-entity-picker.tsx", import.meta.url), "utf8");
  assert.match(picker, /\["local", "local_draft", "authority", "external_web", "unresolved"\]/);
  for (const entityType of ["person", "work", "theory", "topic", "knowledge_node", "discipline", "subdiscipline", "organization", "publisher", "journal"]) {
    assert.match(picker, new RegExp(`"${entityType}"`));
  }
  assert.match(picker, /\/catalog\/admin\/research\/entity-discovery\//);
  assert.match(picker, /\/catalog\/admin\/research\/entity-decisions\//);
  for (const action of ["link_existing", "create_draft", "keep_unresolved", "reject"]) {
    assert.match(picker, new RegExp(action));
  }
  assert.match(picker, /if \(!workspace\?\.itemId\)/);
  assert.match(picker, /权威数据维护页/);
  assert.match(picker, /aria-activedescendant/);
  assert.match(picker, /event\.key === "ArrowUp"/);
  assert.match(picker, /event\.key === "ArrowDown"/);
  assert.match(picker, /event\.key === "Enter"/);
  assert.match(picker, /event\.key === "Escape"/);
  assert.match(picker, /event\.key === "Tab"/);
  assert.match(picker, /aria-live="polite"/);
  assert.match(picker, /if \(requestRevision\.current === revision\) requestRevision\.current \+= 1/);
  assert.doesNotMatch(picker, /if \(!workspace\)[\s\S]*?<EntityPicker/);
  assert.match(picker, /getServerSessionCredential/);
  assert.match(picker, /workspace\?\.token \?\? getServerSessionCredential\(\)/);
  assert.match(picker, /workspace \? workspace\.canRun : true/);
  assert.match(picker, /Object\.entries\(asRecord\(candidate\.external_ids\)\)/);
  assert.match(picker, /candidate\.source_record_id/);
  assert.match(picker, /candidate\.source_url \?\? metadata\.url/);
  assert.match(picker, /candidate\.provider \?\? candidate\.source/);
  assert.match(picker, /const succeeded = await workspace\.onCandidateDecision/);
  assert.match(picker, /if \(!succeeded\)[\s\S]*候选仍保留/);
});

test("entity discovery keeps exact edition context and degrades without dropping local candidates", async () => {
  const picker = await readFile(new URL("../components/admin/research/research-entity-picker.tsx", import.meta.url), "utf8");
  const context = await readFile(new URL("../components/admin/research/research-workspace-context.tsx", import.meta.url), "utf8");
  assert.match(context, /editionId\?: string/);
  assert.match(picker, /edition_id: workspace\?\.editionId/);
  assert.match(picker, /edition_id: workspace\.editionId/);
  assert.match(picker, /mergeCandidates\(remoteCandidates, seedCandidates\)/);
  assert.match(picker, /setDiscoveryState\("failed"\)/);
  assert.match(picker, /馆内候选仍保留在列表中/);
  assert.match(picker, /workflow-universal-entity-degraded/);
});

test("text candidates use canonical labels and unsupported persistent decisions stay hidden", async () => {
  const picker = await readFile(new URL("../components/admin/research/research-entity-picker.tsx", import.meta.url), "utf8");
  assert.match(picker, /use_value: "使用规范文本"/);
  assert.match(picker, /onUseValue\(name, candidate\)/);
  assert.match(picker, /DIRECT_ENTITY_DECISION_ACTIONS\.has\(action\)/);
  assert.match(picker, /DIRECT_ENTITY_DECISION_TYPES\.has\(candidateEntityType\)/);
  assert.match(picker, /workspace\?\.itemId[\s\S]*DIRECT_ENTITY_DECISION_ACTIONS/);
  assert.doesNotMatch(picker, /maintenanceBlocked/);
  assert.match(picker, /field === "translation_of"/);
  assert.match(picker, /当前作品不能作为自己的原作/);
});

test("entity picker popover is wide on desktop and contained on narrow screens", async () => {
  const css = await readFile(new URL("../app/editorial-workspaces.css", import.meta.url), "utf8");
  assert.match(css, /width: clamp\(420px, 48vw, 560px\)/);
  assert.match(css, /\.workflow-universal-entity-popover\s*\{[\s\S]*?right: auto;[\s\S]*?left: 0;/);
  assert.match(css, /\.workflow-knowledge-relation > \.workflow-research-entity-picker \.workflow-universal-entity-popover\s*\{[\s\S]*?right: 0;[\s\S]*?left: auto;/);
  assert.match(css, /@media \(max-width: 720px\)[\s\S]*\.workflow-universal-entity-popover[\s\S]*width: 100%/);
  assert.match(css, /max-width: 100%/);
  assert.match(css, /\.workflow-section\.presentation-current\s*\{[\s\S]*?overflow: visible;/);
});

test("workflow editor provides unsaved drafts and decision handling to research UI", async () => {
  const editor = await readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8");
  assert.match(editor, /ResearchWorkspaceContext\.Provider value=\{researchWorkspace\}/);
  assert.match(editor, /draftData: drafts/);
  assert.match(editor, /changedFields: dirty/);
  assert.match(editor, /onCandidateDecision: decideCandidate/);
  assert.match(editor, /operationRef\.current/);
  assert.match(editor, /<ActionButton/);
  assert.match(editor, /<AsyncStatus/);
  assert.match(editor, /entityType="person" step="contributors" field="contributors"/);
  assert.match(editor, /entityType="discipline" step="classification" field="primary_disciplines"/);
  assert.match(editor, /entityType=\{targetType\} step="knowledge" field="relations"/);
  assert.match(editor, /editionId: asString|editionId,/);
  assert.match(editor, /entityType="work" step="work" field="translation_of"/);
  assert.match(editor, /endpoint="\/catalog\/admin\/library\/works\/" queryParam="q" nameField="title" entityType="work"/);
  assert.match(editor, /renderEntityText\("publisher", "出版者", "publisher"\)/);
  assert.match(editor, /renderEntityText\("journal_title", "期刊名", "journal"/);
  assert.match(editor, /renderEntityText\("degree_institution", "学位授予单位", "organization"/);
  assert.match(editor, /renderEntityText\("report_institution", "报告责任机构", "organization"/);
  assert.match(editor, /publisher_authority_id/);
  assert.match(editor, /候选决定尚未提交/);
  assert.match(editor, /return true;[\s\S]*catch \(reason\)[\s\S]*return false;/);
});

test("curation uses universal reading-path discovery before the existing stage placement mutation", async () => {
  const curation = await readFile(new URL("../components/admin/curation/work-curation-editor.tsx", import.meta.url), "utf8");
  assert.match(curation, /<ResearchEntityPicker label="搜索现有阅读路径"/);
  assert.match(curation, /entityType="reading_path" step="curation" field="reading_path_placements"/);
  assert.match(curation, /theory-system\/reading-paths\/\$\{encodeURIComponent\(selectedPath\)\}/);
  assert.match(curation, /selectedPathOption\?\.stages\?\.map/);
  assert.match(curation, /reading_path_id: selectedPath/);
  assert.match(curation, /stage_id: selectedStage/);
});

test("reading-path workbench uses the shared picker for formal Discipline, Work and KnowledgeNode inputs", async () => {
  const workbench = await readFile(new URL("../components/admin/curation/reading-path-workbench.tsx", import.meta.url), "utf8");
  const fields = await readFile(new URL("../components/admin/forms/workflow-fields.tsx", import.meta.url), "utf8");
  assert.match(workbench, /<ResearchEntityPicker label="馆藏作品"/);
  assert.match(workbench, /entityType="work"[\s\S]*queryParam="q"[\s\S]*nameField="title"/);
  assert.match(workbench, /<ResearchEntityPicker label="知识节点"/);
  assert.match(workbench, /entityType="knowledge_node"[\s\S]*queryParam="q"[\s\S]*nameField="canonical_name_zh"/);
  assert.match(workbench, /node_name: asString\(nodeData\.canonical_name_zh/);
  assert.match(workbench, /work_name: asString\(workData\.title/);
  assert.match(workbench, /<ResearchEntityPicker label="主要学科" endpoint="\/catalog\/admin\/disciplines\/" queryParam="q"[\s\S]*step="classification" field="primary_disciplines"/);
  assert.doesNotMatch(workbench, /<span>主要学科<\/span><select/);
  assert.doesNotMatch(workbench, /catalogQuery/);
  assert.match(fields, /queryParam = "search"/);
  assert.match(fields, /!queryParam && query\.trim\(\)/);
  assert.match(fields, /encodeURIComponent\(queryParam\)/);
});

test("active knowledge maintenance routes use universal discovery for every entity input", async () => {
  const knowledgeAdmin = await readFile(new URL("../components/knowledge-admin.tsx", import.meta.url), "utf8");
  const theoryAdmin = await readFile(new URL("../components/theory-system-admin.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../app/editorial-workspaces.css", import.meta.url), "utf8");

  assert.match(knowledgeAdmin, /label="所属学科"[\s\S]*?step="maintenance_subdisciplines" field="discipline"/);
  assert.match(knowledgeAdmin, /label="上级子学科"[\s\S]*?step="maintenance_subdisciplines" field="parent"/);
  assert.doesNotMatch(knowledgeAdmin, /<span>所属学科<\/span><select/);
  assert.doesNotMatch(knowledgeAdmin, /<span>上级子学科<\/span><select/);

  for (const field of ["filter_discipline", "parent", "primary_discipline", "related_disciplines", "merge_target"]) {
    assert.match(theoryAdmin, new RegExp(`step="maintenance_theory_nodes" field="${field}"`));
  }
  for (const field of ["review_candidate", "new_node_discipline", "source_node", "target_node"]) {
    assert.match(theoryAdmin, new RegExp(`step="maintenance_theory_relations" field="${field}"`));
  }
  for (const field of ["filter_discipline", "nodes", "disciplines", "scholar", "work"]) {
    assert.match(theoryAdmin, new RegExp(`step="maintenance_theory_timeline" field="${field}"`));
  }

  assert.match(theoryAdmin, /label="关联学者"[\s\S]*?entityType="person"[\s\S]*?field="scholar"/);
  assert.match(theoryAdmin, /field="related_disciplines" multiple values=/);
  assert.match(theoryAdmin, /field="nodes" multiple values=/);
  assert.match(theoryAdmin, /field="disciplines" multiple values=/);
  assert.doesNotMatch(theoryAdmin, /draft\.nodes\.includes\(/);
  assert.doesNotMatch(theoryAdmin, /draft\.disciplines\.includes\(/);
  assert.doesNotMatch(theoryAdmin, /<span>源理论<\/span><select/);
  assert.doesNotMatch(theoryAdmin, /<span>目标理论<\/span><select/);
  assert.doesNotMatch(theoryAdmin, /<span>关联学者<\/span><select/);
  assert.doesNotMatch(theoryAdmin, /<span>关联馆藏<\/span><select/);

  assert.match(theoryAdmin, /candidate_node: candidateNode \|\| null/);
  assert.match(theoryAdmin, /primary_discipline: newNodeDiscipline \|\| null/);
  assert.match(theoryAdmin, /source_node: picked\?\.id \?\? ""/);
  assert.match(theoryAdmin, /scholar: draft\.scholar \|\| null/);
  assert.match(theoryAdmin, /work: draft\.work \|\| null/);
  assert.match(css, /theory-node-editor:has\(\.workflow-research-entity-picker input\[aria-expanded="true"\]\)/);
  assert.match(css, /normalized-timeline-list:has\(\.workflow-research-entity-picker input\[aria-expanded="true"\]\)/);
  assert.match(css, /theory-review-editor \.workflow-universal-entity-popover[\s\S]*?right: 0;[\s\S]*?left: auto;/);
});

test("maintenance editor pins the exact Edition across load, save and publication", async () => {
  const page = await readFile(new URL("../app/admin/library/works/[workId]/page.tsx", import.meta.url), "utf8");
  const library = await readFile(new URL("../components/admin/library/work-library.tsx", import.meta.url), "utf8");
  const editor = await readFile(new URL("../components/admin/workflow/workflow-editor.tsx", import.meta.url), "utf8");
  assert.match(page, /query\.edition/);
  assert.match(page, /editionId=\{editionId\}/);
  assert.match(library, /primary_edition_id/);
  assert.match(library, /\?edition=\$\{encodeURIComponent\(work\.primary_edition_id\)\}/);
  assert.match(editor, /requestedEditionId \|\| asString\(payload\?\.context\.edition_id\)/);
  assert.match(editor, /const scopedEndpoint = mode === "maintenance"/);
  assert.match(editor, /sections\/\$\{step\}\/\$\{maintenanceQuery\}/);
  assert.match(editor, /sections\/curation\/\$\{maintenanceQuery\}/);
  assert.equal(editor.match(/publication\/\$\{maintenanceQuery\}/g)?.length, 2);
  assert.match(editor, /edition_id: maintenanceEditionId/);
});

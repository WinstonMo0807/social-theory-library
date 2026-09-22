/** Generated from DRF/OpenAPI. Do not edit by hand. */
export interface paths {
    "/api/catalog/admin/bibliographic-candidates/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_bibliographic_candidates_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/catalog-field-contracts/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_catalog_field_contracts_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/cataloging-sessions/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["cataloging_sessions_list"];
        put?: never;
        post: operations["catalog_admin_cataloging_sessions_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/cataloging-sessions/{session_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["cataloging_sessions_detail"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/cataloging-sessions/{session_id}/abandon/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_cataloging_sessions_abandon_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/cataloging-sessions/{session_id}/candidates/{candidate_id}/decision/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_cataloging_sessions_candidates_decision_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/cataloging-sessions/{session_id}/metadata/{candidate_id}/decision/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_cataloging_sessions_metadata_decision_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/cataloging-sessions/{session_id}/metadata/import/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_cataloging_sessions_metadata_import_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/curation-drafts/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_curation_drafts_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/discovery-index/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_discovery_index_retrieve"];
        put?: never;
        post: operations["catalog_admin_discovery_index_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/media/cover/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_editions_media_cover_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/media/recommendation/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_editions_media_recommendation_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/publication/history/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_editions_publication_history_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/publication/prepare/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_editions_publication_prepare_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/publication/rollback/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_editions_publication_rollback_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/evidence-curation/{object_type}/{object_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_evidence_curation_retrieve"];
        put: operations["catalog_admin_evidence_curation_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/evidence-curation/{object_type}/{object_id}/publish/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_evidence_curation_publish_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/evidence-curation/sources/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_evidence_curation_sources_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/knowledge-media/{object_type}/{object_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_knowledge_media_retrieve"];
        put?: never;
        post: operations["catalog_admin_knowledge_media_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/media/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_media_list"];
        put?: never;
        post: operations["catalog_admin_media_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/media/{media_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_media_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch: operations["catalog_admin_media_partial_update"];
        trace?: never;
    };
    "/api/catalog/admin/media/{media_id}/renditions/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_media_renditions_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/media/collection/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_media_collection_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/people/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_people_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/people/{person_id}/duplicates/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_people_duplicates_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/people/{person_id}/merge/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_people_merge_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/people/{person_id}/merge-preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_people_merge_preview_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/people/merge-records/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_people_merge_records_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/people/merge-records/{record_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_people_merge_records_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/people/merge-records/{record_id}/rollback/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_people_merge_records_rollback_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/recommendation-issues/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_recommendation_issues_list"];
        put?: never;
        post: operations["catalog_admin_recommendation_issues_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/recommendation-issues/{issue_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_recommendation_issues_retrieve"];
        put: operations["catalog_admin_recommendation_issues_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/recommendation-issues/{issue_id}/items/{item_id}/link/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_recommendation_issues_items_link_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/recommendation-issues/{issue_id}/publish/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_recommendation_issues_publish_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/scholar-relations/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_scholar_relations_list"];
        put?: never;
        post: operations["catalog_admin_scholar_relations_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/scholar-relations/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_scholar_relations_retrieve"];
        put: operations["catalog_admin_scholar_relations_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/scholar-relations/{id}/archive/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_scholar_relations_archive_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/scholar-relations/{id}/publish/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_scholar_relations_publish_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/scholars/{scholar_id}/portrait/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_scholars_portrait_retrieve"];
        put?: never;
        post: operations["catalog_admin_scholars_portrait_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/site-content/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_site_content_retrieve"];
        put: operations["catalog_admin_site_content_update"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/site-content/publish/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_site_content_publish_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/works/{work_id}/recommendation-image/metadata/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_works_recommendation_image_metadata_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/assets/{asset_id}/manifest/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_assets_manifest_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/assets/{asset_id}/pages/{page_index}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_assets_pages_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/discovery-search/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_discovery_search_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/discovery-search/{session_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_discovery_search_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/discovery-search/{session_id}/cancel/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_discovery_search_cancel_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/discovery-search/{session_id}/context/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_discovery_search_context_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/discovery-search/{session_id}/expand/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_discovery_search_expand_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/evidence-curation/{object_type}/{object_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_evidence_curation_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/recommendation-issues/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_recommendation_issues_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/recommendation-issues/{slug}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_recommendation_issues_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/recommendation-issues/{slug}/save-list/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_recommendation_issues_save_list_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/scholar-relations/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_scholar_relations_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/works/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_works_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/works/{slug}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_works_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/works/{work_id}/cover-metadata/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_works_cover_metadata_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/works/{work_id}/recommendation-image-metadata/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_works_recommendation_image_metadata_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/distribution/assets/{asset_id}/access/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["distribution_assets_access_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        AboutPageBlock: {
            /** Format: uuid */
            readonly id: string;
            key: string;
            block_type: components["schemas"]["BlockTypeEnum"];
            title?: string;
            body?: string;
            icon?: string;
            action_label?: string;
            action_href?: string;
            /** Format: int64 */
            sort_order?: number;
            visible?: boolean;
            configuration?: unknown;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
        };
        AboutPageBlockRequest: {
            key: string;
            block_type: components["schemas"]["BlockTypeEnum"];
            title?: string;
            body?: string;
            icon?: string;
            action_label?: string;
            action_href?: string;
            /** Format: int64 */
            sort_order?: number;
            visible?: boolean;
            configuration?: unknown;
        };
        /**
         * @description * `inherit` - 继承版本权限
         *     * `private` - 仅后台可用
         *     * `registered` - 登录读者
         *     * `restricted` - 受限访问
         *     * `public` - 公开访问
         * @enum {string}
         */
        AccessStatusEnum: "inherit" | "private" | "registered" | "restricted" | "public";
        AdminIssueSummary: {
            total: number;
            published: number;
            drafts: number;
            scheduled: number;
        };
        AdminRecommendationIssueCollection: {
            count: number;
            next: string | null;
            previous: string | null;
            current: components["schemas"]["RecommendationIssue"] | null;
            results: components["schemas"]["RecommendationIssue"][];
            summary: components["schemas"]["AdminIssueSummary"];
            upcoming: components["schemas"]["RecommendationIssue"][];
        };
        ApiError: {
            code: string;
            message: string;
            field: string | null;
            severity: components["schemas"]["SeverityEnum"];
            details: unknown;
        };
        AssetCompact: {
            /** Format: uuid */
            readonly id: string;
            kind: components["schemas"]["AssetCompactKindEnum"];
            original_filename?: string;
            mime_type?: string;
            /** Format: int64 */
            page_count?: number;
            /** Format: int64 */
            byte_size?: number;
            sha256: string;
            /** Format: double */
            text_layer_quality?: number | null;
            language_guess?: string;
            access_status?: components["schemas"]["AccessStatusEnum"];
            rights_note?: string;
        };
        /**
         * @description * `original` - 原始文件
         *     * `normalized` - 规范阅读文件
         *     * `ocr_pdf` - OCR 阅读文件
         *     * `web_derivative` - 网页阅读派生文件
         * @enum {string}
         */
        AssetCompactKindEnum: "original" | "normalized" | "ocr_pdf" | "web_derivative";
        BibliographicLookupRequest: {
            /** Format: uuid */
            edition_id: string;
            /** @default  */
            query: string;
            /** @default false */
            allow_external: boolean;
            form_context?: {
                [key: string]: unknown;
            };
        };
        /**
         * @description * `intro` - 简介
         *     * `stat` - 数据
         *     * `feature` - 功能
         *     * `process` - 入库步骤
         *     * `principle` - 开放原则
         *     * `notice` - 提示
         *     * `action` - 操作入口
         *     * `footer` - 页脚信息
         * @enum {string}
         */
        BlockTypeEnum: "intro" | "stat" | "feature" | "process" | "principle" | "notice" | "action" | "footer";
        /**
         * @description * `link_existing` - link_existing
         *     * `create_draft` - create_draft
         *     * `keep_unresolved` - keep_unresolved
         *     * `reject` - reject
         * @enum {string}
         */
        CatalogingCandidateDecisionActionEnum: "link_existing" | "create_draft" | "keep_unresolved" | "reject";
        CatalogingCandidateDecisionRequest: {
            action: components["schemas"]["CatalogingCandidateDecisionActionEnum"];
            target_type: string;
            /** Format: uuid */
            target_id?: string | null;
            /** @default false */
            confirm_identity: boolean;
            /** @default  */
            reason: string;
        };
        CatalogingMetadataImportRequest: {
            source_label: string;
            source_url?: string;
            fields: {
                [key: string]: unknown;
            };
        };
        CatalogingSession: {
            /** Format: uuid */
            readonly id: string;
            readonly source_type: components["schemas"]["CatalogingSourceTypeEnum"];
            readonly status: components["schemas"]["StatusEnum"];
            /** Format: uuid */
            readonly edition_id: string | null;
            /** Format: uuid */
            readonly work_id: string | null;
            /** Format: uuid */
            readonly upload_item_id: string | null;
            /** Format: uuid */
            readonly base_public_revision_id: string | null;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
            readonly workbench_url: string;
        };
        CatalogingSessionCreateRequest: {
            source_type: components["schemas"]["CatalogingSourceTypeEnum"];
            /** Format: uuid */
            edition_id?: string;
            /** Format: uuid */
            upload_item_id?: string;
            title?: string;
            document_type?: components["schemas"]["DocumentTypeEnum"];
            language?: string;
            /** Format: uuid */
            request_key?: string;
        };
        CatalogingSessionDetail: {
            session: components["schemas"]["CatalogingSession"];
            workspace: unknown;
        };
        CatalogingSessionList: {
            results: components["schemas"]["CatalogingSession"][];
        };
        /**
         * @description * `upload` - 上传文献
         *     * `manual` - 手工编目
         *     * `import` - 导入书目
         *     * `existing` - 编辑馆藏
         * @enum {string}
         */
        CatalogingSourceTypeEnum: "upload" | "manual" | "import" | "existing";
        /**
         * @description * `unchanged` - unchanged
         *     * `added` - added
         *     * `removed` - removed
         *     * `changed` - changed
         * @enum {string}
         */
        ChangeEnum: "unchanged" | "added" | "removed" | "changed";
        CoverMediaSelectionRequest: {
            /** Format: uuid */
            media_id: string;
        };
        CoverMediaSelectionResult: {
            saved: boolean;
            /** Format: uuid */
            media_id: string | null;
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            editorial_revision_id: string | null;
            workbench_url: string;
            canonical_write_deferred: boolean;
        };
        CurationDraft: {
            id: string;
            /** Format: uuid */
            object_id: string;
            object_type: string;
            title: string;
            label: string;
            /** Format: date-time */
            updated_at: string;
            edit_url: string;
            state: components["schemas"]["StateEnum"];
            can_edit: boolean;
        };
        CurationDraftPage: {
            count: number;
            page: number;
            page_size: number;
            total_pages: number;
            next: string | null;
            previous: string | null;
            results: components["schemas"]["CurationDraft"][];
        };
        CurationItem: {
            /** Format: uuid */
            id?: string;
            source_type: components["schemas"]["CurationItemSourceTypeEnum"];
            /** Format: uuid */
            source_id: string;
            group_title?: string;
            reason?: string;
            order?: number;
            readonly source: components["schemas"]["CurationSource"];
        };
        CurationItemRequest: {
            /** Format: uuid */
            id?: string;
            source_type: components["schemas"]["CurationItemSourceTypeEnum"];
            /** Format: uuid */
            source_id: string;
            group_title?: string;
            reason?: string;
            order?: number;
        };
        /**
         * @description * `span` - span
         *     * `passage` - passage
         * @enum {string}
         */
        CurationItemSourceTypeEnum: "span" | "passage";
        CurationSource: {
            /** Format: uuid */
            id: string;
            source_type: string;
            text: string;
            context_before: string;
            context_after: string;
            /** Format: uuid */
            work_id: string;
            work_title: string;
            /** Format: uuid */
            edition_id: string;
            edition_label: string;
            /** Format: uuid */
            asset_id: string;
            page_start: number;
            page_end: number;
            printed_label: string;
            /** Format: uuid */
            document_revision_id: string | null;
            reader_url: string;
            public_eligible: boolean;
        };
        CurationSourceRequest: {
            /** Format: uuid */
            id: string;
            source_type: string;
            text: string;
            context_before: string;
            context_after: string;
            /** Format: uuid */
            work_id: string;
            work_title: string;
            /** Format: uuid */
            edition_id: string;
            edition_label: string;
            /** Format: uuid */
            asset_id: string;
            page_start: number;
            page_end: number;
            printed_label: string;
            /** Format: uuid */
            document_revision_id: string | null;
            reader_url: string;
            public_eligible: boolean;
        };
        CurationSourcesPage: {
            count: number;
            next: string | null;
            previous: string | null;
            results: components["schemas"]["CurationSource"][];
        };
        /**
         * @description * `directed` - directed
         *     * `bidirectional` - bidirectional
         *     * `undirected` - undirected
         * @enum {string}
         */
        DirectionEnum: "directed" | "bidirectional" | "undirected";
        DiscoveryContext: {
            /** Format: uuid */
            result_id: string;
            /** Format: uuid */
            document_revision_id: string;
            /** Format: uuid */
            asset_id: string;
            excerpt: string;
            blocks: {
                [key: string]: unknown;
            }[];
            before: string;
            after: string;
            reader_url: string;
            locator_precision: string;
            source_kind: string;
            notice: string;
        };
        DiscoveryCreateRequest: {
            q: string;
            filters?: {
                [key: string]: unknown;
            };
        };
        DiscoveryCuration: {
            /** Format: uuid */
            id: string;
            title: string;
            source_title: string;
            source_kind: string;
            recommendation_excerpt: string;
            url: string;
            linked_work_ids?: string[];
            match_basis: string[];
        };
        DiscoveryEntity: {
            /** Format: uuid */
            id: string;
            kind: string;
            title: string;
            url: string;
            excerpt: string;
            portrait_url?: string;
            match_basis: string[];
        };
        DiscoveryPassage: {
            /** Format: uuid */
            id: string;
            excerpt: string;
            work: components["schemas"]["DiscoveryWork"];
            authors: string[];
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            edition_id?: string;
            /** Format: uuid */
            document_revision_id: string;
            pdf_page: number;
            printed_page?: string;
            source_kind: string;
            source_revision: string;
            reader_url: string;
            locator_precision: string;
            context_reference: string;
            match_basis: string[];
        };
        DiscoveryResponse: {
            /** Format: uuid */
            id: string;
            query: string;
            /** @description queued, running, partial, completed, failed or canceled */
            status: string;
            access_token?: string;
            passages: components["schemas"]["DiscoveryPassage"][];
            entities: components["schemas"]["DiscoveryEntity"][];
            curation: components["schemas"]["DiscoveryCuration"][];
            next_cursor: string | null;
            can_expand: boolean;
            warnings: components["schemas"]["DiscoveryWarning"][];
            coverage_summary: {
                [key: string]: unknown;
            };
            completed_channels: string[];
            channels: {
                [key: string]: unknown;
            };
            counts: {
                [key: string]: unknown;
            };
            source_changed: boolean;
            expansion_count: number;
            generation: number;
            mode: string;
            original_query: string;
            filters: {
                [key: string]: unknown;
            };
            count: number;
            corpus_version: string;
            knowledge_version: string;
            pipeline_version: string;
            poll_after_ms: number | null;
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            expires_at: string;
            notice: string;
            status_url?: string;
        };
        DiscoveryWarning: {
            code: string;
            message: string;
            channel?: string;
        };
        DiscoveryWork: {
            /** Format: uuid */
            id: string;
            title: string;
            slug?: string;
        };
        /**
         * @description * `book` - 图书
         *     * `journal_article` - 期刊论文
         *     * `journal_issue` - 整期期刊
         *     * `thesis` - 学位论文
         *     * `report` - 研究报告
         * @enum {string}
         */
        DocumentTypeEnum: "book" | "journal_article" | "journal_issue" | "thesis" | "report";
        EditionCompact: {
            /** Format: uuid */
            readonly id: string;
            public_slug?: (string) | null;
            version_label?: string;
            readonly edition_statement: string;
            /** Format: date */
            publication_date?: string | null;
            /** Format: int64 */
            publication_year?: number | null;
            publisher?: string;
            readonly publisher_verbatim: string;
            /** Format: uuid */
            publisher_authority?: string | null;
            publication_place?: string;
            readonly publication_place_verbatim: string;
            distribution_place?: string;
            distributor?: string;
            manufacture_place?: string;
            manufacturer?: string;
            journal_title?: string;
            readonly journal_contents: components["schemas"]["PublicJournalContent"][];
            volume?: string;
            issue?: string;
            page_range?: string;
            isbn?: string;
            isbn10?: string;
            isbn13?: string;
            doi?: string;
            series?: string;
            extent?: string;
            responsibility_statement?: string;
            readonly contributors: components["schemas"]["PublicContributionSnapshot"][];
            readonly readable_asset: components["schemas"]["AssetCompact"] | null;
        };
        EditorialPublishRequest: {
            edit_version: string;
        };
        EvidenceCuration: {
            /** Format: uuid */
            readonly id: string | null;
            readonly configured: boolean;
            readonly object_type: string;
            /** Format: uuid */
            readonly object_id: string;
            readonly title: string;
            edit_version?: string;
            readonly has_unpublished_changes: boolean;
            items: components["schemas"]["CurationItem"][];
        };
        EvidenceCurationRequest: {
            edit_version?: string;
            items: components["schemas"]["CurationItemRequest"][];
        };
        /**
         * @description * `rebuild` - rebuild
         *     * `retry` - retry
         * @enum {string}
         */
        IndexActionActionEnum: "rebuild" | "retry";
        IndexActionRequest: {
            action: components["schemas"]["IndexActionActionEnum"];
            /** Format: uuid */
            job_id?: string;
        };
        IndexActionResult: {
            /** Format: uuid */
            job_id: string;
            status: string;
            message: string;
        };
        IndexStatus: {
            active_generation: unknown;
            model: unknown;
            summary: unknown;
            capabilities: unknown;
            count: number;
            page: number;
            page_size: number;
            results: unknown[];
            jobs: unknown[];
            warnings: unknown[];
        };
        IssueBodyBlock: {
            type: components["schemas"]["TypeEnum"];
            text: string;
            source?: string;
            url?: string;
        };
        IssueBodyBlockRequest: {
            type: components["schemas"]["TypeEnum"];
            text: string;
            source?: string;
            url?: string;
        };
        IssueItem: {
            /** Format: uuid */
            id?: string;
            kind: components["schemas"]["IssueItemKindEnum"];
            /** Format: uuid */
            work_id?: string | null;
            /** Format: uuid */
            edition_id?: string | null;
            title?: string;
            authors?: string;
            version_note?: string;
            isbn?: string;
            doi?: string;
            note?: string;
            position?: number;
            document_type?: string;
            readonly status: string;
            readonly work_url: string;
            readonly reader_url: string;
            readonly cover_url: string;
            readonly file_status: string;
            /** Format: uuid */
            readonly cataloging_session_id: string | null;
            /** Format: uuid */
            readonly available_work_id: string | null;
            /** Format: uuid */
            readonly available_edition_id: string | null;
            readonly workbench_url: string;
            readonly match_candidates: {
                [key: string]: unknown;
            }[];
        };
        /**
         * @description * `catalog` - catalog
         *     * `planned` - planned
         * @enum {string}
         */
        IssueItemKindEnum: "catalog" | "planned";
        IssueItemRequest: {
            /** Format: uuid */
            id?: string;
            kind: components["schemas"]["IssueItemKindEnum"];
            /** Format: uuid */
            work_id?: string | null;
            /** Format: uuid */
            edition_id?: string | null;
            title?: string;
            authors?: string;
            version_note?: string;
            isbn?: string;
            doi?: string;
            note?: string;
            position?: number;
            document_type?: string;
        };
        KnowledgeImageRequestRequest: {
            /** Format: uuid */
            media_id: string | null;
            fingerprint: string;
        };
        KnowledgeImageState: {
            object_type: components["schemas"]["ObjectTypeEnum"];
            /** Format: uuid */
            object_id: string;
            name: string;
            media: components["schemas"]["PublicCoverMedia"] | null;
            preview_url: string;
            /** Format: uuid */
            editorial_revision_id: string | null;
            canonical_write_deferred: boolean;
            editor_url: string;
            fingerprint: string;
        };
        MediaAsset: {
            /** Format: uuid */
            readonly id: string;
            media_type: string;
            source_type?: components["schemas"]["MediaSourceTypeEnum"];
            source_url?: string;
            source_label?: string;
            rights?: string;
            license?: string;
            credit?: string;
            alt_text?: string;
            /** Format: int64 */
            width: number;
            /** Format: int64 */
            height: number;
            checksum: string;
            /** Format: int64 */
            byte_size: number;
            /** Format: double */
            focal_x?: number;
            /** Format: double */
            focal_y?: number;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
            readonly renditions: components["schemas"]["MediaRendition"][];
        };
        MediaCollection: {
            count: number;
            page: number;
            page_size: number;
            pages: number;
            results: components["schemas"]["MediaAsset"][];
        };
        MediaDetail: {
            /** Format: uuid */
            readonly id: string;
            media_type: string;
            source_type?: components["schemas"]["MediaSourceTypeEnum"];
            source_url?: string;
            source_label?: string;
            rights?: string;
            license?: string;
            credit?: string;
            alt_text?: string;
            /** Format: int64 */
            width: number;
            /** Format: int64 */
            height: number;
            checksum: string;
            /** Format: int64 */
            byte_size: number;
            /** Format: double */
            focal_x?: number;
            /** Format: double */
            focal_y?: number;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
            readonly renditions: components["schemas"]["MediaRendition"][];
            readonly references: unknown;
        };
        MediaRendition: {
            /** Format: uuid */
            readonly id: string;
            kind: string;
            /** Format: int64 */
            requested_width: number;
            /** Format: int64 */
            width: number;
            /** Format: int64 */
            height: number;
            checksum: string;
            /** Format: int64 */
            byte_size: number;
            readonly url: string;
        };
        /**
         * @description * `cover` - cover
         *     * `portrait` - portrait
         *     * `hero` - hero
         *     * `card` - card
         *     * `thumbnail` - thumbnail
         * @enum {string}
         */
        MediaRenditionRequestKindEnum: "cover" | "portrait" | "hero" | "card" | "thumbnail";
        MediaRenditionRequestRequest: {
            /** @default 640 */
            width: components["schemas"]["WidthEnum"];
            /** @default cover */
            kind: components["schemas"]["MediaRenditionRequestKindEnum"];
        };
        /**
         * @description * `upload` - 人工上传
         *     * `pdf` - 文献页面
         *     * `external` - 外部资料
         *     * `generated` - 生成图片
         * @enum {string}
         */
        MediaSourceTypeEnum: "upload" | "pdf" | "external" | "generated";
        MediaUploadRequest: {
            /** Format: date-time */
            expected_updated_at?: string;
            source_type?: components["schemas"]["MediaSourceTypeEnum"];
            source_url?: string;
            source_label?: string;
            rights?: string;
            license?: string;
            credit?: string;
            alt_text?: string;
            /** Format: double */
            focal_x?: number;
            /** Format: double */
            focal_y?: number;
            /** Format: binary */
            image: string;
        };
        /**
         * @description * `reject` - reject
         *     * `reopen` - reopen
         * @enum {string}
         */
        MetadataDecisionActionEnum: "reject" | "reopen";
        MetadataDecisionRequest: {
            action: components["schemas"]["MetadataDecisionActionEnum"];
        };
        /**
         * @description * `knowledge_node` - knowledge_node
         *     * `reading_path` - reading_path
         *     * `discipline` - discipline
         *     * `subdiscipline` - subdiscipline
         * @enum {string}
         */
        ObjectTypeEnum: "knowledge_node" | "reading_path" | "discipline" | "subdiscipline";
        PaginatedWorkCardList: {
            /** @example 123 */
            count: number;
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=4
             */
            next?: string | null;
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?page=2
             */
            previous?: string | null;
            results: components["schemas"]["WorkCard"][];
        };
        PatchedMediaMetadataRequest: {
            /** Format: date-time */
            expected_updated_at?: string;
            source_type?: components["schemas"]["MediaSourceTypeEnum"];
            source_url?: string;
            source_label?: string;
            rights?: string;
            license?: string;
            credit?: string;
            alt_text?: string;
            /** Format: double */
            focal_x?: number;
            /** Format: double */
            focal_y?: number;
        };
        PersonDuplicateCandidate: {
            person: components["schemas"]["PersonResolutionSummary"];
            matches: unknown[];
            identity_conflicts: unknown[];
        };
        PersonDuplicateResponse: {
            source: components["schemas"]["PersonResolutionSummary"];
            results: components["schemas"]["PersonDuplicateCandidate"][];
            limit: number;
            has_more: boolean;
            automatic_merge: boolean;
            matching_policy: string;
        };
        PersonLexiconEntry: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            entity_id: string;
            term: string;
            normalized_term: string;
            language: string;
            term_type: string;
            source_kind: string;
            trust_level: string;
            source_ref: string;
            displayable: boolean;
            public_active: boolean;
            admin_resolvable: boolean;
        };
        PersonLexiconPreview: {
            scope: string;
            available: boolean;
            status: string;
            /** Format: uuid */
            generation_id: string | null;
            revision: number | null;
            normalization_version: string;
            source_registry_version: string;
            source: number;
            target: number;
            source_rows: components["schemas"]["PersonLexiconEntry"][];
            target_rows: components["schemas"]["PersonLexiconEntry"][];
            truncated: boolean;
            error: string;
        };
        PersonMergeHistoryItem: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            source_person_id: string;
            /** Format: uuid */
            target_person_id: string;
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            rolled_back_at: string | null;
        };
        PersonMergePreviewResponse: {
            business_impact?: unknown;
            version: string;
            fingerprint: string;
            source: unknown;
            target: unknown;
            source_profile: unknown;
            target_profile: unknown;
            references: unknown[];
            affected_works: unknown[];
            affected_editions: unknown[];
            affected_edition_count: number;
            publication_revisions: unknown[];
            publication_revision_count: number;
            editorial_drafts: unknown[];
            identity_conflicts: unknown[];
            review_issues: unknown[];
            lexicon_entries: components["schemas"]["PersonLexiconPreview"];
            complete_reference_listing: boolean;
            merge_execution_available: boolean;
            coverage: unknown;
            preservation: string[];
            execution_policy?: string;
            execution_guidance?: string[];
            context_impact?: unknown;
        };
        PersonMergeRecord: {
            business_impact?: unknown;
            source_name?: string;
            target_name?: string;
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            source_person_id: string;
            /** Format: uuid */
            target_person_id: string;
            status: string;
            /** Format: date-time */
            created_at: string;
            created_by_id: number | null;
            /** Format: date-time */
            rolled_back_at: string | null;
            moved_counts: unknown;
            affected_edition_ids: string[];
            event_ids: string[];
            rollback_event_ids: string[];
            rollback: unknown;
        };
        PersonMergeRequestRequest: {
            /** Format: uuid */
            target_person: string;
            fingerprint: string;
            idempotency_key: string;
            confirmed: boolean;
            change_note?: string;
        };
        PersonMergeRollbackRequestRequest: {
            fingerprint: string;
            confirmed: boolean;
        };
        PersonResolutionSummary: {
            /** Format: uuid */
            id: string;
            preferred_name: string;
            original_name: string;
            birth_year: number | null;
            death_year: number | null;
            authority_status: string;
        };
        PersonSearchResponse: {
            results: components["schemas"]["PersonResolutionSummary"][];
            has_more: boolean;
        };
        PlannedItemLinkRequest: {
            edit_version: string;
            /** Format: uuid */
            work_id: string;
            /** Format: uuid */
            edition_id: string;
            confirm_version: boolean;
        };
        PublicClassificationLink: {
            /** Format: uuid */
            id: string | null;
            name: string;
            slug: string;
            is_primary: boolean;
        };
        PublicContributionSnapshot: {
            role: string;
            order: number;
            person: components["schemas"]["PublicPersonSnapshot"];
        };
        PublicCoverMedia: {
            /** Format: uuid */
            media_id: string;
            /** Format: uuid */
            primary_rendition_id: string;
            alt_text: string;
            source_label: string;
            source_url: string;
            rights: string;
            license: string;
            credit: string;
            renditions: components["schemas"]["PublicMediaRendition"][];
        };
        PublicEntityLink: {
            /** Format: uuid */
            id: string | null;
            name: string;
            slug: string;
        };
        PublicJournalContent: {
            /** Format: uuid */
            id?: string | null;
            /** Format: uuid */
            article_work_id?: string | null;
            title: string;
            author_display: string;
            page_range: string;
            position: number;
            article_href: string;
        };
        PublicMediaRendition: {
            /** Format: uuid */
            id: string;
            width: number;
            height: number;
            url: string;
        };
        PublicOutlineItem: {
            index: number;
            file_page_index?: number;
            printed_label: string;
            chapter_title: string;
        };
        PublicPersonSnapshot: {
            /** Format: uuid */
            id: string | null;
            preferred_name: string;
            original_name?: string;
            aliases?: string[];
            authority_status?: string;
            birth_year?: number | null;
            death_year?: number | null;
            biography?: string;
            portrait?: string;
            /** @description Historical snapshot media is retained as JSON. */
            portrait_media?: unknown;
            scholar_slug?: string | null;
        };
        PublicTheoryAssociation: {
            /** Format: uuid */
            id: string;
            node: components["schemas"]["PublicTheoryAssociationNode"];
            role: string;
            role_label: string;
            strength: string;
            evidence: components["schemas"]["PublicTheoryAssociationEvidence"][];
        };
        PublicTheoryAssociationEvidence: {
            /** Format: uuid */
            id: string;
            page_number: number;
            page_end: number | null;
            printed_page_label: string;
            quote: string;
            reader_href: string;
        };
        PublicTheoryAssociationNode: {
            /** Format: uuid */
            id: string;
            name: string;
            slug: string;
            foreign_name: string;
            type: string;
        };
        PublicationFieldDiff: {
            field: string;
            label: string;
            change: components["schemas"]["ChangeEnum"];
            before: unknown;
            after: unknown;
            before_display: string;
            after_display: string;
        };
        PublicationHistoryItem: {
            /** Format: uuid */
            id: string;
            revision: number;
            title: string;
            status: string;
            /** Format: date-time */
            activated_at: string | null;
            is_current: boolean;
            can_rollback: boolean;
        };
        PublicationPreparation: {
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            active_revision_id: string | null;
            fingerprint: string;
            changes: components["schemas"]["PublicationFieldDiff"][];
            blocking: string[];
            warnings: string[];
            background_processing: string[];
            can_publish: boolean;
        };
        PublicationRollbackRequest: {
            /** Format: uuid */
            revision_id: string;
            /** Format: uuid */
            request_key: string;
            reason: string;
        };
        PublicationRollbackResult: {
            /** Format: uuid */
            event_id: string;
            /** Format: uuid */
            source_revision_id: string;
            status: string;
        };
        ReaderAssetAccess: {
            url: string;
            download_url: string;
            original_download_url: string;
            download_rendition: string;
            source: string;
            expires_in: number | null;
            supports_range: boolean;
            download_filename: string;
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            requested_asset_id: string;
            /** Format: uuid */
            served_asset_id: string;
            /** Format: uuid */
            source_artifact_id: string | null;
            rendition: string;
            reader_rendition_policy: string;
            reader_fallback_reason: string;
            sha256: string;
            page_count: number;
            ocr_status: string;
            ocr_text_available: boolean;
            page_label_status: string;
            semantic_index_status: string;
        };
        ReaderManifest: {
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            edition_id: string;
            page_count: number;
            publication_status: string;
            ocr_status: string;
            semantic_index_status: string;
            page_label_status: string;
            reader_rendition_policy: string;
            outline: components["schemas"]["PublicOutlineItem"][];
            related_scholars: components["schemas"]["ReaderRelatedScholar"][];
            related_theories: components["schemas"]["ReaderRelatedLink"][];
            related_topics: components["schemas"]["ReaderRelatedLink"][];
            work: components["schemas"]["WorkCard"];
        };
        ReaderPageContent: {
            /** Format: uuid */
            page_id: string;
            page_index: number;
            file_page_index: number;
            printed_label: string;
            citation_page_label: string;
            label_source: string;
            /** Format: double */
            label_confidence: number;
            chapter_title: string;
            text_available: boolean;
            text_source: components["schemas"]["TextSourceEnum"];
            /** Format: double */
            width: number;
            /** Format: double */
            height: number;
            text: string;
            blocks: components["schemas"]["ReaderTextBlock"][];
        };
        ReaderRelatedLink: {
            name: string;
            slug: string;
        };
        ReaderRelatedScholar: {
            name: string;
            slug: string | null;
            years: string;
        };
        ReaderTextBlock: {
            /** Format: uuid */
            id: string;
            order: number;
            type: string;
            text: string;
            /** @description Existing geometric JSON, not restricted to an invented coordinate shape. */
            bbox: unknown;
            /** Format: double */
            confidence: number;
        };
        RecommendationImagePreview: {
            /** Format: uuid */
            work_id: string;
            document_type: string;
            available: boolean;
            source: string;
            preview_url: string;
            public_url: string;
            /** Format: date-time */
            updated_at: string;
            canonical_write_deferred: boolean;
            /** Format: uuid */
            editorial_revision_id: string | null;
            workbench_url: string;
            media_library_url: string;
            detail: string;
        };
        RecommendationIssue: {
            /** Format: uuid */
            readonly id: string;
            slug?: string;
            title: string;
            issue_label?: string;
            introduction?: string;
            public_byline?: string;
            body_blocks?: components["schemas"]["IssueBodyBlock"][];
            cover_url?: string;
            /** Format: uuid */
            cover_rendition_id?: string | null;
            /** Format: date-time */
            display_from?: string | null;
            /** Format: date-time */
            readonly published_at: string | null;
            items?: components["schemas"]["IssueItem"][];
            edit_version?: string;
            /** Format: uuid */
            readonly draft_revision_id: string | null;
            readonly has_unpublished_changes: boolean;
        };
        RecommendationIssueCollection: {
            count: number;
            next: string | null;
            previous: string | null;
            current: components["schemas"]["RecommendationIssue"] | null;
            results: components["schemas"]["RecommendationIssue"][];
        };
        RecommendationIssueRequest: {
            slug?: string;
            title: string;
            issue_label?: string;
            introduction?: string;
            public_byline?: string;
            body_blocks?: components["schemas"]["IssueBodyBlockRequest"][];
            cover_url?: string;
            /** Format: uuid */
            cover_rendition_id?: string | null;
            /** Format: date-time */
            display_from?: string | null;
            items?: components["schemas"]["IssueItemRequest"][];
            edit_version?: string;
        };
        /**
         * @description * `teaching` - teaching
         *     * `cooperation` - cooperation
         *     * `influence` - influence
         *     * `criticism` - criticism
         *     * `comparative_reading` - comparative_reading
         *     * `other` - other
         * @enum {string}
         */
        RelationTypeEnum: "teaching" | "cooperation" | "influence" | "criticism" | "comparative_reading" | "other";
        SavedIssueList: {
            /** Format: uuid */
            id: string;
            title: string;
            item_count: number;
            planned_count: number;
        };
        ScholarPortraitRequestRequest: {
            /** Format: uuid */
            media_id: string | null;
            /** Format: uuid */
            expected_person_id: string;
            fingerprint: string;
        };
        ScholarPortraitState: {
            /** Format: uuid */
            scholar_id: string;
            /** Format: uuid */
            person_id: string;
            name: string;
            media: components["schemas"]["PublicCoverMedia"] | null;
            preview_url: string;
            /** Format: uuid */
            editorial_revision_id: string | null;
            canonical_write_deferred: boolean;
            editor_url: string;
            fingerprint: string;
        };
        ScholarRelation: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            source_scholar: string;
            /** Format: uuid */
            target_scholar: string;
            readonly source_name: string;
            readonly target_name: string;
            readonly source_slug: string;
            readonly target_slug: string;
            relation_type: components["schemas"]["RelationTypeEnum"];
            direction: components["schemas"]["DirectionEnum"];
            summary: string;
            source: string;
            readonly status: string;
            edit_version?: string;
            readonly has_unpublished_changes: boolean;
        };
        ScholarRelationPage: {
            count: number;
            next: string | null;
            previous: string | null;
            results: components["schemas"]["ScholarRelation"][];
        };
        ScholarRelationRequest: {
            /** Format: uuid */
            source_scholar: string;
            /** Format: uuid */
            target_scholar: string;
            relation_type: components["schemas"]["RelationTypeEnum"];
            direction: components["schemas"]["DirectionEnum"];
            summary: string;
            source: string;
            edit_version?: string;
        };
        /**
         * @description * `blocking` - blocking
         *     * `warning` - warning
         *     * `info` - info
         * @enum {string}
         */
        SeverityEnum: "blocking" | "warning" | "info";
        SiteConfig: {
            /** @default  */
            home_hero_image: string;
            /** @default  */
            home_hero_alt: string;
            /** Format: uuid */
            home_hero_rendition_id?: string | null;
            site_name: string;
            wordmark_lines: string[];
            home_title_left_lines: string[];
            home_title_right_lines: string[];
            intro_lines: string[];
            about_label: string;
            about_title: string;
            about_body: string;
            about_why_title: string;
            about_why_body: string;
            about_feature_search_title: string;
            about_feature_search_body: string;
            about_feature_read_title: string;
            about_feature_read_body: string;
            about_feature_knowledge_title: string;
            about_feature_knowledge_body: string;
            about_ingestion_title: string;
            about_ingestion_body: string;
            about_access_title: string;
            about_access_body: string;
            about_rights_title: string;
            about_rights_body: string;
            about_privacy_title: string;
            about_privacy_body: string;
            about_warning_title: string;
            about_warning_body: string;
            copyright_text: string;
            navigation: {
                [key: string]: string;
            };
            sections: {
                [key: string]: string;
            };
        };
        SiteConfigRequest: {
            /** @default  */
            home_hero_image: string;
            /** @default  */
            home_hero_alt: string;
            /** Format: uuid */
            home_hero_rendition_id?: string | null;
            site_name: string;
            wordmark_lines: string[];
            home_title_left_lines: string[];
            home_title_right_lines: string[];
            intro_lines: string[];
            about_label: string;
            about_title: string;
            about_body: string;
            about_why_title: string;
            about_why_body: string;
            about_feature_search_title: string;
            about_feature_search_body: string;
            about_feature_read_title: string;
            about_feature_read_body: string;
            about_feature_knowledge_title: string;
            about_feature_knowledge_body: string;
            about_ingestion_title: string;
            about_ingestion_body: string;
            about_access_title: string;
            about_access_body: string;
            about_rights_title: string;
            about_rights_body: string;
            about_privacy_title: string;
            about_privacy_body: string;
            about_warning_title: string;
            about_warning_body: string;
            copyright_text: string;
            navigation: {
                [key: string]: string;
            };
            sections: {
                [key: string]: string;
            };
        };
        SiteContent: {
            config: components["schemas"]["SiteConfig"];
            about_blocks: components["schemas"]["AboutPageBlock"][];
            edit_version: string;
            readonly has_unpublished_changes: boolean;
        };
        SiteContentRequest: {
            config: components["schemas"]["SiteConfigRequest"];
            about_blocks: components["schemas"]["AboutPageBlockRequest"][];
            edit_version: string;
        };
        /**
         * @description * `draft` - draft
         *     * `changes_pending` - changes_pending
         * @enum {string}
         */
        StateEnum: "draft" | "changes_pending";
        /**
         * @description * `drafting` - 编目中
         *     * `reviewing` - 核对中
         *     * `ready` - 准备发布
         *     * `publishing` - 发布中
         *     * `published` - 已发布
         *     * `abandoned` - 已结束编辑
         * @enum {string}
         */
        StatusEnum: "drafting" | "reviewing" | "ready" | "publishing" | "published" | "abandoned";
        /**
         * @description * `none` - 尚无文字
         *     * `embedded` - PDF 原生文本
         *     * `ocr` - OCR
         *     * `hybrid` - 混合
         * @enum {string}
         */
        TextSourceEnum: "none" | "embedded" | "ocr" | "hybrid";
        /**
         * @description * `paragraph` - paragraph
         *     * `heading` - heading
         *     * `quote` - quote
         *     * `link` - link
         * @enum {string}
         */
        TypeEnum: "paragraph" | "heading" | "quote" | "link";
        /**
         * @description * `320` - 320
         *     * `640` - 640
         *     * `1280` - 1280
         * @enum {integer}
         */
        WidthEnum: 320 | 640 | 1280;
        WorkCard: {
            /** Format: uuid */
            readonly id: string;
            document_type: components["schemas"]["DocumentTypeEnum"];
            title: string;
            subtitle?: string;
            original_title?: string;
            uniform_title?: string;
            abstract?: string;
            language?: string;
            original_language?: string;
            /** Format: date */
            first_publication_date?: string | null;
            /** Format: uuid */
            translation_of?: string | null;
            readonly cover: string;
            readonly cover_media: components["schemas"]["PublicCoverMedia"] | null;
            readonly recommendation_image: string;
            readonly recommendation_media: components["schemas"]["PublicCoverMedia"] | null;
            readonly edition: components["schemas"]["EditionCompact"] | null;
            readonly theories: components["schemas"]["PublicEntityLink"][];
            readonly topics: components["schemas"]["PublicEntityLink"][];
            readonly disciplines: components["schemas"]["PublicClassificationLink"][];
            readonly subdisciplines: components["schemas"]["PublicClassificationLink"][];
        };
        WorkDetail: {
            /** Format: uuid */
            readonly id: string;
            document_type: components["schemas"]["DocumentTypeEnum"];
            title: string;
            subtitle?: string;
            original_title?: string;
            uniform_title?: string;
            abstract?: string;
            language?: string;
            original_language?: string;
            /** Format: date */
            first_publication_date?: string | null;
            /** Format: uuid */
            translation_of?: string | null;
            readonly cover: string;
            readonly cover_media: components["schemas"]["PublicCoverMedia"] | null;
            readonly recommendation_image: string;
            readonly recommendation_media: components["schemas"]["PublicCoverMedia"] | null;
            readonly edition: components["schemas"]["EditionCompact"] | null;
            readonly theories: components["schemas"]["PublicEntityLink"][];
            readonly topics: components["schemas"]["PublicEntityLink"][];
            readonly disciplines: components["schemas"]["PublicClassificationLink"][];
            readonly subdisciplines: components["schemas"]["PublicClassificationLink"][];
            readonly editions: components["schemas"]["EditionCompact"][];
            readonly outline: components["schemas"]["PublicOutlineItem"][];
            readonly theory_associations: components["schemas"]["PublicTheoryAssociation"][];
            /** @description Evidence-backed curation groups; detailed EvidenceEnvelope JSON is not yet a verified typed contract. */
            readonly curated_claims: {
                [key: string]: unknown[];
            };
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    catalog_admin_bibliographic_candidates_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BibliographicLookupRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["BibliographicLookupRequest"];
                "multipart/form-data": components["schemas"]["BibliographicLookupRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    catalog_admin_catalog_field_contracts_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    cataloging_sessions_list: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogingSessionList"];
                };
            };
        };
    };
    catalog_admin_cataloging_sessions_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CatalogingSessionCreateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CatalogingSessionCreateRequest"];
                "multipart/form-data": components["schemas"]["CatalogingSessionCreateRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogingSession"];
                };
            };
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogingSession"];
                };
            };
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    cataloging_sessions_detail: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogingSessionDetail"];
                };
            };
        };
    };
    catalog_admin_cataloging_sessions_abandon_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogingSession"];
                };
            };
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    catalog_admin_cataloging_sessions_candidates_decision_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                candidate_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CatalogingCandidateDecisionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CatalogingCandidateDecisionRequest"];
                "multipart/form-data": components["schemas"]["CatalogingCandidateDecisionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    catalog_admin_cataloging_sessions_metadata_decision_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                candidate_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MetadataDecisionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MetadataDecisionRequest"];
                "multipart/form-data": components["schemas"]["MetadataDecisionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    catalog_admin_cataloging_sessions_metadata_import_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CatalogingMetadataImportRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CatalogingMetadataImportRequest"];
                "multipart/form-data": components["schemas"]["CatalogingMetadataImportRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    catalog_admin_curation_drafts_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurationDraftPage"];
                };
            };
        };
    };
    catalog_admin_discovery_index_retrieve: {
        parameters: {
            query?: {
                page?: number;
                page_size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexStatus"];
                };
            };
        };
    };
    catalog_admin_discovery_index_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IndexActionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["IndexActionRequest"];
                "multipart/form-data": components["schemas"]["IndexActionRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexActionResult"];
                };
            };
        };
    };
    catalog_admin_editions_media_cover_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                edition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CoverMediaSelectionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CoverMediaSelectionRequest"];
                "multipart/form-data": components["schemas"]["CoverMediaSelectionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CoverMediaSelectionResult"];
                };
            };
        };
    };
    catalog_admin_editions_media_recommendation_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                edition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CoverMediaSelectionRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CoverMediaSelectionRequest"];
                "multipart/form-data": components["schemas"]["CoverMediaSelectionRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CoverMediaSelectionResult"];
                };
            };
        };
    };
    catalog_admin_editions_publication_history_list: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                edition_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicationHistoryItem"][];
                };
            };
        };
    };
    catalog_admin_editions_publication_prepare_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                edition_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicationPreparation"];
                };
            };
        };
    };
    catalog_admin_editions_publication_rollback_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                edition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PublicationRollbackRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PublicationRollbackRequest"];
                "multipart/form-data": components["schemas"]["PublicationRollbackRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicationRollbackResult"];
                };
            };
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiError"];
                };
            };
        };
    };
    catalog_admin_evidence_curation_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                object_id: string;
                object_type: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvidenceCuration"];
                };
            };
        };
    };
    catalog_admin_evidence_curation_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                object_id: string;
                object_type: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvidenceCurationRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EvidenceCurationRequest"];
                "multipart/form-data": components["schemas"]["EvidenceCurationRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvidenceCuration"];
                };
            };
        };
    };
    catalog_admin_evidence_curation_publish_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                object_id: string;
                object_type: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EditorialPublishRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EditorialPublishRequest"];
                "multipart/form-data": components["schemas"]["EditorialPublishRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvidenceCuration"];
                };
            };
        };
    };
    catalog_admin_evidence_curation_sources_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurationSourcesPage"];
                };
            };
        };
    };
    catalog_admin_knowledge_media_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                object_id: string;
                object_type: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeImageState"];
                };
            };
        };
    };
    catalog_admin_knowledge_media_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                object_id: string;
                object_type: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KnowledgeImageRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["KnowledgeImageRequestRequest"];
                "multipart/form-data": components["schemas"]["KnowledgeImageRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeImageState"];
                };
            };
        };
    };
    catalog_admin_media_list: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MediaAsset"][];
                };
            };
        };
    };
    catalog_admin_media_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["MediaUploadRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MediaUploadRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MediaAsset"];
                };
            };
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MediaAsset"];
                };
            };
        };
    };
    catalog_admin_media_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                media_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MediaDetail"];
                };
            };
        };
    };
    catalog_admin_media_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                media_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedMediaMetadataRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedMediaMetadataRequest"];
                "multipart/form-data": components["schemas"]["PatchedMediaMetadataRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MediaAsset"];
                };
            };
        };
    };
    catalog_admin_media_renditions_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                media_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["MediaRenditionRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MediaRenditionRequestRequest"];
                "multipart/form-data": components["schemas"]["MediaRenditionRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MediaRendition"];
                };
            };
        };
    };
    catalog_admin_media_collection_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MediaCollection"];
                };
            };
        };
    };
    catalog_admin_people_retrieve: {
        parameters: {
            query?: {
                limit?: number;
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonSearchResponse"];
                };
            };
        };
    };
    catalog_admin_people_duplicates_retrieve: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonDuplicateResponse"];
                };
            };
        };
    };
    catalog_admin_people_merge_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonMergeRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PersonMergeRequestRequest"];
                "multipart/form-data": components["schemas"]["PersonMergeRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonMergeRecord"];
                };
            };
        };
    };
    catalog_admin_people_merge_preview_retrieve: {
        parameters: {
            query?: {
                target_person?: string;
            };
            header?: never;
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonMergePreviewResponse"];
                };
            };
        };
    };
    catalog_admin_people_merge_records_list: {
        parameters: {
            query: {
                source_person: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonMergeHistoryItem"][];
                };
            };
        };
    };
    catalog_admin_people_merge_records_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                record_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonMergeRecord"];
                };
            };
        };
    };
    catalog_admin_people_merge_records_rollback_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                record_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonMergeRollbackRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PersonMergeRollbackRequestRequest"];
                "multipart/form-data": components["schemas"]["PersonMergeRollbackRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonMergeRecord"];
                };
            };
        };
    };
    catalog_admin_recommendation_issues_list: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminRecommendationIssueCollection"];
                };
            };
        };
    };
    catalog_admin_recommendation_issues_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RecommendationIssueRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["RecommendationIssueRequest"];
                "multipart/form-data": components["schemas"]["RecommendationIssueRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationIssue"];
                };
            };
        };
    };
    catalog_admin_recommendation_issues_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                issue_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationIssue"];
                };
            };
        };
    };
    catalog_admin_recommendation_issues_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                issue_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RecommendationIssueRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["RecommendationIssueRequest"];
                "multipart/form-data": components["schemas"]["RecommendationIssueRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationIssue"];
                };
            };
        };
    };
    catalog_admin_recommendation_issues_items_link_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                issue_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlannedItemLinkRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PlannedItemLinkRequest"];
                "multipart/form-data": components["schemas"]["PlannedItemLinkRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationIssue"];
                };
            };
        };
    };
    catalog_admin_recommendation_issues_publish_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                issue_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EditorialPublishRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EditorialPublishRequest"];
                "multipart/form-data": components["schemas"]["EditorialPublishRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationIssue"];
                };
            };
        };
    };
    catalog_admin_scholar_relations_list: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScholarRelationPage"];
                };
            };
        };
    };
    catalog_admin_scholar_relations_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScholarRelationRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ScholarRelationRequest"];
                "multipart/form-data": components["schemas"]["ScholarRelationRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScholarRelation"];
                };
            };
        };
    };
    catalog_admin_scholar_relations_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScholarRelation"];
                };
            };
        };
    };
    catalog_admin_scholar_relations_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScholarRelationRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ScholarRelationRequest"];
                "multipart/form-data": components["schemas"]["ScholarRelationRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScholarRelation"];
                };
            };
        };
    };
    catalog_admin_scholar_relations_archive_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EditorialPublishRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EditorialPublishRequest"];
                "multipart/form-data": components["schemas"]["EditorialPublishRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScholarRelation"];
                };
            };
        };
    };
    catalog_admin_scholar_relations_publish_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EditorialPublishRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EditorialPublishRequest"];
                "multipart/form-data": components["schemas"]["EditorialPublishRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScholarRelation"];
                };
            };
        };
    };
    catalog_admin_scholars_portrait_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scholar_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScholarPortraitState"];
                };
            };
        };
    };
    catalog_admin_scholars_portrait_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scholar_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScholarPortraitRequestRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ScholarPortraitRequestRequest"];
                "multipart/form-data": components["schemas"]["ScholarPortraitRequestRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScholarPortraitState"];
                };
            };
        };
    };
    catalog_admin_site_content_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SiteContent"];
                };
            };
        };
    };
    catalog_admin_site_content_update: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SiteContentRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["SiteContentRequest"];
                "multipart/form-data": components["schemas"]["SiteContentRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SiteContent"];
                };
            };
        };
    };
    catalog_admin_site_content_publish_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EditorialPublishRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EditorialPublishRequest"];
                "multipart/form-data": components["schemas"]["EditorialPublishRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SiteContent"];
                };
            };
        };
    };
    catalog_admin_works_recommendation_image_metadata_retrieve: {
        parameters: {
            query?: {
                edition_id?: string;
            };
            header?: never;
            path: {
                work_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationImagePreview"];
                };
            };
        };
    };
    catalog_assets_manifest_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReaderManifest"];
                };
            };
        };
    };
    catalog_assets_pages_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
                page_index: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReaderPageContent"];
                };
            };
        };
    };
    catalog_discovery_search_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DiscoveryCreateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["DiscoveryCreateRequest"];
                "multipart/form-data": components["schemas"]["DiscoveryCreateRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DiscoveryResponse"];
                };
            };
        };
    };
    catalog_discovery_search_retrieve: {
        parameters: {
            query?: {
                cursor?: string;
                limit?: number;
            };
            header?: {
                /** @description Anonymous search capability returned once at creation; do not put in URLs. */
                "X-Discovery-Token"?: string;
            };
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DiscoveryResponse"];
                };
            };
        };
    };
    catalog_discovery_search_cancel_create: {
        parameters: {
            query?: never;
            header?: {
                /** @description Anonymous search capability returned once at creation; do not put in URLs. */
                "X-Discovery-Token"?: string;
            };
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DiscoveryResponse"];
                };
            };
        };
    };
    catalog_discovery_search_context_retrieve: {
        parameters: {
            query: {
                result_id: string;
            };
            header?: {
                /** @description Anonymous search capability returned once at creation; do not put in URLs. */
                "X-Discovery-Token"?: string;
            };
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DiscoveryContext"];
                };
            };
        };
    };
    catalog_discovery_search_expand_create: {
        parameters: {
            query?: never;
            header?: {
                /** @description Anonymous search capability returned once at creation; do not put in URLs. */
                "X-Discovery-Token"?: string;
            };
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DiscoveryResponse"];
                };
            };
        };
    };
    catalog_evidence_curation_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                object_id: string;
                object_type: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvidenceCuration"];
                };
            };
        };
    };
    catalog_recommendation_issues_list: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationIssueCollection"];
                };
            };
        };
    };
    catalog_recommendation_issues_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                slug: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationIssue"];
                };
            };
        };
    };
    catalog_recommendation_issues_save_list_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                slug: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedIssueList"];
                };
            };
        };
    };
    catalog_scholar_relations_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScholarRelationPage"];
                };
            };
        };
    };
    catalog_works_list: {
        parameters: {
            query?: {
                /**
                 * @description * `book` - 图书
                 *     * `journal_article` - 期刊论文
                 *     * `journal_issue` - 整期期刊
                 *     * `thesis` - 学位论文
                 *     * `report` - 研究报告
                 */
                document_type?: "book" | "journal_article" | "journal_issue" | "report" | "thesis";
                language?: string;
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaginatedWorkCardList"];
                };
            };
        };
    };
    catalog_works_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                slug: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkDetail"];
                };
            };
        };
    };
    catalog_works_cover_metadata_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                work_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicCoverMedia"];
                };
            };
        };
    };
    catalog_works_recommendation_image_metadata_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                work_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicCoverMedia"];
                };
            };
        };
    };
    distribution_assets_access_retrieve: {
        parameters: {
            query?: {
                /** @description original selects the original PDF; 1 or true selects the preferred download. */
                download?: string;
            };
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReaderAssetAccess"];
                };
            };
        };
    };
}

/** Generated from DRF/OpenAPI. Do not edit by hand. */
export interface paths {
    "/api/catalog/admin/assets/{asset_id}/outline/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_assets_outline_retrieve"];
        put?: never;
        post: operations["catalog_admin_assets_outline_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
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
    "/api/catalog/admin/content-placements/{page_type}/{page_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_content_placements_retrieve"];
        put?: never;
        post: operations["catalog_admin_content_placements_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/content-placements/{page_type}/{page_id}/history/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_content_placements_history_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/content-placements/sources/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_content_placements_sources_retrieve"];
        put?: never;
        post?: never;
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
    "/api/catalog/admin/editions/{edition_id}/reader-rendition/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put: operations["catalog_admin_editions_reader_rendition_update"];
        post?: never;
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
    "/api/catalog/admin/outline-jobs/{job_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_outline_jobs_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/outline-rebuilds/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description Bounded old-library inventory; GET never schedules a job. */
        get: operations["catalog_admin_outline_rebuilds_retrieve"];
        put?: never;
        post: operations["catalog_admin_outline_rebuilds_create"];
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
    "/api/catalog/admin/recommendation-issues/{issue_id}/assistant/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_editorial_assistance_list"];
        put?: never;
        post: operations["catalog_editorial_assistance_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/recommendation-issues/{issue_id}/assistant/{job_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_editorial_assistance_retrieve"];
        put?: never;
        post: operations["catalog_editorial_assistance_command"];
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
    "/api/catalog/assets/{asset_id}/outline/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_assets_outline_retrieve"];
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
    "/api/catalog/assets/{asset_id}/search/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_assets_search_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/content-placements/{page_type}/{page_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_content_placements_retrieve"];
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
    "/api/catalog/discovery-search/{session_id}/retry/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_discovery_search_retry_create"];
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
    "/api/catalog/home/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_home"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/passages/{id}/focus/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_passages_focus_retrieve"];
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
    "/api/catalog/theory-system/evidence/{id}/focus/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description Return a reviewed evidence locator for the existing PDF reader. */
        get: operations["catalog_theory_system_evidence_focus_retrieve"];
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
    "/api/distribution/admin/assets/{asset_id}/preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * @description Serve one current normalized PDF to authenticated back-office staff.
         *
         *     This endpoint deliberately bypasses only the publication-state filter. It
         *     keeps the existing file-path, X-Accel and Range safeguards, and forces
         *     private no-store caching so draft assets never enter a shared cache.
         */
        get: operations["distribution_admin_assets_preview_retrieve"];
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
    "/api/distribution/assets/{asset_id}/file/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["distribution_assets_file_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/distribution/backups/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["distribution_backups_list"];
        put?: never;
        post: operations["distribution_backups_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-audits/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_list"];
        put?: never;
        post: operations["reading_citation_audits_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-audits/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_retrieve"];
        put?: never;
        post?: never;
        delete: operations["reading_citation_audits_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-audits/{id}/command/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_citation_audits_command_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-audits/{id}/export/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_export_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-audits/{id}/ocr/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_ocr_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-audits/{id}/original/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_original_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-audits/capabilities/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_capabilities_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/reading-plans/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_reading_plans_list"];
        put?: never;
        post: operations["reading_reading_plans_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/reading-plans/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_reading_plans_retrieve"];
        put?: never;
        post?: never;
        delete: operations["reading_reading_plans_destroy"];
        options?: never;
        head?: never;
        patch: operations["reading_reading_plans_partial_update"];
        trace?: never;
    };
    "/api/reading/reading-plans/{id}/command/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_reading_plans_command_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/reading-plans/{id}/export/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_reading_plans_export_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-account/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_account_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch: operations["reading_research_account_partial_update"];
        trace?: never;
    };
    "/api/reading/research-memories/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_memories_list"];
        put?: never;
        post: operations["reading_research_memories_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-memories/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_memories_retrieve"];
        put?: never;
        post?: never;
        delete: operations["reading_research_memories_destroy"];
        options?: never;
        head?: never;
        patch: operations["reading_research_memories_partial_update"];
        trace?: never;
    };
    "/api/reading/research-memories/{id}/export/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_memories_export_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-memories/search/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_research_memories_search_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-projects/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_projects_list"];
        put?: never;
        post: operations["reading_research_projects_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-projects/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_projects_retrieve"];
        put?: never;
        post?: never;
        delete: operations["reading_research_projects_destroy"];
        options?: never;
        head?: never;
        patch: operations["reading_research_projects_partial_update"];
        trace?: never;
    };
    "/api/reading/research-projects/{id}/comparison/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_research_projects_comparison_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-projects/{id}/export/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_projects_export_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-projects/{id}/selections/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_research_projects_selections_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-projects/{id}/turns/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_projects_turns_list"];
        put?: never;
        post: operations["reading_research_projects_turns_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-projects/import/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_research_projects_import_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-turns/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_turns_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-turns/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_turns_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-turns/{id}/cancel/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_research_turns_cancel_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-turns/{id}/decision/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_research_turns_decision_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-turns/{id}/expand/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_research_turns_expand_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-turns/{id}/export/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_turns_export_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-turns/{id}/retry/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_research_turns_retry_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/research-turns/{id}/subclaims/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_research_turns_subclaims_create"];
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
        AnalysisDecisionInputRequest: {
            expected_revision: number;
            /** @description 分析候选 id，来自轮次返回值。 */
            id: string;
            relation: components["schemas"]["RelationEnum"];
            note?: string;
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
        AuditCapabilitiesOutput: {
            readonly max_upload_bytes: number;
            readonly max_pdf_pages: number;
            readonly max_occurrences: number;
            readonly max_active_jobs_per_owner: number;
            readonly accepted_filetypes: string[];
            readonly default_checks: string[];
            readonly checks: unknown;
            readonly scopes: unknown;
            readonly ocr: unknown;
            readonly analysis: unknown;
        };
        /**
         * @description * `cancel` - cancel
         *     * `match` - match
         *     * `link` - link
         *     * `decision` - decision
         *     * `analyze` - analyze
         *     * `retry` - retry
         * @enum {string}
         */
        AuditCommandInputActionEnum: "cancel" | "match" | "link" | "decision" | "analyze" | "retry";
        AuditCommandInputRequest: {
            expected_revision: number;
            action: components["schemas"]["AuditCommandInputActionEnum"];
            /** Format: uuid */
            entry_id?: string;
            /** Format: uuid */
            edition_id?: string;
            /** Format: uuid */
            occurrence_id?: string;
            occurrence_ids?: string[];
            entry_ids?: string[];
            decision?: components["schemas"]["DecisionEnum"];
            note?: string;
            /** @description 仅保存本人的校正文案，不改写上传原稿或原始识别文字。 */
            corrected_text?: string;
            reference?: components["schemas"]["EvidenceReferenceInputRequest"];
        };
        AuditCreateInputRequest: {
            /** Format: uuid */
            request_id: string;
            /**
             * Format: binary
             * @description DOCX/PDF，最大 12 MiB，仅保存在本人的加密记录中。
             */
            file: string;
            /** Format: uuid */
            project_id?: string;
            /** @description multipart 使用重复 checks 字段；默认前三项，扫描 OCR 必须显式选择。 */
            checks?: components["schemas"]["ChecksEnum"][];
            scope?: components["schemas"]["ScopeEnum"];
        };
        /**
         * @description * `draft` - 草稿
         *     * `needs_review` - 待消歧
         *     * `verified` - 已核验
         *     * `rejected` - 已拒绝
         *     * `merged` - 已合并
         *     * `archived` - 已归档
         * @enum {string}
         */
        AuthorityStatusEnum: "draft" | "needs_review" | "verified" | "rejected" | "merged" | "archived";
        BackupJob: {
            /** Format: uuid */
            readonly id: string;
            readonly status: components["schemas"]["BackupJobStatusEnum"];
            destination_path: string;
            include_originals?: boolean;
            readonly archive_path: string;
            readonly manifest: unknown;
            readonly checksum: string;
            readonly error_message: string;
            /** Format: date-time */
            readonly started_at: string | null;
            /** Format: date-time */
            readonly completed_at: string | null;
            /** Format: date-time */
            readonly created_at: string;
        };
        BackupJobRequest: {
            destination_path: string;
            include_originals?: boolean;
        };
        /**
         * @description * `queued` - 等待
         *     * `running` - 执行中
         *     * `completed` - 完成
         *     * `failed` - 失败
         * @enum {string}
         */
        BackupJobStatusEnum: "queued" | "running" | "completed" | "failed";
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
            readonly status: components["schemas"]["CatalogingSessionStatusEnum"];
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
         * @description * `drafting` - 编目中
         *     * `reviewing` - 核对中
         *     * `ready` - 准备发布
         *     * `publishing` - 发布中
         *     * `published` - 已发布
         *     * `abandoned` - 已结束编辑
         * @enum {string}
         */
        CatalogingSessionStatusEnum: "drafting" | "reviewing" | "ready" | "publishing" | "published" | "abandoned";
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
        /**
         * @description * `citation_identification` - citation_identification
         *     * `bibliography_identity` - bibliography_identity
         *     * `version_page` - version_page
         *     * `scan_ocr` - scan_ocr
         * @enum {string}
         */
        ChecksEnum: "citation_identification" | "bibliography_identity" | "version_page" | "scan_ocr";
        CitationOCROutput: {
            readonly progress: unknown;
            readonly units: unknown;
            readonly unit: unknown;
        };
        ComparisonCellInputRequest: {
            dimension: string;
            /** @description 当前选材的 edition:/work:/asset: 身份，或原比较格的文献身份。 */
            column_id?: string;
            author?: string;
            reference_ids?: string[];
            note?: string;
        };
        ComparisonInputRequest: {
            expected_revision: number;
            dimensions: string[];
            cells: components["schemas"]["ComparisonCellInputRequest"][];
        };
        /**
         * @description * `work` - work
         *     * `edition` - edition
         *     * `node` - node
         *     * `span` - span
         * @enum {string}
         */
        ContentReferenceTypeEnum: "work" | "edition" | "node" | "span";
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
            state: components["schemas"]["CurationDraftStateEnum"];
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
        /**
         * @description * `draft` - draft
         *     * `changes_pending` - changes_pending
         * @enum {string}
         */
        CurationDraftStateEnum: "draft" | "changes_pending";
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
         * @description * `accepted` - accepted
         *     * `ignored` - ignored
         *     * `corrected` - corrected
         *     * `needs_review` - needs_review
         * @enum {string}
         */
        DecisionEnum: "accepted" | "ignored" | "corrected" | "needs_review";
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
        DiscoveryDeepProgress: {
            status: components["schemas"]["DiscoveryDeepProgressStatusEnum"];
            stage: string;
            completed: number;
            total: number;
            terminal: boolean;
            model: string;
            index_uid: string;
            index_generation: string;
            embedding_artifact: string;
            embedding_dimensions?: number | null;
            reranker_artifact: string;
            context_artifact: string;
            notice: string;
            /** Format: date-time */
            started_at?: string | null;
            /** Format: date-time */
            updated_at?: string | null;
            /** Format: date-time */
            finished_at?: string | null;
        };
        /**
         * @description * `baseline_ready` - baseline_ready
         *     * `deep_queued` - deep_queued
         *     * `deep_running` - deep_running
         *     * `completed` - completed
         *     * `partial` - partial
         *     * `unavailable` - unavailable
         *     * `pending` - pending
         *     * `queued` - queued
         *     * `running` - running
         *     * `degraded` - degraded
         *     * `disabled` - disabled
         *     * `skipped` - skipped
         *     * `failed` - failed
         * @enum {string}
         */
        DiscoveryDeepProgressStatusEnum: "baseline_ready" | "deep_queued" | "deep_running" | "completed" | "partial" | "unavailable" | "pending" | "queued" | "running" | "degraded" | "disabled" | "skipped" | "failed";
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
            /** Format: uuid */
            evidence_span_id?: string;
            /** Format: uuid */
            passage_id?: string;
            pdf_page: number;
            printed_page?: string;
            source_kind: string;
            source_revision: string;
            reader_url: string;
            locator_precision: string;
            context_reference: string;
            match_basis: string[];
            deep_rank?: number;
            /** Format: double */
            deep_score?: number | null;
            deep_context?: {
                [key: string]: unknown;
            };
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
            deep_passages?: components["schemas"]["DiscoveryPassage"][];
            deep_stage?: components["schemas"]["DiscoveryDeepProgress"];
            next_cursor: string | null;
            can_expand: boolean;
            can_retry: boolean;
            task_progress: components["schemas"]["DiscoveryTaskProgress"];
            retrieval_identity: components["schemas"]["DiscoveryRetrievalIdentity"];
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
            api_version?: string;
            canonical_endpoint?: string;
            deprecated?: boolean;
            status_url?: string;
        };
        DiscoveryRetrievalIdentity: {
            index_generation: string;
            index_uid: string;
            embedding_artifact: string;
            embedding_dimensions?: number | null;
            reranker_artifact: string;
            pipeline_version: string;
        };
        DiscoveryRetryRequest: {
            expected_generation: number;
        };
        DiscoveryTaskProgress: {
            /** Format: uuid */
            id: string;
            generation: number;
            status: string;
            terminal: boolean;
            stage: string;
            completed: number;
            total: number;
            unit: string;
            retryable: boolean;
            /** Format: date-time */
            started_at: string | null;
            /** Format: date-time */
            updated_at: string;
            /** Format: date-time */
            finished_at: string | null;
            deep: components["schemas"]["DiscoveryDeepProgress"];
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
        EditorialAssistance: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            issue_id: string;
            operation: components["schemas"]["OperationEnum"];
            status: string;
            stage: string;
            progress: number;
            error_code: string;
            error_message: string;
            source_available: boolean;
            draft_changed: boolean;
            can_adopt: boolean;
            edit_version: string;
            sources: {
                [key: string]: unknown;
            }[];
            suggestions: components["schemas"]["EditorialSuggestion"][];
            adopted_ids: string[];
            model: {
                [key: string]: unknown;
            } | null;
            poll_after_ms: number | null;
        };
        /**
         * @description * `retry` - retry
         *     * `cancel` - cancel
         *     * `adopt` - adopt
         * @enum {string}
         */
        EditorialAssistanceCommandActionEnum: "retry" | "cancel" | "adopt";
        EditorialAssistanceCommandRequest: {
            action: components["schemas"]["EditorialAssistanceCommandActionEnum"];
            /** Format: uuid */
            request_id?: string;
            edit_version?: string;
            suggestion_ids?: string[];
        };
        EditorialAssistanceInputRequest: {
            /** Format: uuid */
            request_id: string;
            edit_version: string;
            operation: components["schemas"]["OperationEnum"];
            question: string;
            references: {
                [key: string]: unknown;
            }[];
        };
        EditorialAssistancePage: {
            count: number;
            page: number;
            total_pages: number;
            results: components["schemas"]["EditorialAssistance"][];
        };
        /**
         * @description * `paragraph` - paragraph
         *     * `heading` - heading
         *     * `quote` - quote
         *     * `link` - link
         *     * `evidence` - evidence
         *     * `work` - work
         *     * `person` - person
         *     * `concept` - concept
         *     * `node` - node
         *     * `timeline` - timeline
         *     * `reading_path` - reading_path
         *     * `comparison` - comparison
         *     * `analysis` - analysis
         * @enum {string}
         */
        EditorialBlockTypeEnum: "paragraph" | "heading" | "quote" | "link" | "evidence" | "work" | "person" | "concept" | "node" | "timeline" | "reading_path" | "comparison" | "analysis";
        EditorialPublishRequest: {
            edit_version: string;
        };
        /**
         * @description * `catalog` - catalog
         *     * `planned` - planned
         * @enum {string}
         */
        EditorialSourceKindEnum: "catalog" | "planned";
        EditorialSuggestion: {
            /** Format: uuid */
            id: string;
            kind: components["schemas"]["EditorialTextKindEnum"];
            text: string;
            source_keys: string[];
            gap: string;
        };
        /**
         * @description * `heading` - heading
         *     * `paragraph` - paragraph
         * @enum {string}
         */
        EditorialTextKindEnum: "heading" | "paragraph";
        /**
         * @description * `ocr_pdf` - ocr_pdf
         *     * `normalized` - normalized
         * @enum {string}
         */
        EffectiveRenditionEnum: "ocr_pdf" | "normalized";
        EvidenceAnchorInputRequest: {
            /** Format: uuid */
            evidence_span_id?: string;
            /** Format: uuid */
            asset_id?: string;
            /** Format: uuid */
            document_revision_id?: string;
            pdf_page?: number;
            content_hash?: string;
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
        EvidenceReferenceInputRequest: {
            /** Format: uuid */
            evidence_span_id?: string;
            /** Format: uuid */
            asset_id?: string;
            /** Format: uuid */
            document_revision_id?: string;
            pdf_page?: number;
            content_hash?: string;
            /** @description 跨页引用按顺序传 1—20 个同文件同修订的单页锚点。 */
            anchors?: components["schemas"]["EvidenceAnchorInputRequest"][];
        };
        HomeResponse: {
            schema_version: string;
            visibility: components["schemas"]["VisibilityEnum"];
            status: components["schemas"]["HomeResponseStatusEnum"];
            config: components["schemas"]["SiteConfig"] | null;
            works: components["schemas"]["WorkCard"][];
            random_works: components["schemas"]["WorkCard"][];
            scholars: components["schemas"]["ScholarProfile"][];
            topics: components["schemas"]["Topic"][];
            issues: components["schemas"]["RecommendationIssue"][];
            issue: components["schemas"]["RecommendationIssue"] | null;
            issue_count: number | null;
            hot_searches: string[];
            sections: components["schemas"]["HomeSections"];
        };
        /**
         * @description * `ready` - ready
         *     * `empty` - empty
         *     * `partial` - partial
         *     * `unavailable` - unavailable
         * @enum {string}
         */
        HomeResponseStatusEnum: "ready" | "empty" | "partial" | "unavailable";
        HomeSection: {
            status: components["schemas"]["HomeSectionStatusEnum"];
            source: string;
            count: number | null;
            message: string;
        };
        /**
         * @description * `ready` - ready
         *     * `empty` - empty
         *     * `unavailable` - unavailable
         * @enum {string}
         */
        HomeSectionStatusEnum: "ready" | "empty" | "unavailable";
        HomeSections: {
            works: components["schemas"]["HomeSection"];
            random_works: components["schemas"]["HomeSection"];
            scholars: components["schemas"]["HomeSection"];
            topics: components["schemas"]["HomeSection"];
            issues: components["schemas"]["HomeSection"];
            hot_searches: components["schemas"]["HomeSection"];
            config: components["schemas"]["HomeSection"];
        };
        ImportedComparisonInputRequest: {
            dimensions: string[];
            cells: components["schemas"]["ComparisonCellInputRequest"][];
        };
        ImportedTurnInputRequest: {
            local_id: string;
            parent_local_id?: string;
            question: string;
            scope?: components["schemas"]["QueryScopeInputRequest"];
            references?: components["schemas"]["EvidenceReferenceInputRequest"][];
            selected_references?: components["schemas"]["EvidenceReferenceInputRequest"][];
            notes?: string;
            /** Format: date-time */
            created_at?: string;
            status?: components["schemas"]["ImportedTurnInputStatusEnum"];
        };
        /**
         * @description * `queued` - queued
         *     * `running` - running
         *     * `completed` - completed
         *     * `partial` - partial
         *     * `failed` - failed
         *     * `canceled` - canceled
         * @enum {string}
         */
        ImportedTurnInputStatusEnum: "queued" | "running" | "completed" | "partial" | "failed" | "canceled";
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
            /** Format: uuid */
            id?: string;
            type: components["schemas"]["EditorialBlockTypeEnum"];
            text: string;
            source?: string;
            url?: string;
            target?: {
                [key: string]: unknown;
            };
            dimensions?: string[];
            rows?: {
                [key: string]: unknown;
            }[];
            references?: {
                [key: string]: unknown;
            }[];
            style?: components["schemas"]["EditorialTextKindEnum"];
            readonly source_status: string;
            readonly resolved_sources: {
                [key: string]: unknown;
            }[];
        };
        IssueBodyBlockRequest: {
            /** Format: uuid */
            id?: string;
            type: components["schemas"]["EditorialBlockTypeEnum"];
            text: string;
            source?: string;
            url?: string;
            target?: {
                [key: string]: unknown;
            };
            dimensions?: string[];
            rows?: {
                [key: string]: unknown;
            }[];
            references?: {
                [key: string]: unknown;
            }[];
            style?: components["schemas"]["EditorialTextKindEnum"];
        };
        IssueItem: {
            /** Format: uuid */
            id?: string;
            kind: components["schemas"]["EditorialSourceKindEnum"];
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
        IssueItemRequest: {
            /** Format: uuid */
            id?: string;
            kind: components["schemas"]["EditorialSourceKindEnum"];
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
        ItemEstimateInputRequest: {
            /** Format: uuid */
            work_id: string;
            difficulty?: components["schemas"]["ReadingDifficultyEnum"];
            minutes?: number;
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
        MemoryCreateInputRequest: {
            /** Format: uuid */
            request_id: string;
            body: string;
            /** @default understanding */
            kind: components["schemas"]["ResearchMemoryKindEnum"];
            /** Format: uuid */
            project_id?: string;
            /** Format: uuid */
            turn_id?: string;
            /** Format: uuid */
            annotation_id?: string;
            sources?: components["schemas"]["EvidenceReferenceInputRequest"][];
        };
        MemorySearchInputRequest: {
            q: string;
            /** @default false */
            semantic: boolean;
            allowed_ids?: string[];
        };
        MemorySearchOutput: {
            readonly results: components["schemas"]["MemorySearchResult"][];
            readonly mode: components["schemas"]["MemorySearchOutputModeEnum"];
            readonly notice: string;
            readonly warning: string;
            readonly semantic_candidate_limit: number | null;
            readonly semantic_scope_count: number | null;
            readonly semantic_evaluated_count: number | null;
            readonly semantic_excluded_count: number | null;
            readonly semantic_scope_complete: boolean;
        };
        /**
         * @description * `disabled` - disabled
         *     * `local_lexical` - local_lexical
         *     * `local_semantic_owner_candidates` - local_semantic_owner_candidates
         * @enum {string}
         */
        MemorySearchOutputModeEnum: "disabled" | "local_lexical" | "local_semantic_owner_candidates";
        MemorySearchResult: {
            /** Format: uuid */
            readonly id: string;
            readonly revision: number;
            readonly data: unknown;
            readonly status: string;
            readonly state: string;
            readonly enhancement_status: string;
            readonly archived: boolean;
            readonly generation: number;
            readonly error_code: string;
            readonly poll_after_ms: number | null;
            readonly completed_units: number;
            readonly total_units: number;
            /** Format: uuid */
            readonly project_id: string | null;
            /** Format: uuid */
            readonly conversation_id: string | null;
            /** Format: uuid */
            readonly parent_id: string | null;
            /** Format: uuid */
            readonly discovery_session_id: string | null;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
            /** Format: date-time */
            readonly finished_at: string | null;
            readonly match_reason: string;
        };
        /**
         * @description * `proposed` - proposed
         *     * `confirmed` - confirmed
         *     * `ignored` - ignored
         * @enum {string}
         */
        MemoryUpdateInputStateEnum: "proposed" | "confirmed" | "ignored";
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
        /**
         * @description * `outline` - outline
         *     * `guide` - guide
         *     * `comparison` - comparison
         * @enum {string}
         */
        OperationEnum: "outline" | "guide" | "comparison";
        OutlineBatchRequest: {
            asset_ids: string[];
            /** Format: uuid */
            request_id: string;
        };
        /**
         * @description * `rebuild` - rebuild
         *     * `edit` - edit
         *     * `adopt` - adopt
         *     * `restore` - restore
         * @enum {string}
         */
        OutlineCommandActionEnum: "rebuild" | "edit" | "adopt" | "restore";
        OutlineCommandRequest: {
            action: components["schemas"]["OutlineCommandActionEnum"];
            expected_revision?: number;
            /** Format: uuid */
            revision_id?: string;
            /** Format: uuid */
            request_id?: string;
            nodes?: components["schemas"]["OutlineNodeRequest"][];
        };
        /**
         * @description * `retry` - retry
         *     * `cancel` - cancel
         * @enum {string}
         */
        OutlineJobCommandActionEnum: "retry" | "cancel";
        OutlineJobCommandRequest: {
            action: components["schemas"]["OutlineJobCommandActionEnum"];
        };
        OutlineNodeRequest: {
            /** Format: uuid */
            id?: string;
            /** Format: uuid */
            parent_id?: string | null;
            title: string;
            pdf_page: number | null;
            printed_label?: string;
            pdf_position?: number[];
            normalized_position?: number[];
            contents_page?: number | null;
        };
        PaginatedBackupJobList: {
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
            results: components["schemas"]["BackupJob"][];
        };
        PaginatedPrivateRecordList: {
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
            results: components["schemas"]["PrivateRecord"][];
        };
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
        PatchedMemoryUpdateInputRequest: {
            expected_revision?: number;
            body?: string;
            sources?: components["schemas"]["EvidenceReferenceInputRequest"][];
            state?: components["schemas"]["MemoryUpdateInputStateEnum"];
        };
        PatchedPlanUpdateInputRequest: {
            expected_revision?: number;
            time_budget?: string;
            budget_minutes?: number | null;
            session_minutes?: number;
            reading_level?: components["schemas"]["ReadingDifficultyEnum"];
            reading_pace?: components["schemas"]["ReadingPaceInputRequest"];
            prefer_unread?: boolean;
            item_estimates?: components["schemas"]["ItemEstimateInputRequest"][];
            /** @description 与 duration_weeks 成对提供；相乘为总预算，最多 100000 分钟。 */
            weekly_minutes?: number;
            duration_weeks?: number;
            /** @description 用于导读提示，不自动排除已选材料。 */
            language_preference?: string;
            /** @description 默认关闭，仅使用显式选择的本人已确认笔记。 */
            use_confirmed_memories?: boolean;
            confirmed_memory_ids?: string[];
            goal?: string;
            background?: string;
            order?: string[];
            /** Format: uuid */
            item_id?: string;
            status?: components["schemas"]["PlanUpdateInputStatusEnum"];
            note?: string;
            reference?: components["schemas"]["EvidenceReferenceInputRequest"];
            adopt_suggestion?: boolean;
            optimize_order?: boolean;
            /** @description 只计算调整预览，不写入或增加 revision；确认时以原 revision 再提交。 */
            preview?: boolean;
            /** @description 替换材料时，明确同意移除仅与被替换材料相关的先修关系；其他关系保留。 */
            remove_related_prerequisites?: boolean;
        };
        PatchedProjectUpdateInputRequest: {
            expected_revision?: number;
            title?: string;
            question?: string;
            notes?: string;
            scope?: components["schemas"]["QueryScopeInputRequest"];
            archived?: boolean;
            layout?: unknown;
        };
        PatchedResearchPreferenceInputRequest: {
            research_personalization?: boolean;
        };
        PersonCompact: {
            /** Format: uuid */
            readonly id: string;
            preferred_name: string;
            original_name?: string;
            aliases?: unknown;
            authority_status?: components["schemas"]["AuthorityStatusEnum"];
            /** Format: int64 */
            birth_year?: number | null;
            /** Format: int64 */
            death_year?: number | null;
            biography?: string;
            readonly portrait: string;
            readonly portrait_media: components["schemas"]["PublicCoverMedia"] | null;
            readonly scholar_slug: string | null;
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
        /**
         * @description * `save` - save
         *     * `add` - add
         *     * `move` - move
         *     * `update` - update
         *     * `remove` - remove
         *     * `undo` - undo
         *     * `restore` - restore
         *     * `publish` - publish
         *     * `withdraw` - withdraw
         * @enum {string}
         */
        PlacementCommandActionEnum: "save" | "add" | "move" | "update" | "remove" | "undo" | "restore" | "publish" | "withdraw";
        PlacementCommandRequest: {
            action: components["schemas"]["PlacementCommandActionEnum"];
            /** Format: uuid */
            request_id: string;
            expected_revision: string;
            items?: components["schemas"]["PlacementRequest"][];
            item?: components["schemas"]["PlacementRequest"];
            /** Format: uuid */
            item_id?: string;
            position?: number;
            area?: string;
            group?: string;
            patch?: {
                [key: string]: unknown;
            };
            /** Format: uuid */
            revision_id?: string;
        };
        PlacementHistoryItem: {
            /** Format: uuid */
            id: string;
            revision: number;
            base_revision: number;
            status: components["schemas"]["PlacementHistoryItemStatusEnum"];
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            published_at: string | null;
            item_count: number;
            withdrawn: boolean;
        };
        /**
         * @description * `draft` - draft
         *     * `published` - published
         *     * `superseded` - superseded
         * @enum {string}
         */
        PlacementHistoryItemStatusEnum: "draft" | "published" | "superseded";
        PlacementHistoryPage: {
            count: number;
            next: string | null;
            previous: string | null;
            results: components["schemas"]["PlacementHistoryItem"][];
        };
        PlacementRead: {
            schema_version: number;
            page_type: string;
            /** Format: uuid */
            page_id: string;
            /** Format: uuid */
            revision_id: string | null;
            configured: boolean;
            items: components["schemas"]["PlacementResultItem"][];
            withdrawn: boolean;
            expected_revision?: string;
            is_current_revision?: boolean;
            /** Format: uuid */
            published_revision_id?: string | null;
            has_unpublished_changes?: boolean;
            source_problems?: {
                [key: string]: unknown;
            }[];
            publication_blockers?: {
                [key: string]: unknown;
            }[];
            state?: string;
            can_publish?: boolean;
            impact?: string;
            title?: string;
            replayed?: boolean;
            /** Format: uuid */
            applied_revision_id?: string;
        };
        PlacementReaderTarget: {
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            document_revision_id: string;
            pdf_page: number;
        };
        PlacementRequest: {
            /** Format: uuid */
            id?: string;
            area?: string;
            group?: string;
            position?: number;
            target: components["schemas"]["PlacementTargetRequest"];
            reason?: string;
            local_text?: string;
            reading_target?: {
                [key: string]: unknown;
            } | null;
            concept_usage?: {
                [key: string]: unknown;
            } | null;
        };
        PlacementResultItem: {
            /** Format: uuid */
            id: string;
            area?: string;
            group?: string;
            position?: number;
            target: components["schemas"]["PlacementTarget"];
            reason?: string;
            local_text?: string;
            reading_target?: components["schemas"]["PlacementReaderTarget"] | null;
            concept_usage?: {
                [key: string]: unknown;
            } | null;
            source: components["schemas"]["PlacementSource"] | null;
        };
        PlacementSource: {
            type: components["schemas"]["ContentReferenceTypeEnum"];
            /** Format: uuid */
            id: string;
            title: string;
            public_eligible: boolean;
            /** Format: uuid */
            work_id?: string;
            /** Format: uuid */
            edition_id?: string;
            edition_label?: string;
            reader_url?: string;
            work_url?: string;
            edit_url?: string;
            source_type?: string;
            text?: string;
            context_before?: string;
            context_after?: string;
            work_title?: string;
            /** Format: uuid */
            asset_id?: string;
            page_start?: number;
            page_end?: number;
            printed_label?: string;
            /** Format: uuid */
            document_revision_id?: string | null;
            reader_target?: components["schemas"]["PlacementReaderTarget"];
            usage_author?: components["schemas"]["PlacementUsageAuthor"] | null;
        };
        PlacementSourceChoice: {
            target: components["schemas"]["PlacementTarget"];
            source: components["schemas"]["PlacementSource"];
        };
        PlacementSourcesPage: {
            count: number;
            next: string | null;
            previous: string | null;
            results: components["schemas"]["PlacementSourceChoice"][];
        };
        PlacementTarget: {
            type: components["schemas"]["ContentReferenceTypeEnum"];
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            edition_id?: string;
            /** Format: uuid */
            document_revision_id?: string;
        };
        PlacementTargetRequest: {
            type: components["schemas"]["ContentReferenceTypeEnum"];
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            edition_id?: string;
            /** Format: uuid */
            document_revision_id?: string;
        };
        PlacementUsageAuthor: {
            /** Format: uuid */
            id: string;
            name: string;
        };
        /**
         * @description * `cancel` - cancel
         *     * `retry` - retry
         *     * `enhance` - enhance
         * @enum {string}
         */
        PlanCommandInputActionEnum: "cancel" | "retry" | "enhance";
        PlanCommandInputRequest: {
            expected_revision: number;
            action: components["schemas"]["PlanCommandInputActionEnum"];
        };
        PlanCreateInputRequest: {
            time_budget?: string;
            budget_minutes?: number | null;
            session_minutes?: number;
            reading_level?: components["schemas"]["ReadingDifficultyEnum"];
            reading_pace?: components["schemas"]["ReadingPaceInputRequest"];
            prefer_unread?: boolean;
            item_estimates?: components["schemas"]["ItemEstimateInputRequest"][];
            /** @description 与 duration_weeks 成对提供；相乘为总预算，最多 100000 分钟。 */
            weekly_minutes?: number;
            duration_weeks?: number;
            /** @description 用于导读提示，不自动排除已选材料。 */
            language_preference?: string;
            /** @description 默认关闭，仅使用显式选择的本人已确认笔记。 */
            use_confirmed_memories?: boolean;
            confirmed_memory_ids?: string[];
            /** Format: uuid */
            request_id: string;
            /** @description 无材料时先启动 Discovery；此时问题最多 1200 字符。 */
            goal: string;
            background?: string;
            /** Format: uuid */
            project_id?: string;
            /** Format: uuid */
            turn_id?: string;
            /** Format: uuid */
            reading_path_id?: string;
            references?: components["schemas"]["EvidenceReferenceInputRequest"][];
            prerequisites?: components["schemas"]["PrerequisiteInputRequest"][];
            scope?: components["schemas"]["QueryScopeInputRequest"];
        };
        /**
         * @description * `pending` - pending
         *     * `reading` - reading
         *     * `completed` - completed
         *     * `skipped` - skipped
         * @enum {string}
         */
        PlanUpdateInputStatusEnum: "pending" | "reading" | "completed" | "skipped";
        PlannedItemLinkRequest: {
            edit_version: string;
            /** Format: uuid */
            work_id: string;
            /** Format: uuid */
            edition_id: string;
            confirm_version: boolean;
        };
        /**
         * @description * `positive` - positive
         *     * `negative` - negative
         *     * `mixed` - mixed
         *     * `uncertain` - uncertain
         * @enum {string}
         */
        PolarityEnum: "positive" | "negative" | "mixed" | "uncertain";
        /**
         * @description * `auto` - 自动选择
         *     * `original` - 强制原始 PDF
         *     * `ocr` - 强制 OCR PDF
         * @enum {string}
         */
        PolicyEnum: "auto" | "original" | "ocr";
        PrerequisiteInputRequest: {
            /** Format: uuid */
            work_id: string;
            /** Format: uuid */
            requires_work_id: string;
            reference: components["schemas"]["EvidenceReferenceInputRequest"];
        };
        PrivateRecord: {
            /** Format: uuid */
            readonly id: string;
            readonly revision: number;
            readonly data: unknown;
            readonly status: string;
            readonly state: string;
            readonly enhancement_status: string;
            readonly archived: boolean;
            readonly generation: number;
            readonly error_code: string;
            readonly poll_after_ms: number | null;
            readonly completed_units: number;
            readonly total_units: number;
            /** Format: uuid */
            readonly project_id: string | null;
            /** Format: uuid */
            readonly conversation_id: string | null;
            /** Format: uuid */
            readonly parent_id: string | null;
            /** Format: uuid */
            readonly discovery_session_id: string | null;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
            /** Format: date-time */
            readonly finished_at: string | null;
        };
        PrivateRecordExport: {
            /** Format: uuid */
            readonly id: string;
            readonly revision: number;
            readonly data: unknown;
            readonly status: string;
            readonly state: string;
            readonly enhancement_status: string;
            readonly archived: boolean;
            readonly generation: number;
            readonly error_code: string;
            readonly poll_after_ms: number | null;
            readonly completed_units: number;
            readonly total_units: number;
            /** Format: uuid */
            readonly project_id: string | null;
            /** Format: uuid */
            readonly conversation_id: string | null;
            /** Format: uuid */
            readonly parent_id: string | null;
            /** Format: uuid */
            readonly discovery_session_id: string | null;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
            /** Format: date-time */
            readonly finished_at: string | null;
            readonly schema_version: number;
            readonly turns: components["schemas"]["PrivateRecord"][];
        };
        ProjectCreateInputRequest: {
            /**
             * Format: uuid
             * @description 客户端每次新操作生成，重试沿用。
             */
            request_id: string;
            title?: string;
            question?: string;
            /** Format: uuid */
            conversation_id?: string;
            scope?: components["schemas"]["QueryScopeInputRequest"];
        };
        ProjectImportInputRequest: {
            /** Format: uuid */
            request_id: string;
            title?: string;
            question?: string;
            scope?: components["schemas"]["QueryScopeInputRequest"];
            schema_version: number;
            local_id: string;
            selections?: components["schemas"]["EvidenceReferenceInputRequest"][];
            notes?: string;
            layout?: unknown;
            comparison?: components["schemas"]["ImportedComparisonInputRequest"];
            turns?: components["schemas"]["ImportedTurnInputRequest"][];
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
            /** Format: uuid */
            id?: string;
            /** Format: uuid */
            parent_id?: string | null;
            position?: number;
            level?: number;
            title?: string;
            pdf_page?: number;
            pdf_position?: number[];
            coordinate_unit?: string;
            coordinate_space?: string;
            source_locator?: unknown;
            page_geometry?: unknown;
            normalized_position?: number[];
            precision?: string;
            source?: string;
            calibration_status?: string;
            /** Format: uuid */
            outline_revision_id?: string;
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
        QueryScopeInputRequest: {
            /** @default library */
            kind: components["schemas"]["ResearchScopeKindEnum"];
            /** @description Discovery 同一过滤协议；作品/学者/主题/时期/语言/类型。 */
            filters?: unknown;
            references?: components["schemas"]["EvidenceReferenceInputRequest"][];
            /**
             * @description 限定段落时始终关闭，不扩大到整书。
             * @default false
             */
            allow_neighbors: boolean;
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
        ReaderDocumentSearch: {
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            document_revision_id: string;
            query: string;
            matches: components["schemas"]["ReaderSearchMatch"][];
        };
        ReaderFocus: {
            /** @description [x0,y0,x1,y1] in displayed cropped/rotated page fractions, or [] when coordinates are unknown. */
            normalized_bbox: number[];
            /** @description validated only proves the coordinate transform; otherwise unknown. */
            geometry_status: string;
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            document_revision_id: string;
            text_source: components["schemas"]["TextSourceEnum"];
            title: string;
            page_index: number;
            printed_label: string;
            /** Format: double */
            width: number;
            /** Format: double */
            height: number;
            bbox: unknown;
            geometry: unknown;
            text: string;
            locator_kind?: string;
            locators?: unknown[];
        };
        ReaderManifest: {
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            document_revision_id: string | null;
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
            asset_id: string;
            /** Format: uuid */
            document_revision_id: string | null;
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
            /** @description Versioned extraction coordinates, or {} for unknown historical units. */
            geometry: unknown;
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
        ReaderRenditionPolicyInputRequest: {
            policy: components["schemas"]["PolicyEnum"];
        };
        ReaderRenditionPolicyResult: {
            policy: components["schemas"]["PolicyEnum"];
            validated_ocr_pdf_available: boolean;
            effective_rendition: components["schemas"]["EffectiveRenditionEnum"];
            fallback_active: boolean;
        };
        ReaderSearchMatch: {
            /** Format: uuid */
            page_id: string;
            page_index: number;
            printed_label: string;
            snippet: string;
            /** Format: double */
            width: number;
            /** Format: double */
            height: number;
            geometry: unknown;
            blocks: unknown[];
            highlights: unknown[];
            rank: number;
            occurrence_count: number;
        };
        ReaderTextBlock: {
            /** @description [x0,y0,x1,y1] in displayed cropped/rotated page fractions, or [] when coordinates are unknown. */
            normalized_bbox: number[];
            /** @description validated only proves the coordinate transform; otherwise unknown. */
            geometry_status: string;
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
        /**
         * @description * `beginner` - beginner
         *     * `intermediate` - intermediate
         *     * `advanced` - advanced
         * @enum {string}
         */
        ReadingDifficultyEnum: "beginner" | "intermediate" | "advanced";
        ReadingPaceInputRequest: {
            cjk_chars_per_minute?: number;
            words_per_minute?: number;
            fallback_minutes_per_page?: number;
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
            readonly body_source_problems: {
                [key: string]: unknown;
            }[];
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
         * @description * `support` - support
         *     * `different_conclusion` - different_conclusion
         *     * `qualification` - qualification
         *     * `reframe` - reframe
         *     * `insufficient_evidence` - insufficient_evidence
         * @enum {string}
         */
        RelationEnum: "support" | "different_conclusion" | "qualification" | "reframe" | "insufficient_evidence";
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
        ResearchAccountCountsOutput: {
            readonly research: number;
            readonly memories: number;
            readonly plans: number;
            readonly audits: number;
        };
        ResearchAccountOutput: {
            readonly counts: components["schemas"]["ResearchAccountCountsOutput"];
            readonly preferences: boolean;
            readonly deletion_notice: string;
        };
        /**
         * @description * `understanding` - understanding
         *     * `question` - question
         *     * `contradiction` - contradiction
         * @enum {string}
         */
        ResearchMemoryKindEnum: "understanding" | "question" | "contradiction";
        ResearchPreferenceInput: {
            research_personalization: boolean;
        };
        /**
         * @description * `library` - library
         *     * `works` - works
         *     * `passages` - passages
         *     * `filtered` - filtered
         * @enum {string}
         */
        ResearchScopeKindEnum: "library" | "works" | "passages" | "filtered";
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
        ScholarProfile: {
            /** Format: uuid */
            readonly id: string;
            slug: string;
            person: components["schemas"]["PersonCompact"];
            short_description?: string;
            affiliations?: unknown;
            key_concerns?: unknown;
            timeline?: unknown;
            featured_quote?: string;
            quote_source?: string;
            readonly works: string;
            readonly curated: string;
            readonly curated_claims: string;
            readonly knowledge_nodes: string;
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
         * @description * `public_library` - public_library
         * @enum {string}
         */
        ScopeEnum: "public_library";
        /**
         * @description * `add` - add
         *     * `remove` - remove
         *     * `undo` - undo
         *     * `reorder` - reorder
         * @enum {string}
         */
        SelectionInputActionEnum: "add" | "remove" | "undo" | "reorder";
        SelectionInputRequest: {
            expected_revision: number;
            action: components["schemas"]["SelectionInputActionEnum"];
            references?: components["schemas"]["EvidenceReferenceInputRequest"][];
            reference_id?: string;
            order?: string[];
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
        StatementInputRequest: {
            proposition: string;
            subject?: string;
            predicate?: string;
            object?: string;
            polarity?: components["schemas"]["PolarityEnum"];
            modality?: string;
            qualifiers?: string[];
            temporal_scope?: unknown;
            geographic_scope?: unknown;
            population_scope?: unknown;
        };
        SubclaimInputRequest: {
            proposition: string;
            subject?: string;
            predicate?: string;
            object?: string;
            polarity?: components["schemas"]["PolarityEnum"];
            modality?: string;
            qualifiers?: string[];
            temporal_scope?: unknown;
            geographic_scope?: unknown;
            population_scope?: unknown;
            /** Format: uuid */
            id: string;
        };
        SubclaimsInputRequest: {
            expected_revision: number;
            /** @description 本人明确拆分的 0—12 个子命题；不自动认定为作者主张或有效反证。 */
            subclaims: components["schemas"]["SubclaimInputRequest"][];
        };
        /**
         * @description * `none` - 尚无文字
         *     * `embedded` - PDF 原生文本
         *     * `ocr` - OCR
         *     * `hybrid` - 混合
         * @enum {string}
         */
        TextSourceEnum: "none" | "embedded" | "ocr" | "hybrid";
        Topic: {
            /** Format: uuid */
            readonly id: string;
            name: string;
            slug: string;
            description?: string;
            problem_statement?: string;
            core_questions?: unknown;
            research_dimensions?: unknown;
            methods?: unknown;
            formation_context?: string;
            key_concepts?: unknown;
            timeline?: unknown;
            /** Format: uri */
            hero_image?: string | null;
            readonly disciplines: string;
            readonly subdisciplines: string;
            readonly linked_theories: string;
            readonly knowledge_nodes: string;
            readonly work_count: number;
            readonly curated: string;
            readonly curated_claims: string;
        };
        /**
         * @description * `search` - search
         *     * `counterargument` - counterargument
         * @enum {string}
         */
        TurnCreateInputModeEnum: "search" | "counterargument";
        TurnCreateInputRequest: {
            expected_revision: number;
            /** Format: uuid */
            request_id: string;
            question: string;
            /** Format: uuid */
            parent_id?: string;
            scope?: components["schemas"]["QueryScopeInputRequest"];
            /** @default search */
            mode: components["schemas"]["TurnCreateInputModeEnum"];
            statement?: components["schemas"]["StatementInputRequest"];
            subclaims?: components["schemas"]["SubclaimInputRequest"][];
            /** Format: uuid */
            active_subclaim_id?: string | null;
            return_context?: unknown;
        };
        TurnExpandInputRequest: {
            expected_revision: number;
            /** Format: uuid */
            request_id: string;
            scope: components["schemas"]["QueryScopeInputRequest"];
            question?: string;
        };
        TurnRetryInputRequest: {
            expected_revision: number;
            /** Format: uuid */
            request_id: string;
        };
        /**
         * @description * `public` - public
         * @enum {string}
         */
        VisibilityEnum: "public";
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
    catalog_admin_assets_outline_retrieve: {
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    catalog_admin_assets_outline_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OutlineCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["OutlineCommandRequest"];
                "multipart/form-data": components["schemas"]["OutlineCommandRequest"];
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
            202: {
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
    catalog_admin_content_placements_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                page_id: string;
                page_type: string;
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
                    "application/json": components["schemas"]["PlacementRead"];
                };
            };
        };
    };
    catalog_admin_content_placements_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                page_id: string;
                page_type: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlacementCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PlacementCommandRequest"];
                "multipart/form-data": components["schemas"]["PlacementCommandRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlacementRead"];
                };
            };
        };
    };
    catalog_admin_content_placements_history_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                page_id: string;
                page_type: string;
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
                    "application/json": components["schemas"]["PlacementHistoryPage"];
                };
            };
        };
    };
    catalog_admin_content_placements_sources_retrieve: {
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
                    "application/json": components["schemas"]["PlacementSourcesPage"];
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
    catalog_admin_editions_reader_rendition_update: {
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
                "application/json": components["schemas"]["ReaderRenditionPolicyInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ReaderRenditionPolicyInputRequest"];
                "multipart/form-data": components["schemas"]["ReaderRenditionPolicyInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReaderRenditionPolicyResult"];
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
    catalog_admin_outline_jobs_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OutlineJobCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["OutlineJobCommandRequest"];
                "multipart/form-data": components["schemas"]["OutlineJobCommandRequest"];
            };
        };
        responses: {
            202: {
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
    catalog_admin_outline_rebuilds_retrieve: {
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
    catalog_admin_outline_rebuilds_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OutlineBatchRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["OutlineBatchRequest"];
                "multipart/form-data": components["schemas"]["OutlineBatchRequest"];
            };
        };
        responses: {
            202: {
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
    catalog_editorial_assistance_list: {
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
                    "application/json": components["schemas"]["EditorialAssistancePage"];
                };
            };
        };
    };
    catalog_editorial_assistance_create: {
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
                "application/json": components["schemas"]["EditorialAssistanceInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EditorialAssistanceInputRequest"];
                "multipart/form-data": components["schemas"]["EditorialAssistanceInputRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EditorialAssistance"];
                };
            };
        };
    };
    catalog_editorial_assistance_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                issue_id: string;
                job_id: string;
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
                    "application/json": components["schemas"]["EditorialAssistance"];
                };
            };
        };
    };
    catalog_editorial_assistance_command: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                issue_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EditorialAssistanceCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EditorialAssistanceCommandRequest"];
                "multipart/form-data": components["schemas"]["EditorialAssistanceCommandRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EditorialAssistance"];
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
    catalog_assets_outline_retrieve: {
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
                    "application/json": {
                        [key: string]: unknown;
                    };
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
    catalog_assets_search_retrieve: {
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
                    "application/json": components["schemas"]["ReaderDocumentSearch"];
                };
            };
        };
    };
    catalog_content_placements_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                page_id: string;
                page_type: string;
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
                    "application/json": components["schemas"]["PlacementRead"];
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
    catalog_discovery_search_retry_create: {
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
        requestBody: {
            content: {
                "application/json": components["schemas"]["DiscoveryRetryRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["DiscoveryRetryRequest"];
                "multipart/form-data": components["schemas"]["DiscoveryRetryRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DiscoveryResponse"];
                };
            };
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
    catalog_home: {
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
                    "application/json": components["schemas"]["HomeResponse"];
                };
            };
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HomeResponse"];
                };
            };
        };
    };
    catalog_passages_focus_retrieve: {
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
                    "application/json": components["schemas"]["ReaderFocus"];
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
    catalog_theory_system_evidence_focus_retrieve: {
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
                    "application/json": components["schemas"]["ReaderFocus"];
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
    distribution_admin_assets_preview_retrieve: {
        parameters: {
            query?: {
                download?: "1" | "original" | "true";
            };
            header?: {
                /** @description One bytes range; unsupported or unsatisfiable ranges return 416. */
                Range?: string;
            };
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    "Accept-Ranges"?: string;
                    "Content-Length"?: number;
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": string;
                };
            };
            206: {
                headers: {
                    "Accept-Ranges"?: string;
                    "Content-Range"?: string;
                    "Content-Length"?: number;
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": string;
                };
            };
            /** @description No response body */
            416: {
                headers: {
                    "Accept-Ranges"?: string;
                    "Content-Range"?: string;
                    [name: string]: unknown;
                };
                content?: never;
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
    distribution_assets_file_retrieve: {
        parameters: {
            query?: {
                download?: "1" | "original" | "true";
            };
            header?: {
                /** @description One bytes range; unsupported or unsatisfiable ranges return 416. */
                Range?: string;
            };
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    "Accept-Ranges"?: string;
                    "Content-Length"?: number;
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": string;
                };
            };
            206: {
                headers: {
                    "Accept-Ranges"?: string;
                    "Content-Range"?: string;
                    "Content-Length"?: number;
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": string;
                };
            };
            /** @description No response body */
            416: {
                headers: {
                    "Accept-Ranges"?: string;
                    "Content-Range"?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    distribution_backups_list: {
        parameters: {
            query?: {
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
                    "application/json": components["schemas"]["PaginatedBackupJobList"];
                };
            };
        };
    };
    distribution_backups_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BackupJobRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["BackupJobRequest"];
                "multipart/form-data": components["schemas"]["BackupJobRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BackupJob"];
                };
            };
        };
    };
    reading_citation_audits_list: {
        parameters: {
            query?: {
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
                    "application/json": components["schemas"]["PaginatedPrivateRecordList"];
                };
            };
        };
    };
    reading_citation_audits_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["AuditCreateInputRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_citation_audits_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 citation audit 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_citation_audits_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 citation audit 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    reading_citation_audits_command_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 citation audit 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AuditCommandInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["AuditCommandInputRequest"];
                "multipart/form-data": components["schemas"]["AuditCommandInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_citation_audits_export_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 citation audit 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecordExport"];
                };
            };
        };
    };
    reading_citation_audits_ocr_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 citation audit 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["CitationOCROutput"];
                };
            };
        };
    };
    reading_citation_audits_original_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 citation audit 的 UUID 字符串。 */
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
                    "application/octet-stream": string;
                };
            };
        };
    };
    reading_citation_audits_capabilities_retrieve: {
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
                    "application/json": components["schemas"]["AuditCapabilitiesOutput"];
                };
            };
        };
    };
    reading_reading_plans_list: {
        parameters: {
            query?: {
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
                    "application/json": components["schemas"]["PaginatedPrivateRecordList"];
                };
            };
        };
    };
    reading_reading_plans_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlanCreateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PlanCreateInputRequest"];
                "multipart/form-data": components["schemas"]["PlanCreateInputRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_reading_plans_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 personal reading plan 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_reading_plans_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 personal reading plan 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    reading_reading_plans_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 personal reading plan 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedPlanUpdateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedPlanUpdateInputRequest"];
                "multipart/form-data": components["schemas"]["PatchedPlanUpdateInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_reading_plans_command_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 personal reading plan 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlanCommandInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PlanCommandInputRequest"];
                "multipart/form-data": components["schemas"]["PlanCommandInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_reading_plans_export_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 personal reading plan 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecordExport"];
                };
            };
        };
    };
    reading_research_account_retrieve: {
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
                    "application/json": components["schemas"]["ResearchAccountOutput"];
                };
            };
        };
    };
    reading_research_account_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedResearchPreferenceInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedResearchPreferenceInputRequest"];
                "multipart/form-data": components["schemas"]["PatchedResearchPreferenceInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResearchPreferenceInput"];
                };
            };
        };
    };
    reading_research_memories_list: {
        parameters: {
            query?: {
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
                    "application/json": components["schemas"]["PaginatedPrivateRecordList"];
                };
            };
        };
    };
    reading_research_memories_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MemoryCreateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MemoryCreateInputRequest"];
                "multipart/form-data": components["schemas"]["MemoryCreateInputRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_memories_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research memory 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_memories_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research memory 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    reading_research_memories_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research memory 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedMemoryUpdateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedMemoryUpdateInputRequest"];
                "multipart/form-data": components["schemas"]["PatchedMemoryUpdateInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_memories_export_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research memory 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecordExport"];
                };
            };
        };
    };
    reading_research_memories_search_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MemorySearchInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MemorySearchInputRequest"];
                "multipart/form-data": components["schemas"]["MemorySearchInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemorySearchOutput"];
                };
            };
        };
    };
    reading_research_projects_list: {
        parameters: {
            query?: {
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
                    "application/json": components["schemas"]["PaginatedPrivateRecordList"];
                };
            };
        };
    };
    reading_research_projects_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectCreateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ProjectCreateInputRequest"];
                "multipart/form-data": components["schemas"]["ProjectCreateInputRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_projects_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research project 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_projects_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research project 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No response body */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    reading_research_projects_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research project 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedProjectUpdateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedProjectUpdateInputRequest"];
                "multipart/form-data": components["schemas"]["PatchedProjectUpdateInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_projects_comparison_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research project 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ComparisonInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ComparisonInputRequest"];
                "multipart/form-data": components["schemas"]["ComparisonInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_projects_export_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research project 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecordExport"];
                };
            };
        };
    };
    reading_research_projects_selections_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research project 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SelectionInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["SelectionInputRequest"];
                "multipart/form-data": components["schemas"]["SelectionInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_projects_turns_list: {
        parameters: {
            query?: {
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                /** @description 搜索关键词。 */
                search?: string;
            };
            header?: never;
            path: {
                /** @description 标识此 research project 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PaginatedPrivateRecordList"];
                };
            };
        };
    };
    reading_research_projects_turns_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research project 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TurnCreateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TurnCreateInputRequest"];
                "multipart/form-data": components["schemas"]["TurnCreateInputRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_projects_import_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectImportInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ProjectImportInputRequest"];
                "multipart/form-data": components["schemas"]["ProjectImportInputRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_turns_list: {
        parameters: {
            query?: {
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
                    "application/json": components["schemas"]["PaginatedPrivateRecordList"];
                };
            };
        };
    };
    reading_research_turns_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research turn 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_turns_cancel_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research turn 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_turns_decision_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research turn 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnalysisDecisionInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["AnalysisDecisionInputRequest"];
                "multipart/form-data": components["schemas"]["AnalysisDecisionInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_turns_expand_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research turn 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TurnExpandInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TurnExpandInputRequest"];
                "multipart/form-data": components["schemas"]["TurnExpandInputRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_turns_export_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research turn 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivateRecordExport"];
                };
            };
        };
    };
    reading_research_turns_retry_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research turn 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TurnRetryInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["TurnRetryInputRequest"];
                "multipart/form-data": components["schemas"]["TurnRetryInputRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
    reading_research_turns_subclaims_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research turn 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SubclaimsInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["SubclaimsInputRequest"];
                "multipart/form-data": components["schemas"]["SubclaimsInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivateRecord"];
                };
            };
        };
    };
}

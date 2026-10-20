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
    "/api/catalog/admin/assets/{asset_id}/page-mapping/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_assets_page_mapping_retrieve"];
        put?: never;
        post: operations["catalog_admin_assets_page_mapping_create"];
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
    "/api/catalog/admin/editions/{edition_id}/files/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_editions_files_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/files/{asset_id}/adopt/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_editions_files_adopt_retrieve"];
        put?: never;
        post: operations["catalog_admin_editions_files_adopt_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/files/{asset_id}/content/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_editions_files_content_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/files/{asset_id}/generate-reader/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_editions_files_generate_reader_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/files/{asset_id}/prepare-public/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_editions_files_prepare_public_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/files/{asset_id}/rights/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch: operations["catalog_admin_editions_files_rights_partial_update"];
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/files/impact.csv": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_editions_files_impact.csv_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/editions/{edition_id}/files/requests/{request_key}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_editions_files_requests_retrieve"];
        put?: never;
        post?: never;
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
    "/api/catalog/admin/public-feedback/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_public_feedback_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/public-feedback/{feedback_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_public_feedback_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch: operations["catalog_admin_public_feedback_partial_update"];
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
    "/api/catalog/admin/works/{work_id}/editions/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_admin_works_editions_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/admin/works/{work_id}/files/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_admin_works_files_retrieve"];
        put?: never;
        post?: never;
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
    "/api/catalog/discovery-search/{session_id}/remove-document/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_discovery_search_remove_document_create"];
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
    "/api/catalog/feedback/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_feedback_create"];
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
    "/api/catalog/parallel/candidates/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["catalog_parallel_candidates_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/parallel/segments/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_parallel_segments_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/parallel/versions/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_parallel_versions_retrieve"];
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
    "/api/catalog/search/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description This endpoint preserves three response branches. scope=catalog (context omitted or global) returns CatalogSearchOutput. Other explicit non-global contexts, or context=global&envelope=1, return ScopedSearchOutput. Remaining requests return LegacyGlobalSearchOutput; omitting context also emits Deprecation and Warning headers. Catalog filters use repeated query parameters, AND across fields and OR within a field, on the same activated public edition. Parameter defaults and validation differ by branch; see each parameter description. */
        get: operations["catalog_search_retrieve"];
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
    "/api/catalog/theory-system/graph/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_theory_system_graph_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/theory-system/nodes/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_theory_system_nodes_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/theory-system/nodes/{slug}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_theory_system_nodes_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/theory-system/nodes/{slug}/citation/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_theory_system_nodes_citation_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/theory-system/overview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_theory_system_overview_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/theory-system/reading-paths/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_theory_system_reading_paths_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/theory-system/reading-paths/{slug}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_theory_system_reading_paths_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/theory-system/timeline/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_theory_system_timeline_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalog/theory-system/timeline/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description Stable event links reuse the public timeline's visibility and serializer. */
        get: operations["theory_system_timeline_detail"];
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
    "/api/distribution/assets/{asset_id}/ocr-status/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["distribution_assets_ocr_status_retrieve"];
        put?: never;
        post: operations["distribution_assets_ocr_status_create"];
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
    "/api/ingestion/ocr-workspace/{asset_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["ingestion_ocr_workspace_retrieve"];
        put?: never;
        post: operations["ingestion_ocr_workspace_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/annotations/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_annotations_list"];
        put?: never;
        post: operations["reading_annotations_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/annotations/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_annotations_retrieve"];
        put: operations["reading_annotations_update"];
        post?: never;
        delete: operations["reading_annotations_destroy"];
        options?: never;
        head?: never;
        patch: operations["reading_annotations_partial_update"];
        trace?: never;
    };
    "/api/reading/bookmarks/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_bookmarks_list"];
        put?: never;
        post: operations["reading_bookmarks_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/bookmarks/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_bookmarks_retrieve"];
        put: operations["reading_bookmarks_update"];
        post?: never;
        delete: operations["reading_bookmarks_destroy"];
        options?: never;
        head?: never;
        patch: operations["reading_bookmarks_partial_update"];
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
    "/api/reading/citation-audits/{id}/manuscript/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_manuscript_retrieve"];
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
    "/api/reading/citation-audits/{id}/preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_preview_retrieve"];
        put?: never;
        post: operations["reading_citation_audits_preview_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-audits/{id}/preview/file/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_preview_file_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-audits/{id}/versions/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_audits_versions_retrieve"];
        put?: never;
        post: operations["reading_citation_audits_versions_create"];
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
    "/api/reading/citation-preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_citation_preview_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-sources/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_sources_list"];
        put?: never;
        post: operations["reading_citation_sources_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-sources/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_sources_retrieve"];
        put?: never;
        post?: never;
        delete: operations["reading_citation_sources_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-sources/{id}/command/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_citation_sources_command_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-sources/{id}/export/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_sources_export_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-sources/{id}/ocr/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_sources_ocr_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-sources/{id}/original/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_sources_original_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-sources/{id}/preview/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_sources_preview_retrieve"];
        put?: never;
        post: operations["reading_citation_sources_preview_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-sources/{id}/preview/file/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_sources_preview_file_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/citation-sources/{id}/segments/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_citation_sources_segments_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/history/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_history_list"];
        put?: never;
        post: operations["reading_history_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_calibrations_list"];
        put?: never;
        post: operations["reading_parallel_calibrations_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_calibrations_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/admin/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_calibrations_admin_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/admin/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_calibrations_admin_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/admin/{id}/publish/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_parallel_calibrations_admin_publish_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/admin/{id}/reject/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_parallel_calibrations_admin_reject_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/admin/{id}/review/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_parallel_calibrations_admin_review_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/by-request/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_calibrations_by_request_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/public/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_calibrations_public_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-calibrations/public/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_calibrations_public_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-tasks/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_tasks_list"];
        put?: never;
        post: operations["reading_parallel_tasks_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/parallel-tasks/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_tasks_retrieve"];
        put?: never;
        post?: never;
        delete: operations["reading_parallel_tasks_destroy"];
        options?: never;
        head?: never;
        patch: operations["reading_parallel_tasks_partial_update"];
        trace?: never;
    };
    "/api/reading/parallel-tasks/by-request/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_parallel_tasks_by_request_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/privacy/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_privacy_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch: operations["reading_privacy_partial_update"];
        trace?: never;
    };
    "/api/reading/privacy/items/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_privacy_items_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/privacy/operations/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_privacy_operations_list"];
        put?: never;
        post: operations["reading_privacy_operations_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/privacy/operations/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_privacy_operations_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/privacy/operations/{id}/command/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["reading_privacy_operations_command_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/privacy/operations/{id}/download/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_privacy_operations_download_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/progress/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_progress_list"];
        put?: never;
        post: operations["reading_progress_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/progress/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_progress_retrieve"];
        put: operations["reading_progress_update"];
        post?: never;
        delete: operations["reading_progress_destroy"];
        options?: never;
        head?: never;
        patch: operations["reading_progress_partial_update"];
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
    "/api/reading/research-memories/{id}/usage/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_research_memories_usage_retrieve"];
        put?: never;
        post: operations["reading_research_memories_usage_create"];
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
    "/api/reading/saved-knowledge/{node_id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_saved_knowledge_retrieve"];
        put?: never;
        post: operations["reading_saved_knowledge_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/search-records/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_search_records_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/source-follows/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_source_follows_list"];
        put?: never;
        post: operations["reading_source_follows_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/source-follows/{id}/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_source_follows_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reading/source-status/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["reading_source_status_retrieve"];
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
        /**
         * @description * `alias` - 别名
         *     * `translation` - 译名
         *     * `abbreviation` - 简称
         *     * `historical` - 历史名称
         *     * `transliteration` - 音译
         * @enum {string}
         */
        AliasTypeEnum: "alias" | "translation" | "abbreviation" | "historical" | "transliteration";
        /**
         * @description * `confirm` - confirm
         *     * `clear` - clear
         * @enum {string}
         */
        AnalysisDecisionInputActionEnum: "confirm" | "clear";
        /**
         * @description * `support` - support
         *     * `different_conclusion` - different_conclusion
         *     * `qualification` - qualification
         *     * `reframe` - reframe
         *     * `insufficient_evidence` - insufficient_evidence
         *     * `unrelated` - unrelated
         * @enum {string}
         */
        AnalysisDecisionInputRelationEnum: "support" | "different_conclusion" | "qualification" | "reframe" | "insufficient_evidence" | "unrelated";
        AnalysisDecisionInputRequest: {
            expected_revision: number;
            /** @description 分析候选 id，来自轮次返回值。 */
            id: string;
            action?: components["schemas"]["AnalysisDecisionInputActionEnum"];
            /**
             * Format: uuid
             * @description 幂等请求；同时保存本人笔记时必需。
             */
            request_id?: string;
            relation?: components["schemas"]["AnalysisDecisionInputRelationEnum"];
            note?: string;
            attribution?: components["schemas"]["AttributionEnum"];
            scope_note?: string;
            save_as_note?: boolean;
        };
        Annotation: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            asset: string;
            readonly work: components["schemas"]["WorkCard"];
            /** Format: uuid */
            page: string;
            kind: components["schemas"]["AnnotationKindEnum"];
            selector?: unknown;
            quote?: string;
            readonly body_text: string | null;
            tags?: string[];
            color?: string;
            readonly asset_sha256: string;
            readonly orphaned: boolean;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
        };
        /**
         * @description * `highlight` - 高亮
         *     * `underline` - 划线
         *     * `note` - 笔记
         * @enum {string}
         */
        AnnotationKindEnum: "highlight" | "underline" | "note";
        AnnotationRequest: {
            /** Format: uuid */
            request_id?: string;
            /** Format: uuid */
            asset: string;
            /** Format: uuid */
            page: string;
            kind: components["schemas"]["AnnotationKindEnum"];
            selector?: unknown;
            quote?: string;
            body?: string;
            tags?: string[];
            color?: string;
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
        /**
         * @description * `author_claim` - author_claim
         *     * `quoted_claim` - quoted_claim
         *     * `reported_claim` - reported_claim
         *     * `criticized_claim` - criticized_claim
         *     * `historical_description` - historical_description
         *     * `uncertain` - uncertain
         * @enum {string}
         */
        AttributionEnum: "author_claim" | "quoted_claim" | "reported_claim" | "criticized_claim" | "historical_description" | "uncertain";
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
            readonly private_sources: unknown;
        };
        /**
         * @description * `cancel` - cancel
         *     * `match` - match
         *     * `match_private` - match_private
         *     * `sources` - sources
         *     * `link` - link
         *     * `decision` - decision
         *     * `analyze` - analyze
         *     * `retry` - retry
         * @enum {string}
         */
        AuditCommandInputActionEnum: "cancel" | "match" | "match_private" | "sources" | "link" | "decision" | "analyze" | "retry";
        AuditCommandInputRequest: {
            expected_revision: number;
            action: components["schemas"]["AuditCommandInputActionEnum"];
            /** Format: uuid */
            source_id?: string;
            private_source_ids?: string[];
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
            scope?: components["schemas"]["AuditCreateInputScopeEnum"];
            private_source_ids?: string[];
        };
        /**
         * @description * `public_library` - public_library
         *     * `private_materials` - private_materials
         * @enum {string}
         */
        AuditCreateInputScopeEnum: "public_library" | "private_materials";
        AuditVersionInputRequest: {
            expected_revision: number;
            /** Format: uuid */
            request_id: string;
            /**
             * Format: binary
             * @description 新版本 DOCX/PDF，最大 12 MiB；原稿与旧报告保持独立。
             */
            file: string;
            /**
             * @description 默认仅重查不能安全复用的引文；取消后检查全部引文。继承原检查项与明确选择的来源范围。
             * @default true
             */
            check_changed_only: boolean;
        };
        AuditVersionSummary: {
            /** Format: uuid */
            readonly id: string;
            readonly revision: number;
            readonly manuscript_revision: number;
            readonly filename: string;
            readonly status: string;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly finished_at: string | null;
            /** Format: uuid */
            readonly parent_audit_id: string | null;
        };
        AuditVersionsOutput: {
            /** Format: uuid */
            readonly current_id: string;
            readonly versions: components["schemas"]["AuditVersionSummary"][];
            readonly notice: string;
            readonly truncated: boolean;
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
        /**
         * @description * `database` - database
         * @enum {string}
         */
        BackendEnum: "database";
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
        Bookmark: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            asset: string;
            readonly work: components["schemas"]["WorkCard"];
            /** Format: uuid */
            page: string;
            readonly page_index: number;
            label?: string;
            /** Format: date-time */
            readonly created_at: string;
        };
        BookmarkRequest: {
            /** Format: uuid */
            asset: string;
            /** Format: uuid */
            page: string;
            label?: string;
        };
        /**
         * @description * `unverified` - unverified
         *     * `needs_review` - needs_review
         *     * `confirmed` - confirmed
         *     * `native` - native
         *     * `matched` - matched
         *     * `generated` - generated
         * @enum {string}
         */
        CalibrationStatusEnum: "unverified" | "needs_review" | "confirmed" | "native" | "matched" | "generated";
        CatalogCounts: {
            works: number;
            books: number;
            articles: number;
            theses: number;
            reports: number;
            scholars: number;
            topics: number;
            theories: number;
            passages: number;
        };
        CatalogEdition: {
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
            readonly language: string;
            readonly availability: string;
            readonly access_state: string;
        };
        CatalogFacet: {
            value: string;
            label: string;
            count: number;
        };
        CatalogFacets: {
            document_types: components["schemas"]["CatalogFacet"][];
            authors: components["schemas"]["CatalogFacet"][];
            years: components["schemas"]["CatalogFacet"][];
            languages: components["schemas"]["CatalogFacet"][];
            access: components["schemas"]["CatalogFacet"][];
            theories: components["schemas"]["CatalogFacet"][];
            topics: components["schemas"]["CatalogFacet"][];
            concepts: components["schemas"]["CatalogFacet"][];
            year_histogram: components["schemas"]["CatalogYearCount"][];
        };
        CatalogPagination: {
            page: number;
            page_size: number;
            total: number;
            total_pages: number;
        };
        CatalogSearchOutput: {
            context: components["schemas"]["GlobalSearchContextEnum"];
            query: string;
            scope: components["schemas"]["CatalogSearchOutputScopeEnum"];
            counts: components["schemas"]["CatalogCounts"];
            works: components["schemas"]["CatalogWork"][];
            facets: components["schemas"]["CatalogFacets"];
            pagination: components["schemas"]["CatalogPagination"];
            scholars: unknown[];
            topics: unknown[];
            theories: unknown[];
            passages: unknown[];
        };
        /**
         * @description * `catalog` - catalog
         * @enum {string}
         */
        CatalogSearchOutputScopeEnum: "catalog";
        CatalogWork: {
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
            readonly edition: components["schemas"]["CatalogEdition"] | null;
            readonly theories: components["schemas"]["PublicEntityLink"][];
            readonly topics: components["schemas"]["PublicEntityLink"][];
            readonly disciplines: components["schemas"]["PublicClassificationLink"][];
            readonly subdisciplines: components["schemas"]["PublicClassificationLink"][];
            readonly editions: components["schemas"]["CatalogEdition"][];
            readonly matched_edition_ids: string[];
        };
        CatalogYearCount: {
            year: number;
            count: number;
        };
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
         * @description * `research` - research
         *     * `notes` - notes
         *     * `plans` - plans
         *     * `audits` - audits
         *     * `source_follows` - source_follows
         *     * `saved_knowledge` - saved_knowledge
         * @enum {string}
         */
        CategoriesEnum: "research" | "notes" | "plans" | "audits" | "source_follows" | "saved_knowledge";
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
        /**
         * @description * `cancel` - cancel
         *     * `retry` - retry
         * @enum {string}
         */
        CitationSourceCommandActionEnum: "cancel" | "retry";
        CitationSourceCommandInputRequest: {
            expected_revision: number;
            action: components["schemas"]["CitationSourceCommandActionEnum"];
        };
        CitationSourceCreateInputRequest: {
            /** Format: uuid */
            request_id: string;
            /**
             * Format: binary
             * @description 本人私人来源 PDF/DOCX，最大 12 MiB，不进入公开馆藏或索引。
             */
            file: string;
            title?: string;
            citation?: string;
            /** @default false */
            scan_ocr: boolean;
        };
        CitationTextUnitsOutput: {
            /** Format: uuid */
            readonly audit_id: string;
            /** Format: uuid */
            readonly source_id: string;
            readonly manuscript_revision: number;
            readonly generation: number;
            readonly revision: number;
            readonly status: string;
            readonly count: number;
            readonly page: number;
            readonly next_page: number | null;
            readonly units: unknown;
            readonly notice: string;
        };
        CompactTheoryWork: {
            /** Format: uuid */
            id: string;
            slug: string;
            title: string;
            subtitle: string;
            document_type: string;
            language: string;
            author: string;
            year: number | null;
            publisher: string;
            cover_url: string;
            /** Format: uuid */
            edition_id?: string;
            /** Format: uuid */
            catalog_revision_id?: string;
            /** Format: uuid */
            document_revision_id?: string | null;
            source_status?: string;
            /** Format: uuid */
            asset_id: string | null;
            reader_href: string | null;
            detail_href: string | null;
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
        DisciplineCompact: {
            /** Format: uuid */
            readonly id: string;
            code: string;
            name: string;
            foreign_name?: string;
            slug: string;
            description?: string;
            /** Format: uri */
            hero_image?: string | null;
        };
        DiscoveryAttribution: {
            status: string;
            label: string;
            notice: string;
        };
        DiscoveryBibliography: {
            cover_url: string;
            original_title: string;
            publication_year: number | null;
            publisher: string;
            language: string;
            page_count: number | null;
            version_label: string;
            document_type: string;
        };
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
            source?: components["schemas"]["DiscoveryPassage"];
            same_work_count?: number;
            same_work_results?: components["schemas"]["DiscoveryPassage"][];
            /** Format: uuid */
            previous_result_id?: string | null;
            /** Format: uuid */
            next_result_id?: string | null;
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
            is_new?: boolean;
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
        DiscoveryDocument: {
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            work_id: string;
            status: components["schemas"]["DiscoveryDocumentStatusEnum"];
            title: string;
            authors: string[];
            bibliography: components["schemas"]["DiscoveryBibliography"] | null;
            material_count: number;
            available_versions: components["schemas"]["DiscoveryDocumentVersion"][];
            url: string;
        };
        /**
         * @description * `queued` - queued
         *     * `running` - running
         *     * `completed` - completed
         *     * `no_returned` - no_returned
         *     * `partial` - partial
         *     * `failed` - failed
         *     * `waiting_index` - waiting_index
         *     * `unreadable` - unreadable
         *     * `changed` - changed
         *     * `canceled` - canceled
         * @enum {string}
         */
        DiscoveryDocumentStatusEnum: "queued" | "running" | "completed" | "no_returned" | "partial" | "failed" | "waiting_index" | "unreadable" | "changed" | "canceled";
        DiscoveryDocumentVersion: {
            /** Format: uuid */
            id: string;
            label: string;
            url: string;
        };
        DiscoveryDocuments: {
            items: components["schemas"]["DiscoveryDocument"][];
            counts: {
                [key: string]: number;
            };
            tracked: number;
            excluded_count: number;
            truncated: boolean;
            notice: string;
        };
        DiscoveryEntity: {
            /** Format: uuid */
            id: string;
            is_new?: boolean;
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
            is_new?: boolean;
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
            bibliography?: components["schemas"]["DiscoveryBibliography"];
            section_title?: string;
            attribution?: components["schemas"]["DiscoveryAttribution"];
        };
        DiscoveryRemoveDocumentRequest: {
            expected_generation: number;
            /** Format: uuid */
            edition_id: string;
        };
        DiscoveryResponse: {
            /** Format: uuid */
            id: string;
            sort: components["schemas"]["SortEnum"];
            /** @description 本轮恢复或扩展后当前仍可访问的新增原文材料总数，包含未分页展示的结果。 */
            added_count: number;
            documents: components["schemas"]["DiscoveryDocuments"];
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
         * @description * `publish` - publish
         *     * `apply_draft` - apply_draft
         * @enum {string}
         */
        DocumentRevisionApplyModeEnum: "publish" | "apply_draft";
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
        /**
         * @description * `supplement` - supplement
         *     * `replace` - replace
         * @enum {string}
         */
        EditionFileInputActionEnum: "supplement" | "replace";
        EditionFileInputRequest: {
            action: components["schemas"]["EditionFileInputActionEnum"];
            /** Format: binary */
            file: string;
            /** Format: uuid */
            request_key: string;
            /** Format: date-time */
            expected_updated_at: string;
            /** Format: uuid */
            expected_reader_asset_id?: string | null;
            confirm: boolean;
            /** @default true */
            generate_reader: boolean;
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
        /**
         * @description * `tradition` - 理论传统
         *     * `school` - 流派
         *     * `branch` - 分支
         * @enum {string}
         */
        EntityLevelEnum: "tradition" | "school" | "branch";
        /**
         * @description * `scholar` - 学者
         *     * `publication` - 重要发表
         *     * `concept_proposed` - 理论概念提出
         *     * `school_formation` - 学派形成
         *     * `debate` - 争论
         *     * `institution` - 机构
         *     * `theoretical_turn` - 理论转向
         *     * `translation` - 重要译介
         *     * `china_reception` - 进入中国学界
         *     * `institutionalization` - 学科制度化
         *     * `formation` - 形成
         *     * `development` - 发展
         * @enum {string}
         */
        EventTypeEnum: "scholar" | "publication" | "concept_proposed" | "school_formation" | "debate" | "institution" | "theoretical_turn" | "translation" | "china_reception" | "institutionalization" | "formation" | "development";
        EvidenceAnchorInputRequest: {
            /** Format: uuid */
            evidence_span_id?: string;
            /** Format: uuid */
            asset_id?: string;
            /** Format: uuid */
            document_revision_id?: string;
            pdf_page?: number;
            content_hash?: string;
            selection_start?: number;
            selection_end?: number;
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
            selection_start?: number;
            selection_end?: number;
            /** @description 跨页引用按顺序传 1—20 个同文件同修订的单页锚点。 */
            anchors?: components["schemas"]["EvidenceAnchorInputRequest"][];
        };
        EvidenceSnippet: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            work: string;
            readonly work_title: string;
            /** Format: uuid */
            file: string;
            /** Format: uuid */
            node?: string | null;
            readonly node_name: string;
            /** Format: uuid */
            work_node_relation?: string | null;
            /** Format: uuid */
            knowledge_relation?: string | null;
            readonly relation_role: string;
            /** Format: int64 */
            page_number: number;
            /** Format: int64 */
            page_end?: number | null;
            printed_page_label?: string;
            quote: string;
            bounding_box?: unknown;
            extraction_method?: components["schemas"]["ExtractionMethodEnum"];
            /** Format: double */
            ocr_confidence?: number | null;
            /** Format: double */
            semantic_confidence?: number | null;
            review_status?: components["schemas"]["ReviewStatusEnum"];
            readonly reader_href: string;
            readonly document_revision_id: string | null;
        };
        /**
         * @description * `pdf` - pdf
         *     * `docx` - docx
         *     * `tiff` - tiff
         * @enum {string}
         */
        ExtensionEnum: "pdf" | "docx" | "tiff";
        /**
         * @description * `text_layer` - PDF 文本层
         *     * `ocr` - OCR
         *     * `manual` - 人工录入
         *     * `external` - 外部来源
         * @enum {string}
         */
        ExtractionMethodEnum: "text_layer" | "ocr" | "manual" | "external";
        FeedbackCounts: {
            total: number;
            submitted: number;
            reviewing: number;
            resolved: number;
        };
        FeedbackDetailOutput: {
            /** Format: uuid */
            id: string;
            category: components["schemas"]["PublicFeedbackCategoryEnum"];
            status: components["schemas"]["PublicFeedbackStatusEnum"];
            excerpt: string;
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            updated_at: string;
            revision: number;
            follow_up: boolean;
            body: string;
            contact: string;
            path: string;
            /** Format: date-time */
            consent_at: string | null;
            consent_version: string;
            note: string;
            handled_by: string;
            can_follow_up: boolean;
            history: components["schemas"]["FeedbackHistoryOutput"];
            source: components["schemas"]["FeedbackSourceOutput"];
        };
        FeedbackHandlingState: {
            status: components["schemas"]["PublicFeedbackStatusEnum"];
            note: string;
            follow_up: boolean;
            revision: number;
        };
        FeedbackHistoryEntry: {
            /** Format: uuid */
            id: string;
            /** Format: date-time */
            created_at: string;
            actor: string;
            before: components["schemas"]["FeedbackHandlingState"];
            after: components["schemas"]["FeedbackHandlingState"];
        };
        FeedbackHistoryOutput: {
            count: number;
            page: number;
            page_size: number;
            results: components["schemas"]["FeedbackHistoryEntry"][];
        };
        FeedbackListOutput: {
            count: number;
            page: number;
            page_size: number;
            counts: components["schemas"]["FeedbackCounts"];
            results: components["schemas"]["FeedbackSummary"][];
        };
        FeedbackSourceOutput: {
            status: components["schemas"]["PublicSourceAvailabilityEnum"];
            canonical_path: string;
            title: string;
            authors: string[];
            cover_url: string;
            source_type: string;
            version_label: string;
            location: string;
            /** Format: date-time */
            updated_at: string | null;
            /** Format: date-time */
            checked_at: string;
            reader_url: string;
            notice: string;
        };
        FeedbackSummary: {
            /** Format: uuid */
            id: string;
            category: components["schemas"]["PublicFeedbackCategoryEnum"];
            status: components["schemas"]["PublicFeedbackStatusEnum"];
            excerpt: string;
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            updated_at: string;
            revision: number;
            follow_up: boolean;
        };
        FeedbackUpdateOutput: {
            /** Format: uuid */
            request_id: string;
            accepted_revision: number;
            record: components["schemas"]["FeedbackDetailOutput"];
        };
        FileAdoptionInputRequest: {
            /** Format: uuid */
            request_key: string;
            fingerprint: string;
            confirm: boolean;
        };
        FileAdoptionPreviewOutput: {
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            target_asset_id: string;
            /** Format: uuid */
            current_reader_asset_id: string | null;
            /** Format: uuid */
            request_key: string;
            fingerprint: string;
            can_adopt: boolean;
            already_current: boolean;
            blocking: string[];
            impact: string[];
        };
        FileAdoptionResultOutput: {
            /** Format: uuid */
            request_key: string;
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            target_asset_id: string;
            event_id: string;
            status: string;
            command_accepted: boolean;
            effective: boolean;
            public_effective: boolean;
            publication_required: boolean;
            detail: string;
        };
        FileFormatCapabilityOutput: {
            extension: components["schemas"]["ExtensionEnum"];
            max_bytes: number;
            max_derived_bytes: number | null;
            available: boolean;
            can_generate_reader: boolean;
            service_verified: boolean;
            reason: string;
        };
        FileImpactOutput: {
            count: number;
            page: number;
            page_size: number;
            results: components["schemas"]["FileImpactRowOutput"][];
            summary: components["schemas"]["FileImpactSummaryOutput"];
            notice: string;
            export_url: string;
        };
        FileImpactRowOutput: {
            /** Format: uuid */
            id: string;
            kind: string;
            title: string;
            /** Format: uuid */
            asset_id: string;
            /** @description 1-based PDF page index. */
            file_page_index: number | null;
            printed_page_label: string;
            status: string;
            href: string;
        };
        FileImpactSummaryOutput: {
            catalog_evidence: number;
            reader_annotations: number;
            reader_bookmarks: number;
            reader_progress: number;
        };
        GenerateReaderInputRequest: {
            /** Format: uuid */
            request_key: string;
            /** Format: date-time */
            expected_asset_updated_at: string;
        };
        /**
         * @description * `global` - global
         * @enum {string}
         */
        GlobalSearchContextEnum: "global";
        GlobalSearchOutput: components["schemas"]["CatalogSearchOutput"] | components["schemas"]["LegacyGlobalSearchOutput"] | components["schemas"]["ScopedSearchOutput"];
        HomeResponse: {
            schema_version: string;
            visibility: components["schemas"]["HomeResponseVisibilityEnum"];
            status: components["schemas"]["PublicCollectionStateEnum"];
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
         * @description * `public` - public
         * @enum {string}
         */
        HomeResponseVisibilityEnum: "public";
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
        KnowledgeEntryCitation: {
            /** Format: uuid */
            node_id: string;
            title: string;
            url: string;
            /** Format: date-time */
            published_at: string | null;
            /** Format: date-time */
            updated_at: string;
            /** Format: date */
            accessed_on: string;
            text: string;
            notice: string;
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
        KnowledgeNodeAlias: {
            /** Format: uuid */
            readonly id: string;
            alias: string;
            language?: string;
            alias_type?: components["schemas"]["AliasTypeEnum"];
            readonly normalized_alias: string;
        };
        KnowledgeNodeDetail: {
            /** Format: uuid */
            readonly id: string;
            node_type: components["schemas"]["NodeTypeEnum"];
            canonical_name_zh: string;
            canonical_name_en?: string;
            slug: string;
            summary?: string;
            core_questions?: unknown;
            /** Format: int64 */
            start_year?: number | null;
            /** Format: int64 */
            end_year?: number | null;
            period_label?: string;
            readonly parent: string | null;
            readonly primary_discipline: components["schemas"]["DisciplineCompact"] | null;
            readonly related_disciplines: components["schemas"]["DisciplineCompact"][];
            status?: components["schemas"]["KnowledgePublicationStatusEnum"];
            /** Format: int64 */
            sort_order?: number;
            readonly aliases_count: number;
            readonly work_count: number;
            readonly relation_count: number;
            readonly representative_scholars: components["schemas"]["PersonNode"][];
            readonly cover_url: string;
            readonly cover_media: components["schemas"]["PublicCoverMedia"] | null;
            /** Format: date-time */
            readonly updated_at: string;
            readonly aliases: components["schemas"]["KnowledgeNodeAlias"][];
            readonly discipline_links: components["schemas"]["KnowledgeNodeDiscipline"][];
            readonly subdiscipline_links: components["schemas"]["KnowledgeNodeSubdiscipline"][];
            readonly topic_links: components["schemas"]["KnowledgeNodeTopic"][];
            definition: string;
            basic_propositions: unknown;
            theoretical_boundary: string;
            readonly direct_relations: components["schemas"]["KnowledgeRelation"][];
            readonly work_groups: components["schemas"]["TheoryWorkGroups"];
            readonly evidence: components["schemas"]["EvidenceSnippet"][];
            readonly curated_claims: {
                [key: string]: {
                    [key: string]: unknown;
                }[];
            };
            /** Format: date-time */
            published_at?: string | null;
        };
        KnowledgeNodeDiscipline: {
            /** Format: uuid */
            readonly id: string;
            readonly discipline: components["schemas"]["DisciplineCompact"];
            relation_type?: components["schemas"]["KnowledgeNodeDisciplineRelationTypeEnum"];
            discipline_specific_summary?: string;
            /** Format: int64 */
            sort_order?: number;
            status?: components["schemas"]["KnowledgePublicationStatusEnum"];
        };
        /**
         * @description * `primary` - 主要学科
         *     * `related` - 关联学科
         *     * `transferred` - 跨学科传播
         * @enum {string}
         */
        KnowledgeNodeDisciplineRelationTypeEnum: "primary" | "related" | "transferred";
        KnowledgeNodeList: {
            /** Format: uuid */
            readonly id: string;
            node_type: components["schemas"]["NodeTypeEnum"];
            canonical_name_zh: string;
            canonical_name_en?: string;
            slug: string;
            summary?: string;
            core_questions?: unknown;
            /** Format: int64 */
            start_year?: number | null;
            /** Format: int64 */
            end_year?: number | null;
            period_label?: string;
            readonly parent: string | null;
            readonly primary_discipline: components["schemas"]["DisciplineCompact"] | null;
            readonly related_disciplines: components["schemas"]["DisciplineCompact"][];
            status?: components["schemas"]["KnowledgePublicationStatusEnum"];
            /** Format: int64 */
            sort_order?: number;
            readonly aliases_count: number;
            readonly work_count: number;
            readonly relation_count: number;
            readonly representative_scholars: components["schemas"]["PersonNode"][];
            readonly cover_url: string;
            readonly cover_media: components["schemas"]["PublicCoverMedia"] | null;
            /** Format: date-time */
            readonly updated_at: string;
        };
        KnowledgeNodeSubdiscipline: {
            /** Format: uuid */
            readonly id: string;
            readonly subdiscipline: components["schemas"]["TheoryTaxonomyLink"];
            is_primary?: boolean;
            relation_role?: string;
            source?: string;
            /** Format: double */
            confidence?: number;
            /** Format: int64 */
            sort_order?: number;
            status?: components["schemas"]["KnowledgePublicationStatusEnum"];
        };
        KnowledgeNodeTopic: {
            /** Format: uuid */
            readonly id: string;
            readonly topic: components["schemas"]["TheoryTaxonomyLink"];
            relation_label?: string;
            source?: string;
            /** Format: double */
            confidence?: number;
            /** Format: int64 */
            sort_order?: number;
            status?: components["schemas"]["KnowledgePublicationStatusEnum"];
        };
        /**
         * @description * `draft` - 草稿
         *     * `pending` - 待审核
         *     * `published` - 已发布
         *     * `rejected` - 已拒绝
         *     * `archived` - 已归档
         * @enum {string}
         */
        KnowledgePublicationStatusEnum: "draft" | "pending" | "published" | "rejected" | "archived";
        KnowledgeRelation: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            source_node: string;
            readonly source_name: string;
            readonly source_slug: string;
            /** Format: uuid */
            target_node: string;
            readonly target_name: string;
            readonly target_slug: string;
            relation_type: components["schemas"]["KnowledgeRelationRelationTypeEnum"];
            readonly relation_label: string;
            direction?: components["schemas"]["KnowledgeRelationDirectionEnum"];
            description?: string;
            evidence_source?: string;
            readonly evidence: components["schemas"]["EvidenceSnippet"][];
            /** Format: double */
            confidence?: number;
            status?: components["schemas"]["KnowledgePublicationStatusEnum"];
            /** Format: date-time */
            readonly published_at: string | null;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
        };
        /**
         * @description * `directed` - 有方向
         *     * `undirected` - 无方向
         * @enum {string}
         */
        KnowledgeRelationDirectionEnum: "directed" | "undirected";
        /**
         * @description * `inherited_from` - 继承
         *     * `revises` - 修正
         *     * `extends` - 扩展
         *     * `criticizes` - 批判
         *     * `responds_to` - 回应
         *     * `competes_with` - 竞争
         *     * `synthesizes` - 综合
         *     * `branches_from` - 分化
         *     * `borrows_concept_from` - 概念借用
         *     * `transferred_to` - 跨学科传播
         *     * `influenced_by` - 受到影响
         *     * `overlaps_with` - 部分重叠
         * @enum {string}
         */
        KnowledgeRelationRelationTypeEnum: "inherited_from" | "revises" | "extends" | "criticizes" | "responds_to" | "competes_with" | "synthesizes" | "branches_from" | "borrows_concept_from" | "transferred_to" | "influenced_by" | "overlaps_with";
        KnowledgeSaveCommandRequest: {
            saved: boolean;
            /** Format: uuid */
            request_id: string;
            expected_version: string;
        };
        KnowledgeSaveNode: {
            /** Format: uuid */
            id: string;
            title: string;
            slug: string;
            node_type: string;
        };
        KnowledgeSaveOutput: {
            owner_id: string;
            /** Format: uuid */
            node_id: string;
            /** Format: uuid */
            record_id: string | null;
            saved: boolean;
            version: string;
            node: components["schemas"]["KnowledgeSaveNode"] | null;
            receipt: components["schemas"]["KnowledgeSaveReceiptOutput"] | null;
        };
        KnowledgeSaveReceiptOutput: {
            /** Format: uuid */
            request_id: string;
            applied_saved: boolean;
        };
        /**
         * @description * `ch` - ch
         *     * `en` - en
         *     * `chinese_cht` - chinese_cht
         * @enum {string}
         */
        LanguagesEnum: "ch" | "en" | "chinese_cht";
        LegacyGlobalFacets: {
            document_types: components["schemas"]["CatalogFacet"][];
            authors: components["schemas"]["CatalogFacet"][];
            years: components["schemas"]["CatalogFacet"][];
            languages: components["schemas"]["CatalogFacet"][];
            access: components["schemas"]["CatalogFacet"][];
            theories: components["schemas"]["CatalogFacet"][];
            topics: components["schemas"]["CatalogFacet"][];
            concepts: components["schemas"]["CatalogFacet"][];
        };
        LegacyGlobalPassage: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            work_id: string;
            edition_slug: string;
            /** Format: uuid */
            asset_id: string;
            title: string;
            page_index: number;
            printed_label: string;
            snippet: string;
            bbox: unknown;
            query: string;
        };
        LegacyGlobalSearchOutput: {
            context: components["schemas"]["GlobalSearchContextEnum"];
            query: string;
            counts: components["schemas"]["CatalogCounts"];
            facets: components["schemas"]["LegacyGlobalFacets"];
            pagination: components["schemas"]["CatalogPagination"];
            works: components["schemas"]["WorkCard"][];
            scholars: components["schemas"]["LegacySearchScholar"][];
            topics: components["schemas"]["LegacySearchTopic"][];
            theories: components["schemas"]["LegacySearchTheory"][];
            passages: components["schemas"]["LegacyGlobalPassage"][];
        };
        LegacySearchScholar: {
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
            readonly works: components["schemas"]["WorkCard"][];
            readonly curated: {
                [key: string]: unknown;
            };
            readonly curated_claims: {
                [key: string]: {
                    [key: string]: unknown;
                }[];
            };
            readonly knowledge_nodes: {
                [key: string]: unknown;
            }[];
        };
        LegacySearchTheory: {
            /** Format: uuid */
            readonly id: string;
            name: string;
            slug: string;
            description?: string;
            symbol?: string;
            foreign_name?: string;
            entity_level?: components["schemas"]["EntityLevelEnum"];
            formation_period?: string;
            core_questions?: unknown;
            key_themes?: unknown;
            /** Format: uri */
            hero_image?: string | null;
            readonly disciplines: {
                [key: string]: unknown;
            }[];
            readonly subdisciplines: {
                [key: string]: unknown;
            }[];
            readonly hierarchy: {
                [key: string]: {
                    [key: string]: unknown;
                }[];
            };
            readonly relations: {
                [key: string]: unknown;
            }[];
            readonly timeline: {
                [key: string]: unknown;
            }[];
            readonly work_count: number;
            readonly scholar_count: number;
            readonly curated: {
                [key: string]: unknown;
            };
        };
        LegacySearchTopic: {
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
            readonly disciplines: {
                [key: string]: unknown;
            }[];
            readonly subdisciplines: {
                [key: string]: unknown;
            }[];
            readonly linked_theories: {
                [key: string]: unknown;
            }[];
            readonly knowledge_nodes: {
                [key: string]: unknown;
            }[];
            readonly work_count: number;
            readonly curated: {
                [key: string]: unknown;
            };
            readonly curated_claims: {
                [key: string]: {
                    [key: string]: unknown;
                }[];
            };
        };
        LocalTheoryGraph: {
            /** Format: uuid */
            center: string | null;
            nodes: components["schemas"]["LocalTheoryGraphNode"][];
            edges: components["schemas"]["LocalTheoryGraphEdge"][];
            depth?: number;
            limit?: number;
            truncated: boolean;
        };
        LocalTheoryGraphEdge: {
            id: string;
            source: string;
            target: string;
            relation_type: string;
            relation_label: string;
            direction: string;
            description?: string;
            evidence_source?: string;
            evidence?: components["schemas"]["EvidenceSnippet"][];
        };
        LocalTheoryGraphNode: {
            id: string;
            kind: string;
            name: string;
            node_type?: string;
            foreign_name?: string;
            slug?: string;
            summary?: string;
            period_label?: string;
            is_center?: boolean;
            work?: components["schemas"]["CompactTheoryWork"] | null;
        };
        MappingAsset: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            work_id: string;
            title: string;
            authors: string[];
            edition_label: string;
            publication_year: number | null;
            document_type: string;
            page_count: number;
            sha256: string;
            status: string;
            validation_status: string;
            is_current: boolean;
            source_current: boolean;
            source_error: string;
            original_filename: string;
            document_revision_id: string;
            preview_url: string;
            reader_url: string;
            cover_url: string;
            publication_state: string;
        };
        MappingChange: {
            pdf_page: number;
            before: string[];
            after: string[];
            page_type_before: string;
            page_type_after: string;
            note: string;
            manual_before: boolean;
        };
        /**
         * @description * `save` - save
         *     * `analyze` - analyze
         *     * `segment` - segment
         *     * `restore` - restore
         *     * `prepare` - prepare
         *     * `publish` - publish
         * @enum {string}
         */
        MappingCommandActionEnum: "save" | "analyze" | "segment" | "restore" | "prepare" | "publish";
        MappingCommandRequest: {
            action: components["schemas"]["MappingCommandActionEnum"];
            /** Format: uuid */
            request_id?: string;
            expected_revision: number;
            source_fingerprint: string;
            data?: components["schemas"]["MappingDataRequest"];
            segment?: components["schemas"]["MappingSegmentRequest"];
            /** Format: uuid */
            revision_id?: string;
            prepared_fingerprint?: string;
        };
        MappingCommandResponse: components["schemas"]["MappingState"] | components["schemas"]["MappingPreview"];
        MappingData: {
            pages: components["schemas"]["MappingPage"][];
            segments: components["schemas"]["MappingSegment"][];
            missing: components["schemas"]["MappingMissing"][];
        };
        MappingDataRequest: {
            pages: components["schemas"]["MappingPageRequest"][];
            segments: components["schemas"]["MappingSegmentRequest"][];
            missing: components["schemas"]["MappingMissingRequest"][];
        };
        MappingDiagnostics: {
            unconfirmed_pages: number[];
            duplicate_labels: components["schemas"]["MappingDuplicate"][];
            spreads: number[];
            unconfirmed_missing: string[];
            missing_present: string[];
        };
        MappingDuplicate: {
            label: string;
            pdf_pages: number[];
            acknowledged: boolean;
        };
        MappingMissing: {
            id: string;
            label: string;
            after_pdf_page: number;
            /** @default  */
            note: string;
            /** @default false */
            confirmed: boolean;
        };
        MappingMissingRequest: {
            id: string;
            label: string;
            after_pdf_page: number;
            /** @default  */
            note: string;
            /** @default false */
            confirmed: boolean;
        };
        MappingPage: {
            pdf_page: number;
            labels: string[];
            page_type: components["schemas"]["PageTypeEnum"];
            /** @default false */
            confirmed: boolean;
            /** @default  */
            note: string;
            /** @default false */
            override_manual: boolean;
            source?: components["schemas"]["SourceEnum"];
            /** Format: double */
            confidence?: number;
        };
        MappingPageRequest: {
            pdf_page: number;
            labels: string[];
            page_type: components["schemas"]["PageTypeEnum"];
            /** @default false */
            confirmed: boolean;
            /** @default  */
            note: string;
            /** @default false */
            override_manual: boolean;
            source?: components["schemas"]["SourceEnum"];
            /** Format: double */
            confidence?: number;
        };
        MappingPrecedingRevision: {
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            revision_id: string;
            revision: number;
        };
        MappingPreview: {
            /** Format: uuid */
            revision_id: string;
            source_fingerprint: string;
            prepared_fingerprint: string;
            changes: components["schemas"]["MappingChange"][];
            changed_page_count: number;
            missing_before: components["schemas"]["MappingMissing"][];
            missing_after: components["schemas"]["MappingMissing"][];
            segments_before: components["schemas"]["MappingSegment"][];
            segments_after: components["schemas"]["MappingSegment"][];
            diagnostics: components["schemas"]["MappingDiagnostics"];
            blockers: string[];
            can_apply: boolean;
            mode: components["schemas"]["DocumentRevisionApplyModeEnum"];
        };
        MappingPublication: {
            /** Format: uuid */
            event_id: string;
            status: string;
            /** Format: uuid */
            revision_id: string;
            revision_status: string;
            error: string;
        };
        MappingReadResponse: components["schemas"]["MappingState"] | components["schemas"]["MappingRevision"];
        MappingRevision: {
            /** Format: uuid */
            id: string;
            revision: number;
            origin: string;
            /** Format: date-time */
            created_at: string;
            created_by_id: number | null;
            /** Format: uuid */
            restored_from_id: string | null;
            source_fingerprint: string;
            /** Format: date-time */
            applied_at: string | null;
            /** Format: uuid */
            applied_asset_id: string | null;
            publication: components["schemas"]["MappingPublication"] | null;
            data?: components["schemas"]["MappingData"];
            diagnostics?: components["schemas"]["MappingDiagnostics"];
        };
        MappingSegment: {
            id: string;
            name: string;
            start: number;
            end: number;
            start_label: string;
            style: components["schemas"]["MappingSegmentStyleEnum"];
        };
        MappingSegmentRequest: {
            id: string;
            name: string;
            start: number;
            end: number;
            start_label: string;
            style: components["schemas"]["MappingSegmentStyleEnum"];
        };
        /**
         * @description * `arabic` - arabic
         *     * `roman_lower` - roman_lower
         *     * `roman_upper` - roman_upper
         *     * `custom` - custom
         *     * `none` - none
         * @enum {string}
         */
        MappingSegmentStyleEnum: "arabic" | "roman_lower" | "roman_upper" | "custom" | "none";
        MappingState: {
            asset: components["schemas"]["MappingAsset"];
            /** Format: uuid */
            asset_id: string;
            expected_revision: number;
            source_fingerprint: string;
            current: components["schemas"]["MappingData"];
            latest: components["schemas"]["MappingRevision"] | null;
            history: components["schemas"]["MappingRevision"][];
            history_count: number;
            history_page: number;
            history_next_page: number | null;
            preceding_revision: components["schemas"]["MappingPrecedingRevision"] | null;
            result?: components["schemas"]["MappingRevision"];
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
        MemoryContextInputRequest: {
            kind: components["schemas"]["ResearchMemoryContextKindEnum"];
            /** Format: uuid */
            id: string;
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
        MemoryListOutput: {
            readonly count: number;
            /** Format: uri */
            readonly next: string | null;
            /** Format: uri */
            readonly previous: string | null;
            readonly results: components["schemas"]["PrivateRecord"][];
            /** @description q/kind/source_status 范围内、state 过滤前的 total/confirmed/proposed/ignored 真实总数。 */
            readonly counts: {
                [key: string]: number;
            };
        };
        MemorySearchInputRequest: {
            q: string;
            /** @default false */
            semantic: boolean;
            allowed_ids?: string[];
            /** @description 仅从此本人研究或计划的显式授权范围中检索。 */
            context?: components["schemas"]["MemoryContextInputRequest"];
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
        MemoryUsageInputRequest: {
            expected_revision: number;
            action: components["schemas"]["ResearchMemoryUsageActionEnum"];
            targets?: components["schemas"]["MemoryUsageTargetInputRequest"][];
        };
        MemoryUsageTargetInputRequest: {
            kind: components["schemas"]["ResearchMemoryContextKindEnum"];
            /** Format: uuid */
            id: string;
            expected_revision: number;
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
        NewWorkEditionInputRequest: {
            /** Format: uuid */
            request_key: string;
            /** Format: date-time */
            expected_work_updated_at: string;
            version_label: string;
            publication_year?: number | null;
            publisher?: string;
        };
        NewWorkEditionOutput: {
            created: boolean;
            /** Format: uuid */
            work_id: string;
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            request_key: string;
            workbench_url: string;
        };
        /**
         * @description * `discipline` - 学科
         *     * `theory_tradition` - 理论传统
         *     * `subdiscipline` - 子学科
         *     * `concept` - 核心概念
         *     * `debate` - 理论争论
         *     * `research_problem` - 研究问题
         *     * `topic` - 主题
         * @enum {string}
         */
        NodeTypeEnum: "discipline" | "theory_tradition" | "subdiscipline" | "concept" | "debate" | "research_problem" | "topic";
        NormalizedTimelineEvent: {
            /** Format: uuid */
            readonly id: string;
            title: string;
            description?: string;
            event_type: components["schemas"]["EventTypeEnum"];
            /** Format: int64 */
            start_year?: number | null;
            /** Format: int64 */
            end_year?: number | null;
            date_label?: string;
            source?: string;
            /** Format: int64 */
            evidence_page?: number | null;
            evidence_printed_label?: string;
            evidence_text?: string;
            readonly relations: components["schemas"]["TheoryTimelineTarget"][];
            readonly reader_href: string | null;
        };
        /**
         * @description * `save` - save
         *     * `prepare` - prepare
         *     * `apply` - apply
         *     * `start` - start
         *     * `pause` - pause
         *     * `resume` - resume
         *     * `cancel` - cancel
         *     * `review` - review
         * @enum {string}
         */
        OCRCommandActionEnum: "save" | "prepare" | "apply" | "start" | "pause" | "resume" | "cancel" | "review";
        OCRCommandRequest: {
            action: components["schemas"]["OCRCommandActionEnum"];
            /** Format: uuid */
            request_id?: string;
            pdf_page?: number;
            expected_revision?: number;
            source_fingerprint?: string;
            text?: string;
            /** @default  */
            note: string;
            confirmed?: boolean;
            /** Format: uuid */
            revision_id?: string;
            prepared_fingerprint?: string;
            page_indexes?: number[];
            source_version?: string;
            /** Format: uuid */
            job_id?: string;
            job_version?: string;
            task_options?: components["schemas"]["OCRTaskOptionsRequest"];
            pages?: components["schemas"]["OCRReviewPageRequest"][];
        };
        OCRCorrection: {
            /** Format: uuid */
            id: string;
            revision: number;
            pdf_page: number;
            text: string;
            original_text: string;
            note: string;
            confirmed: boolean;
            review_only: boolean;
            source_fingerprint: string;
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            applied_at: string | null;
            /** Format: uuid */
            applied_asset_id: string | null;
            publication: {
                [key: string]: unknown;
            } | null;
        };
        OCRCorrectionPreview: {
            /** Format: uuid */
            revision_id: string;
            pdf_page: number;
            before: string;
            after: string;
            blockers: string[];
            can_apply: boolean;
            mode: components["schemas"]["DocumentRevisionApplyModeEnum"];
            notice: string;
            prepared_fingerprint: string;
        };
        OCRPage: {
            pdf_page: number;
            printed_label: string;
            text_source: string;
            /** Format: double */
            confidence: number;
            is_text_manual: boolean;
            char_count: number;
            status: string;
            reason: string;
            source_fingerprint: string;
            reviewed: boolean;
            /** Format: double */
            width: number;
            /** Format: double */
            height: number;
            replacement_character: boolean;
        };
        OCRPageDetail: {
            pdf_page: number;
            text: string;
            original_text: string;
            parsed: boolean;
            manual: boolean;
            /** Format: uuid */
            manual_revision_id: string | null;
            manual_revision: components["schemas"]["OCRCorrection"] | null;
            latest: components["schemas"]["OCRCorrection"] | null;
            source_fingerprint: string;
            history: components["schemas"]["OCRCorrection"][];
            history_count: number;
            history_page: number;
            history_next_page: number | null;
        };
        OCRReviewPageRequest: {
            pdf_page: number;
            source_fingerprint: string;
        };
        OCRTaskOptionsRequest: {
            languages: components["schemas"]["LanguagesEnum"][];
            layout: boolean;
            /** Format: double */
            quality_threshold: number;
            detect_spreads: boolean;
            detect_garbled: boolean;
            skip_reviewed: boolean;
        };
        OCRWorkspace: {
            asset: components["schemas"]["MappingAsset"];
            source_version: string;
            expected_revision: number;
            pages: components["schemas"]["OCRPage"][];
            count: number;
            list_page: number;
            next_page: number | null;
            counts: {
                [key: string]: number;
            };
            parsed_page_count: number;
            missing_page_count: number;
            detail: components["schemas"]["OCRPageDetail"];
            jobs: {
                [key: string]: unknown;
            }[];
            active_job_id: string;
            paused: boolean;
            can_run: boolean;
            denied_reason: string;
            provider_label: string;
            /** Format: date-time */
            checked_at: string;
            settings: {
                [key: string]: unknown;
            };
            result?: components["schemas"]["OCRCorrection"];
        };
        OCRWorkspaceCommandResult: components["schemas"]["OCRWorkspace"] | components["schemas"]["OCRCorrectionPreview"];
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
            base_revision_id?: string | null;
            /** Format: uuid */
            request_id?: string;
            nodes?: components["schemas"]["OutlineNodeRequest"][];
        };
        OutlineJobCommandRequest: {
            action: components["schemas"]["CitationSourceCommandActionEnum"];
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
            clear_position?: boolean;
            calibration_status?: components["schemas"]["CalibrationStatusEnum"];
        };
        /**
         * @description * `front` - front
         *     * `body` - body
         *     * `appendix` - appendix
         *     * `other` - other
         *     * `blank` - blank
         * @enum {string}
         */
        PageTypeEnum: "front" | "body" | "appendix" | "other" | "blank";
        PaginatedAnnotationList: {
            /** @example 123 */
            count: number;
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?p=4
             */
            next?: string | null;
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?p=2
             */
            previous?: string | null;
            results: components["schemas"]["Annotation"][];
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
        PaginatedBookmarkList: {
            /** @example 123 */
            count: number;
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?p=4
             */
            next?: string | null;
            /**
             * Format: uri
             * @example http://api.example.org/accounts/?p=2
             */
            previous?: string | null;
            results: components["schemas"]["Bookmark"][];
        };
        PaginatedKnowledgeNodeListList: {
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
            results: components["schemas"]["KnowledgeNodeList"][];
        };
        PaginatedMemoryListOutputList: {
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
            results: components["schemas"]["MemoryListOutput"][];
        };
        PaginatedNormalizedTimelineEventList: {
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
            results: components["schemas"]["NormalizedTimelineEvent"][];
        };
        PaginatedParallelCalibrationPageOutputList: {
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
            results: components["schemas"]["ParallelCalibrationPageOutput"][];
        };
        PaginatedParallelTaskPageOutputList: {
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
            results: components["schemas"]["ParallelTaskPageOutput"][];
        };
        PaginatedPrivacyOperationsPageList: {
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
            results: components["schemas"]["PrivacyOperationsPage"][];
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
        PaginatedPublicParallelCalibrationPageOutputList: {
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
            results: components["schemas"]["PublicParallelCalibrationPageOutput"][];
        };
        PaginatedReadingHistoryList: {
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
            results: components["schemas"]["ReadingHistory"][];
        };
        PaginatedReadingPathList: {
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
            results: components["schemas"]["ReadingPath"][];
        };
        PaginatedReadingProgressList: {
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
            results: components["schemas"]["ReadingProgress"][];
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
        ParallelAlignmentInputRequest: {
            /** Format: uuid */
            id: string;
            left?: components["schemas"]["ParallelReferenceInputRequest"] | null;
            right?: components["schemas"]["ParallelReferenceInputRequest"] | null;
            status: components["schemas"]["ParallelAlignmentStatusEnum"];
            /** @default  */
            note: string;
        };
        ParallelAlignmentOutput: {
            /** Format: uuid */
            id: string;
            left: components["schemas"]["ParallelStoredReferenceOutput"] | null;
            right: components["schemas"]["ParallelStoredReferenceOutput"] | null;
            status: components["schemas"]["ParallelAlignmentStatusEnum"];
            note?: string;
        };
        /**
         * @description * `confirmed` - confirmed
         *     * `no_match` - no_match
         *     * `addition` - addition
         * @enum {string}
         */
        ParallelAlignmentStatusEnum: "confirmed" | "no_match" | "addition";
        ParallelCalibrationCreateInputRequest: {
            /** Format: uuid */
            request_id: string;
            /** Format: uuid */
            task_id: string;
            expected_revision: number;
            /** Format: uuid */
            alignment_id?: string;
            scope: components["schemas"]["ParallelCalibrationScopeEnum"];
            basis: string;
        };
        ParallelCalibrationDataOutput: {
            /** Format: uuid */
            left_asset_id: string;
            /** Format: uuid */
            right_asset_id: string;
            /** Format: uuid */
            left_document_revision_id: string;
            /** Format: uuid */
            right_document_revision_id: string;
            basis: string;
            alignments: components["schemas"]["ParallelAlignmentOutput"][];
        };
        ParallelCalibrationOutput: {
            /** Format: uuid */
            readonly id: string;
            readonly revision: number;
            /** Format: uuid */
            readonly request_id: string;
            readonly applied_revision: number;
            readonly data: components["schemas"]["ParallelCalibrationDataOutput"];
            readonly source_available: boolean;
            readonly pair_sources: components["schemas"]["ParallelPairSourcesOutput"] | null;
            readonly notice: string;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
            readonly status: components["schemas"]["ParallelCalibrationOutputStatusEnum"];
            readonly scope: components["schemas"]["ParallelCalibrationScopeEnum"];
            readonly review_note: string;
            readonly reviewer_id: number | null;
        };
        /**
         * @description * `submitted` - submitted
         *     * `reviewed` - reviewed
         *     * `published` - published
         *     * `rejected` - rejected
         * @enum {string}
         */
        ParallelCalibrationOutputStatusEnum: "submitted" | "reviewed" | "published" | "rejected";
        ParallelCalibrationPageOutput: {
            count: number;
            next: string | null;
            previous: string | null;
            results: components["schemas"]["ParallelCalibrationOutput"][];
        };
        /**
         * @description * `bibliography` - bibliography
         *     * `passages` - passages
         * @enum {string}
         */
        ParallelCalibrationScopeEnum: "bibliography" | "passages";
        ParallelCandidateOutput: {
            reference: components["schemas"]["ParallelReferenceOutput"];
            label: string;
            text: string;
            status: components["schemas"]["ParallelCandidateOutputStatusEnum"];
            text_truncated: boolean;
        };
        /**
         * @description * `pending` - pending
         * @enum {string}
         */
        ParallelCandidateOutputStatusEnum: "pending";
        ParallelCandidatesInputRequest: {
            left_reference: components["schemas"]["ParallelReferenceInputRequest"];
            /** Format: uuid */
            target_asset_id: string;
            /** Format: uuid */
            target_document_revision_id: string;
        };
        ParallelCandidatesOutput: {
            state: components["schemas"]["PublicCollectionStateEnum"];
            notice: string;
            candidates: components["schemas"]["ParallelCandidateOutput"][];
            warnings: components["schemas"]["ParallelWarning"][];
            allows_no_correspondence: boolean;
        };
        ParallelPairSourcesOutput: {
            left: components["schemas"]["ParallelSourceSummaryOutput"];
            right: components["schemas"]["ParallelSourceSummaryOutput"];
        };
        ParallelPositionInput: {
            /** @default 1 */
            left_page: number;
            /** @default 1 */
            right_page: number;
            left_segment_id?: string | null;
            right_segment_id?: string | null;
        };
        ParallelPositionInputRequest: {
            /** @default 1 */
            left_page: number;
            /** @default 1 */
            right_page: number;
            left_segment_id?: string | null;
            right_segment_id?: string | null;
        };
        ParallelReferenceInputRequest: {
            /** Format: uuid */
            evidence_span_id?: string | null;
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            document_revision_id: string;
            pdf_page: number;
            content_hash: string;
            selection_start?: number;
            selection_end?: number;
            /** @description 跨页引用按顺序传 1—20 个同文件同修订的单页锚点。 */
            anchors?: components["schemas"]["EvidenceAnchorInputRequest"][];
            /** Format: uuid */
            work_id?: string;
            /** Format: uuid */
            edition_id?: string;
        };
        ParallelReferenceOutput: {
            reference_id: string;
            source_status: components["schemas"]["SourceStatusEnum"];
            /** Format: uuid */
            work_id: string;
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            document_revision_id: string;
            /** Format: uuid */
            evidence_span_id?: string | null;
            pdf_page: number;
            content_hash: string;
            printed_label: string;
            title: string;
            authors: string[];
            quote: string;
            reader_url: string | null;
            locator_precision: string;
            selection_start?: number;
            selection_end?: number;
            page_text_range?: unknown;
            anchors?: unknown[];
        };
        ParallelReviewInputRequest: {
            /** Format: uuid */
            request_id: string;
            expected_revision: number;
            /** @default  */
            note: string;
        };
        ParallelSegmentOutput: {
            id: string;
            label: string;
            order: number;
            reference: components["schemas"]["ParallelReferenceOutput"];
            printed_label: string;
            text: string;
            text_truncated: boolean;
        };
        ParallelSegmentsOutput: {
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            document_revision_id: string | null;
            page: number;
            total_pages: number;
            previous_page: number | null;
            next_page: number | null;
            state: components["schemas"]["ParallelSegmentsOutputStateEnum"];
            notice: string;
            segments: components["schemas"]["ParallelSegmentOutput"][];
            offset: number;
            has_more: boolean;
            next_offset: number | null;
        };
        /**
         * @description * `ready` - ready
         *     * `unstructured` - unstructured
         *     * `empty` - empty
         *     * `text_unavailable` - text_unavailable
         * @enum {string}
         */
        ParallelSegmentsOutputStateEnum: "ready" | "unstructured" | "empty" | "text_unavailable";
        ParallelSourceSummaryOutput: {
            title: string;
            version_label: string;
            authors: string[];
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            document_revision_id: string;
            reader_url: string;
        };
        ParallelStoredReferenceOutput: {
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            document_revision_id: string;
            pdf_page: number;
            content_hash: string;
            /** Format: uuid */
            evidence_span_id?: string | null;
            /** Format: uuid */
            work_id?: string;
            /** Format: uuid */
            edition_id?: string;
            reference_id: string;
            source_status: components["schemas"]["SourceStatusEnum"];
            quote: string;
            reader_url: string | null;
            title?: string;
            authors?: string[];
            printed_label?: string;
            selection_start?: number;
            selection_end?: number;
            anchors?: unknown[];
        };
        ParallelTaskCreateInputRequest: {
            /** Format: uuid */
            request_id: string;
            data: components["schemas"]["ParallelTaskDataInputRequest"];
        };
        ParallelTaskDataInputRequest: {
            /** Format: uuid */
            left_asset_id: string;
            /** Format: uuid */
            right_asset_id: string;
            /** Format: uuid */
            left_document_revision_id: string;
            /** Format: uuid */
            right_document_revision_id: string;
            positions?: components["schemas"]["ParallelPositionInputRequest"];
            /** @default true */
            sync_scroll: boolean;
            alignments?: components["schemas"]["ParallelAlignmentInputRequest"][];
            terms?: components["schemas"]["ParallelTermInputRequest"][];
        };
        ParallelTaskDataOutput: {
            /** Format: uuid */
            left_asset_id: string;
            /** Format: uuid */
            right_asset_id: string;
            /** Format: uuid */
            left_document_revision_id: string;
            /** Format: uuid */
            right_document_revision_id: string;
            positions: components["schemas"]["ParallelPositionInput"];
            sync_scroll: boolean;
            alignments: components["schemas"]["ParallelAlignmentOutput"][];
            terms: components["schemas"]["ParallelTermOutput"][];
        };
        ParallelTaskOutput: {
            /** Format: uuid */
            readonly id: string;
            readonly revision: number;
            /** Format: uuid */
            readonly request_id: string;
            readonly applied_revision: number;
            readonly data: components["schemas"]["ParallelTaskDataOutput"];
            readonly source_available: boolean;
            readonly pair_sources: components["schemas"]["ParallelPairSourcesOutput"] | null;
            readonly notice: string;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
        };
        ParallelTaskPageOutput: {
            count: number;
            next: string | null;
            previous: string | null;
            results: components["schemas"]["ParallelTaskOutput"][];
        };
        ParallelTermInputRequest: {
            /** Format: uuid */
            id: string;
            original: string;
            /** @default  */
            translation: string;
            /** @default  */
            note: string;
            left?: components["schemas"]["ParallelReferenceInputRequest"] | null;
            right?: components["schemas"]["ParallelReferenceInputRequest"] | null;
        };
        ParallelTermOutput: {
            /** Format: uuid */
            id: string;
            original: string;
            translation: string;
            note: string;
            left: components["schemas"]["ParallelStoredReferenceOutput"] | null;
            right: components["schemas"]["ParallelStoredReferenceOutput"] | null;
        };
        ParallelVersionOutput: {
            /** Format: uuid */
            work_id: string;
            /** Format: uuid */
            edition_id: string;
            /** Format: uuid */
            asset_id: string | null;
            /** Format: uuid */
            document_revision_id: string | null;
            title: string;
            original_title: string;
            authors: string[];
            language: string;
            publication_year: number | null;
            version_label: string;
            publisher: string;
            cover_url: string | null;
            total_pages: number;
            relation: components["schemas"]["ParallelVersionOutputRelationEnum"];
            current: boolean;
            state: components["schemas"]["ParallelVersionOutputStateEnum"];
            notice: string;
        };
        /**
         * @description * `same_work` - same_work
         *     * `translation` - translation
         * @enum {string}
         */
        ParallelVersionOutputRelationEnum: "same_work" | "translation";
        /**
         * @description * `available` - available
         *     * `metadata_only` - metadata_only
         * @enum {string}
         */
        ParallelVersionOutputStateEnum: "available" | "metadata_only";
        ParallelVersionsOutput: {
            /** Format: uuid */
            source_asset_id: string;
            versions: components["schemas"]["ParallelVersionOutput"][];
            truncated: boolean;
        };
        ParallelWarning: {
            code: string;
            message: string;
        };
        PatchedAnnotationRequest: {
            /** Format: uuid */
            request_id?: string;
            /** Format: uuid */
            asset?: string;
            /** Format: uuid */
            page?: string;
            kind?: components["schemas"]["AnnotationKindEnum"];
            selector?: unknown;
            quote?: string;
            body?: string;
            tags?: string[];
            color?: string;
        };
        PatchedBookmarkRequest: {
            /** Format: uuid */
            asset?: string;
            /** Format: uuid */
            page?: string;
            label?: string;
        };
        PatchedFeedbackUpdateInputRequest: {
            /** Format: uuid */
            request_id?: string;
            expected_revision?: number;
            status?: components["schemas"]["PublicFeedbackStatusEnum"];
            note?: string;
            follow_up?: boolean;
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
            kind?: components["schemas"]["ResearchMemoryKindEnum"];
            sources?: components["schemas"]["EvidenceReferenceInputRequest"][];
            state?: components["schemas"]["MemoryUpdateInputStateEnum"];
            /** @description 本人已对照当前原笔记后明确更新来源身份；不修改原笔记。 */
            refresh_origin?: boolean;
        };
        PatchedParallelTaskUpdateInputRequest: {
            /** Format: uuid */
            request_id?: string;
            data?: components["schemas"]["ParallelTaskDataInputRequest"];
            expected_revision?: number;
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
        PatchedPrivacyPreferencesInputRequest: {
            expected_revision?: number;
            retention?: {
                [key: string]: boolean;
            };
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
        PatchedReadingProgressRequest: {
            /** Format: uuid */
            asset?: string;
            /** Format: int64 */
            current_page?: number;
            /** Format: double */
            progress_ratio?: number;
            last_position?: unknown;
        };
        PatchedResearchPreferenceInputRequest: {
            research_personalization?: boolean;
        };
        PatchedWorkFileRightsInputRequest: {
            /** Format: uuid */
            request_key?: string;
            /** Format: date-time */
            expected_asset_updated_at?: string;
            rights_note?: string;
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
        PersonNode: {
            /** Format: uuid */
            readonly id: string;
            readonly name: string;
            readonly original_name: string;
            readonly birth_year: number;
            readonly death_year: number;
            readonly portrait_url: string;
            readonly scholar_slug: string;
            relation_label?: string;
            is_representative?: boolean;
            /** Format: int64 */
            sort_order?: number;
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
            public_detail?: components["schemas"]["PublicConceptDetail"];
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
        PreparePublicFileInputRequest: {
            /** Format: uuid */
            request_key: string;
            /** Format: date-time */
            expected_asset_updated_at: string;
            confirm: boolean;
        };
        PrerequisiteInputRequest: {
            /** Format: uuid */
            work_id: string;
            /** Format: uuid */
            requires_work_id: string;
            reference: components["schemas"]["EvidenceReferenceInputRequest"];
        };
        /**
         * @description * `generate` - generate
         *     * `cancel` - cancel
         * @enum {string}
         */
        PreviewCommandActionEnum: "generate" | "cancel";
        PreviewCommandRequest: {
            action: components["schemas"]["PreviewCommandActionEnum"];
            /** Format: uuid */
            request_id: string;
            expected_preview_revision: number;
            source_generation: number;
        };
        PreviewStatus: {
            /** Format: uuid */
            readonly audit_id: string;
            readonly audit_revision: number;
            readonly content_hash: string;
            readonly source_generation: number;
            readonly manuscript_revision: number;
            readonly preview_revision: number;
            readonly preview_generation: number;
            readonly status: string;
            readonly enabled: boolean;
            readonly page_count: number | null;
            readonly converter_version: string | null;
            readonly fonts_version: string | null;
            readonly poll_after_ms: number | null;
            readonly notice: string;
            readonly message: string;
        };
        /**
         * @description * `spread` - spread
         *     * `page` - page
         *     * `unknown` - unknown
         * @enum {string}
         */
        PrintedLabelPrecisionEnum: "spread" | "page" | "unknown";
        /**
         * @description * `confirm` - confirm
         *     * `cancel` - cancel
         *     * `retry` - retry
         * @enum {string}
         */
        PrivacyCommandInputActionEnum: "confirm" | "cancel" | "retry";
        PrivacyCommandInputRequest: {
            expected_revision: number;
            action: components["schemas"]["PrivacyCommandInputActionEnum"];
        };
        PrivacyItemsOutput: {
            owner_id: string;
            count: number;
            page: number;
            page_size: number;
            results: {
                [key: string]: unknown;
            }[];
        };
        PrivacyOperationInputRequest: {
            /** Format: uuid */
            request_id: string;
            kind: components["schemas"]["ReaderPrivacyOperationKindEnum"];
            categories?: components["schemas"]["CategoriesEnum"][];
            targets?: components["schemas"]["PrivacyTargetInputRequest"][];
        };
        PrivacyOperationOutput: {
            /** Format: uuid */
            id: string;
            owner_id: string;
            revision: number;
            kind: components["schemas"]["ReaderPrivacyOperationKindEnum"];
            status: components["schemas"]["PrivacyOperationOutputStatusEnum"];
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            updated_at: string;
            /** Format: date-time */
            finished_at: string | null;
            total: number;
            completed: number;
            failed: number;
            remaining: number;
            categories: string[];
            results: {
                [key: string]: unknown;
            }[];
            preview: {
                [key: string]: unknown;
            }[];
            error_code: string;
            download_available: boolean;
            notice: string;
        };
        /**
         * @description * `preview` - preview
         *     * `queued` - queued
         *     * `running` - running
         *     * `completed` - completed
         *     * `partial` - partial
         *     * `failed` - failed
         *     * `canceled` - canceled
         * @enum {string}
         */
        PrivacyOperationOutputStatusEnum: "preview" | "queued" | "running" | "completed" | "partial" | "failed" | "canceled";
        PrivacyOperationsPage: {
            count: number;
            /** Format: uri */
            next: string | null;
            /** Format: uri */
            previous: string | null;
            results: components["schemas"]["PrivacyOperationOutput"][];
        };
        PrivacySummaryOutput: {
            owner_id: string;
            revision: number;
            retention: {
                [key: string]: boolean;
            };
            automatic_memory_use: boolean;
            confirmed_notes: number;
            authorized_contexts: number;
            export_counts: {
                [key: string]: number;
            };
            erase_counts: {
                [key: string]: number;
            };
            operations: components["schemas"]["PrivacyOperationOutput"][];
            preference_history: {
                [key: string]: unknown;
            }[];
            max_operation_items: number;
            export_formats: string[];
            notice: string;
        };
        /**
         * @description * `reading_history` - reading_history
         *     * `search_history` - search_history
         *     * `annotations` - annotations
         *     * `memories` - memories
         *     * `parallel_alignments` - parallel_alignments
         *     * `plans` - plans
         *     * `followed_topics` - followed_topics
         *     * `source_follows` - source_follows
         *     * `saved_knowledge` - saved_knowledge
         * @enum {string}
         */
        PrivacyTargetInputCategoryEnum: "reading_history" | "search_history" | "annotations" | "memories" | "parallel_alignments" | "plans" | "followed_topics" | "source_follows" | "saved_knowledge";
        PrivacyTargetInputRequest: {
            category: components["schemas"]["PrivacyTargetInputCategoryEnum"];
            /** Format: uuid */
            id: string;
            revision: string;
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
            expected_owner_id?: number;
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
        PublicCitationInputRequest: {
            /** Format: uuid */
            edition_id?: string;
            reference?: components["schemas"]["EvidenceReferenceInputRequest"];
            selected_text?: string;
        };
        PublicCitationOutput: {
            readonly source: unknown;
            readonly reference: unknown;
            readonly citations: {
                [key: string]: unknown;
            };
        };
        PublicClassificationLink: {
            /** Format: uuid */
            id: string | null;
            name: string;
            slug: string;
            is_primary: boolean;
        };
        /**
         * @description * `ready` - ready
         *     * `empty` - empty
         *     * `partial` - partial
         *     * `unavailable` - unavailable
         * @enum {string}
         */
        PublicCollectionStateEnum: "ready" | "empty" | "partial" | "unavailable";
        PublicConceptAuthor: {
            /** Format: uuid */
            id: string;
            name: string;
            original_name: string;
            birth_year: number | null;
            death_year: number | null;
            portrait_url: string;
            scholar_slug: string;
        };
        PublicConceptDetail: {
            configured: boolean;
            /** Format: uuid */
            revision_id: string | null;
            usages: components["schemas"]["PublicConceptUsage"][];
            unavailable_usage_count: number;
        };
        PublicConceptUsage: {
            /** Format: uuid */
            id: string;
            term: string;
            language: string;
            usage_type: string;
            interpretation: string;
            attribution_note: string;
            title: string;
            explanatory_object: string;
            period: string;
            context: string;
            author: components["schemas"]["PublicConceptAuthor"] | null;
            source: components["schemas"]["PlacementSource"];
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
        /**
         * @description * `content` - 内容
         *     * `function` - 功能
         *     * `usage` - 使用咨询
         *     * `suggestion` - 改进建议
         *     * `citation` - 引用
         *     * `accessibility` - 无障碍
         *     * `other` - 其他
         * @enum {string}
         */
        PublicFeedbackCategoryEnum: "content" | "function" | "usage" | "suggestion" | "citation" | "accessibility" | "other";
        PublicFeedbackInputRequest: {
            /** Format: uuid */
            request_id: string;
            /** @default other */
            category: components["schemas"]["PublicFeedbackCategoryEnum"];
            body: string;
            contact?: string;
            /** @default  */
            path: string;
            consent: boolean;
        };
        PublicFeedbackReceipt: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            request_id: string;
            status: components["schemas"]["PublicFeedbackStatusEnum"];
            /** Format: date-time */
            created_at: string;
            message: string;
        };
        /**
         * @description * `submitted` - 已提交
         *     * `reviewing` - 处理中
         *     * `resolved` - 已处理
         * @enum {string}
         */
        PublicFeedbackStatusEnum: "submitted" | "reviewing" | "resolved";
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
        PublicParallelCalibrationPageOutput: {
            /** @description 始终为 null；公开读取逐页复核来源，不以未复核候选数冒充可见校准总数。 */
            count: number | null;
            next: string | null;
            previous: string | null;
            results: components["schemas"]["ParallelCalibrationOutput"][];
            notice: string;
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
        PublicReaderManifest: {
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
            work: components["schemas"]["PublicReaderWork"];
        };
        /** @description The requested PDF and its bibliography share one activated edition. */
        PublicReaderWork: {
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
            readonly edition: components["schemas"]["CatalogEdition"] | null;
            readonly theories: components["schemas"]["PublicEntityLink"][];
            readonly topics: components["schemas"]["PublicEntityLink"][];
            readonly disciplines: components["schemas"]["PublicClassificationLink"][];
            readonly subdisciplines: components["schemas"]["PublicClassificationLink"][];
            readonly editions: components["schemas"]["CatalogEdition"][];
        };
        /**
         * @description * `available` - available
         *     * `replaced` - replaced
         *     * `unavailable` - unavailable
         *     * `page` - page
         * @enum {string}
         */
        PublicSourceAvailabilityEnum: "available" | "replaced" | "unavailable" | "page";
        PublicSourceStatus: {
            path: string;
            canonical_path: string;
            status: components["schemas"]["PublicSourceAvailabilityEnum"];
            title: string;
            authors: string[];
            cover_url: string;
            source_type: string;
            version_label: string;
            location: string;
            /** Format: date-time */
            updated_at: string | null;
            /** Format: date-time */
            checked_at: string;
            can_subscribe: boolean;
            reader_url: string;
            /** Format: uuid */
            work_id: string | null;
            /** Format: uuid */
            edition_id: string | null;
            /** Format: uuid */
            asset_id: string | null;
            /** Format: uuid */
            catalog_revision_id: string | null;
            /** Format: uuid */
            document_revision_id: string | null;
            notice: string;
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
        PublicWorkDetail: {
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
            readonly edition: components["schemas"]["CatalogEdition"] | null;
            readonly theories: components["schemas"]["PublicEntityLink"][];
            readonly topics: components["schemas"]["PublicEntityLink"][];
            readonly disciplines: components["schemas"]["PublicClassificationLink"][];
            readonly subdisciplines: components["schemas"]["PublicClassificationLink"][];
            readonly editions: components["schemas"]["CatalogEdition"][];
            readonly outline: components["schemas"]["PublicOutlineItem"][];
            readonly theory_associations: components["schemas"]["PublicTheoryAssociation"][];
            /** @description Evidence-backed curation groups; detailed EvidenceEnvelope JSON is not yet a verified typed contract. */
            readonly curated_claims: {
                [key: string]: unknown[];
            };
            readonly relations: components["schemas"]["WorkRelations"];
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
        /**
         * @description * `pause` - pause
         *     * `resume` - resume
         * @enum {string}
         */
        ReaderOCRActionEnum: "pause" | "resume";
        ReaderOCRCommandInputRequest: {
            action: components["schemas"]["ReaderOCRActionEnum"];
            /** Format: uuid */
            request_id: string;
            /** Format: uuid */
            job_id: string;
            job_version: string;
            source_sha256: string;
            /** Format: uuid */
            document_revision_id: string | null;
        };
        ReaderOCRContentOutput: {
            state: components["schemas"]["ReaderOCRContentStateEnum"];
            url: string | null;
            label: string;
            notice: string;
        };
        /**
         * @description * `unavailable` - unavailable
         *     * `awaiting_publication` - awaiting_publication
         *     * `published` - published
         *     * `admin_preview` - admin_preview
         * @enum {string}
         */
        ReaderOCRContentStateEnum: "unavailable" | "awaiting_publication" | "published" | "admin_preview";
        ReaderOCRJobOutput: {
            /** Format: uuid */
            id: string;
            /** @description 固定字符串；提交命令时原样传回，不重新格式化时间。 */
            job_version: string;
            status: string;
            phase: string;
            phase_label: string;
            completed_pages: number | null;
            /** @description 本次任务目标页数，不一定等于整份文件页数。 */
            total_pages: number | null;
            /** Format: double */
            percent: number | null;
            phase_elapsed_seconds: number;
            /** Format: date-time */
            updated_at: string;
            pause_requested: boolean;
            stale: boolean;
        };
        ReaderOCRReceiptOutput: {
            /** Format: uuid */
            request_id: string;
            action: components["schemas"]["ReaderOCRActionEnum"];
            /** Format: uuid */
            job_id: string;
            applied: boolean;
        };
        ReaderOCRStatusOutput: {
            /** Format: uuid */
            asset_id: string;
            /** Format: uuid */
            edition_id: string;
            owner_id: number | null;
            /** Format: uuid */
            document_revision_id: string | null;
            source_sha256: string;
            file_page_count: number;
            ocr_status: string;
            /** Format: date-time */
            checked_at: string;
            job: components["schemas"]["ReaderOCRJobOutput"] | null;
            can_pause: boolean;
            can_resume: boolean;
            denied_reason: string;
            management_url: string | null;
            processed_content: components["schemas"]["ReaderOCRContentOutput"];
            receipt: components["schemas"]["ReaderOCRReceiptOutput"] | null;
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
            printed_labels?: string[];
            printed_label_precision?: components["schemas"]["PrintedLabelPrecisionEnum"];
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
        /**
         * @description * `export` - export
         *     * `erase` - erase
         * @enum {string}
         */
        ReaderPrivacyOperationKindEnum: "export" | "erase";
        ReaderRelatedLink: {
            name: string;
            slug: string;
        };
        ReaderRelatedScholar: {
            name: string;
            slug: string | null;
            years: string;
            portrait: string;
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
        ReadingHistory: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            asset: string;
            readonly work: components["schemas"]["WorkCard"];
            readonly title: string;
            /** Format: int64 */
            page_index?: number;
            /** Format: int64 */
            session_seconds?: number;
            /** Format: date-time */
            readonly created_at: string;
        };
        ReadingHistoryRequest: {
            /** Format: uuid */
            asset: string;
            /** Format: int64 */
            page_index?: number;
            /** Format: int64 */
            session_seconds?: number;
        };
        ReadingPaceInputRequest: {
            cjk_chars_per_minute?: number;
            words_per_minute?: number;
            fallback_minutes_per_page?: number;
        };
        ReadingPath: {
            /** Format: uuid */
            readonly id: string;
            title: string;
            slug: string;
            introduction?: string;
            learning_goal?: string;
            /** Format: uuid */
            primary_discipline?: string | null;
            readonly primary_discipline_data: components["schemas"]["DisciplineCompact"];
            audience?: string;
            difficulty?: components["schemas"]["ReadingPathDifficultyEnum"];
            estimated_reading?: string;
            /** Format: uri */
            cover_asset?: string | null;
            readonly cover_url: string;
            readonly cover_media: components["schemas"]["PublicCoverMedia"] | null;
            status?: components["schemas"]["KnowledgePublicationStatusEnum"];
            /** Format: int64 */
            sort_order?: number;
            readonly stages: components["schemas"]["ReadingPathStage"][];
            items?: components["schemas"]["ReadingPathItem"][];
            /** Format: date-time */
            readonly published_at: string | null;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
        };
        /**
         * @description * `beginner` - 入门
         *     * `intermediate` - 进阶
         *     * `advanced` - 深入
         * @enum {string}
         */
        ReadingPathDifficultyEnum: "beginner" | "intermediate" | "advanced";
        ReadingPathItem: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            stage?: string | null;
            readonly stage_data: components["schemas"]["ReadingPathStage"];
            stage_name: string;
            stage_description?: string;
            /** Format: uuid */
            node?: string | null;
            readonly node_data: components["schemas"]["KnowledgeNodeList"];
            /** Format: uuid */
            work?: string | null;
            readonly work_data: components["schemas"]["CompactTheoryWork"] | null;
            recommendation_reason?: string;
            prerequisite?: string;
            /** Format: int64 */
            position?: number;
            /** Format: int64 */
            reading_order?: number;
            is_required?: boolean;
            editorial_note?: string;
        };
        ReadingPathStage: {
            /** Format: uuid */
            readonly id: string;
            name: string;
            description?: string;
            /** Format: int64 */
            position?: number;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
        };
        ReadingProgress: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            asset: string;
            readonly work: components["schemas"]["WorkCard"];
            /** Format: int64 */
            current_page?: number;
            /** Format: double */
            progress_ratio?: number;
            last_position?: unknown;
            /** Format: date-time */
            readonly updated_at: string;
        };
        ReadingProgressRequest: {
            /** Format: uuid */
            asset: string;
            /** Format: int64 */
            current_page?: number;
            /** Format: double */
            progress_ratio?: number;
            last_position?: unknown;
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
         * @description * `project` - project
         *     * `plan` - plan
         * @enum {string}
         */
        ResearchMemoryContextKindEnum: "project" | "plan";
        /**
         * @description * `concept` - concept
         *     * `understanding` - understanding
         *     * `question` - question
         *     * `method` - method
         *     * `observation` - observation
         *     * `contradiction` - contradiction
         * @enum {string}
         */
        ResearchMemoryKindEnum: "concept" | "understanding" | "question" | "method" | "observation" | "contradiction";
        /**
         * @description * `grant` - grant
         *     * `revoke` - revoke
         *     * `revoke_all` - revoke_all
         * @enum {string}
         */
        ResearchMemoryUsageActionEnum: "grant" | "revoke" | "revoke_all";
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
        /**
         * @description * `suggested` - 系统建议
         *     * `approved` - 人工确认
         *     * `rejected` - 人工拒绝
         * @enum {string}
         */
        ReviewStatusEnum: "suggested" | "approved" | "rejected";
        /**
         * @description * `foundational_work` - 奠基性原著
         *     * `systematic_exposition` - 系统阐释
         *     * `theoretical_development` - 理论发展
         *     * `empirical_application` - 经验应用
         *     * `comparative_study` - 比较研究
         *     * `critique` - 批评反思
         *     * `general_mention` - 一般提及
         * @enum {string}
         */
        RoleEnum: "foundational_work" | "systematic_exposition" | "theoretical_development" | "empirical_application" | "comparative_study" | "critique" | "general_mention";
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
            relation_type: components["schemas"]["ScholarRelationRelationTypeEnum"];
            direction: components["schemas"]["ScholarRelationDirectionEnum"];
            summary: string;
            source: string;
            readonly status: string;
            edit_version?: string;
            readonly has_unpublished_changes: boolean;
        };
        /**
         * @description * `directed` - directed
         *     * `bidirectional` - bidirectional
         *     * `undirected` - undirected
         * @enum {string}
         */
        ScholarRelationDirectionEnum: "directed" | "bidirectional" | "undirected";
        ScholarRelationPage: {
            count: number;
            next: string | null;
            previous: string | null;
            results: components["schemas"]["ScholarRelation"][];
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
        ScholarRelationRelationTypeEnum: "teaching" | "cooperation" | "influence" | "criticism" | "comparative_reading" | "other";
        ScholarRelationRequest: {
            /** Format: uuid */
            source_scholar: string;
            /** Format: uuid */
            target_scholar: string;
            relation_type: components["schemas"]["ScholarRelationRelationTypeEnum"];
            direction: components["schemas"]["ScholarRelationDirectionEnum"];
            summary: string;
            source: string;
            edit_version?: string;
        };
        /**
         * @description * `works` - works
         *     * `scholars` - scholars
         *     * `disciplines` - disciplines
         *     * `subdisciplines` - subdisciplines
         *     * `theories` - theories
         *     * `topics` - topics
         *     * `reading_paths` - reading_paths
         * @enum {string}
         */
        ScopedSearchContextEnum: "works" | "scholars" | "disciplines" | "subdisciplines" | "theories" | "topics" | "reading_paths";
        ScopedSearchGroup: {
            context: components["schemas"]["ScopedSearchContextEnum"];
            label: string;
            backend: components["schemas"]["BackendEnum"];
            count: number;
            results: components["schemas"]["ScopedSearchResult"][];
            /** @description Present only for a non-global scoped search. */
            pagination?: components["schemas"]["ScopedSearchPagination"];
        };
        ScopedSearchMatch: {
            type: components["schemas"]["ScopedSearchMatchTypeEnum"];
            query: string;
            highlights: string[];
        };
        /**
         * @description * `exact` - exact
         *     * `verified_alias` - verified_alias
         *     * `prefix` - prefix
         *     * `text` - text
         *     * `browse` - browse
         * @enum {string}
         */
        ScopedSearchMatchTypeEnum: "exact" | "verified_alias" | "prefix" | "text" | "browse";
        ScopedSearchOutput: {
            implementation_version: string;
            context: components["schemas"]["SearchContextEnum"];
            visibility: components["schemas"]["ScopedSearchOutputVisibilityEnum"];
            query: string;
            groups: components["schemas"]["ScopedSearchGroup"][];
            total: number;
            pagination: components["schemas"]["ScopedSearchPagination"];
            /** Format: double */
            latency_ms: number;
        };
        /**
         * @description * `public` - public
         *     * `admin` - admin
         * @enum {string}
         */
        ScopedSearchOutputVisibilityEnum: "public" | "admin";
        ScopedSearchPagination: {
            page: number;
            limit: number;
            total: number;
            total_pages: number;
        };
        ScopedSearchResult: {
            context: components["schemas"]["ScopedSearchContextEnum"];
            entity_type: string;
            /** Format: uuid */
            id: string;
            title: string;
            subtitle: string;
            description: string;
            url: string;
            match: components["schemas"]["ScopedSearchMatch"];
            metadata: {
                [key: string]: unknown;
            };
        };
        /**
         * @description * `works` - works
         *     * `scholars` - scholars
         *     * `disciplines` - disciplines
         *     * `subdisciplines` - subdisciplines
         *     * `theories` - theories
         *     * `topics` - topics
         *     * `reading_paths` - reading_paths
         *     * `global` - global
         * @enum {string}
         */
        SearchContextEnum: "works" | "scholars" | "disciplines" | "subdisciplines" | "theories" | "topics" | "reading_paths" | "global";
        SearchRecordOutput: {
            /** Format: uuid */
            id: string;
            query: string;
            filters: unknown;
            /** Format: date-time */
            created_at: string;
        };
        SearchRecordsPage: {
            owner_id: string;
            recording_enabled: boolean;
            count: number;
            page: number;
            page_size: number;
            results: components["schemas"]["SearchRecordOutput"][];
            notice: string;
        };
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
            expected_owner_id?: number;
            /**
             * Format: uuid
             * @description 未知响应重试沿用原标识；旧客户端可省略。
             */
            request_id?: string;
            note?: string;
            notes?: {
                [key: string]: string;
            };
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
        /**
         * @description * `relevance` - relevance
         *     * `year_desc` - year_desc
         *     * `year_asc` - year_asc
         * @enum {string}
         */
        SortEnum: "relevance" | "year_desc" | "year_asc";
        /**
         * @description * `manual` - manual
         *     * `pdf_page_labels` - pdf_page_labels
         *     * `embedded_text` - embedded_text
         *     * `ocr` - ocr
         *     * `sequence` - sequence
         *     * `file_index` - file_index
         *     * `unknown` - unknown
         * @enum {string}
         */
        SourceEnum: "manual" | "pdf_page_labels" | "embedded_text" | "ocr" | "sequence" | "file_index" | "unknown";
        SourceEventOutput: {
            /** Format: uuid */
            id: string;
            action: components["schemas"]["SourceEventOutputActionEnum"];
            before_status: string;
            after_status: string;
            /** Format: date-time */
            observed_at: string;
            revision: number;
        };
        /**
         * @description * `subscribe` - subscribe
         *     * `unsubscribe` - unsubscribe
         *     * `mark_read` - mark_read
         *     * `changed` - changed
         * @enum {string}
         */
        SourceEventOutputActionEnum: "subscribe" | "unsubscribe" | "mark_read" | "changed";
        /**
         * @description * `subscribe` - subscribe
         *     * `unsubscribe` - unsubscribe
         *     * `mark_read` - mark_read
         * @enum {string}
         */
        SourceFollowCommandActionEnum: "subscribe" | "unsubscribe" | "mark_read";
        SourceFollowCommandRequest: {
            path: string;
            action: components["schemas"]["SourceFollowCommandActionEnum"];
            /** Format: uuid */
            request_id: string;
            expected_revision: number;
        };
        SourceFollowOutput: {
            /** Format: uuid */
            id: string;
            owner_id: string;
            path: string;
            active: boolean;
            revision: number;
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            updated_at: string;
            /** Format: date-time */
            last_checked_at: string | null;
            check_error: string;
            unread_count: number;
            updates_paused: boolean;
            source: components["schemas"]["PublicSourceStatus"];
            notice: string;
            history: components["schemas"]["SourceHistoryOutput"];
        };
        SourceFollowsPage: {
            count: number;
            page: number;
            page_size: number;
            owner_id: string;
            results: components["schemas"]["SourceFollowOutput"][];
            notice: string;
        };
        SourceHistoryOutput: {
            count: number;
            page: number;
            page_size: number;
            results: components["schemas"]["SourceEventOutput"][];
        };
        /**
         * @description * `available` - available
         *     * `unavailable` - unavailable
         * @enum {string}
         */
        SourceStatusEnum: "available" | "unavailable";
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
        /**
         * @description * `high` - 高
         *     * `medium` - 中
         *     * `low` - 低
         * @enum {string}
         */
        StrengthEnum: "high" | "medium" | "low";
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
        TheoryBrowseCounts: {
            theory_traditions: number;
            subdisciplines: number;
            debates: number;
        };
        TheoryOverviewDiscipline: {
            /** Format: uuid */
            readonly id: string;
            code: string;
            name: string;
            foreign_name?: string;
            slug: string;
            description?: string;
            /** Format: uri */
            hero_image?: string | null;
            counts: {
                [key: string]: number;
            };
        };
        TheoryRecent: {
            nodes: components["schemas"]["KnowledgeNodeList"][];
            timeline_events: components["schemas"]["NormalizedTimelineEvent"][];
            work_relations: components["schemas"]["WorkNodeRelation"][];
        };
        TheorySystemOverview: {
            disciplines: components["schemas"]["TheoryOverviewDiscipline"][];
            featured_nodes: components["schemas"]["KnowledgeNodeList"][];
            browse: components["schemas"]["TheoryBrowseCounts"];
            reading_paths: components["schemas"]["ReadingPath"][];
            recent: components["schemas"]["TheoryRecent"];
        };
        TheoryTaxonomyLink: {
            /** Format: uuid */
            id: string;
            name: string;
            slug: string;
            foreign_name?: string;
            /** Format: uuid */
            discipline_id?: string | null;
        };
        TheoryTimelineTarget: {
            type: string;
            /** Format: uuid */
            id: string;
            name: string;
            relation_type: string;
            slug?: string;
            detail_href?: string | null;
        };
        TheoryWorkGroups: {
            foundational_work?: components["schemas"]["WorkNodeRelation"][];
            systematic_exposition?: components["schemas"]["WorkNodeRelation"][];
            theoretical_development?: components["schemas"]["WorkNodeRelation"][];
            empirical_application?: components["schemas"]["WorkNodeRelation"][];
            comparative_study?: components["schemas"]["WorkNodeRelation"][];
            critique?: components["schemas"]["WorkNodeRelation"][];
            general_mention?: components["schemas"]["WorkNodeRelation"][];
        };
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
        WorkEditionOutput: {
            /** Format: uuid */
            id: string;
            label: string;
            version_label: string;
            publication_year: number | null;
            publisher: string;
            language: string;
            is_primary: boolean;
            state: string;
            original_count: number;
            reader_count: number;
            /** Format: uuid */
            current_reader_asset_id: string | null;
        };
        WorkFileHistoryOutput: {
            count: number;
            page: number;
            page_size: number;
            results: components["schemas"]["WorkFileHistoryRowOutput"][];
        };
        WorkFileHistoryRowOutput: {
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
        WorkFileOutput: {
            /** Format: uuid */
            id: string;
            kind: string;
            filename: string;
            mime_type: string;
            byte_size: number;
            page_count: number;
            sha256: string;
            version: number;
            /** Format: uuid */
            source_asset_id: string | null;
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            updated_at: string;
            created_by: string;
            status: string;
            validation_status: string;
            is_current: boolean;
            is_public_reader: boolean;
            preview_url: string;
            download_url: string;
            generate_reader_url: string;
            can_adopt: boolean;
            rights_note: string;
            public_preparation: components["schemas"]["WorkFilePublicPreparationOutput"];
            access_status: string;
        };
        WorkFilePageOutput: {
            count: number;
            page: number;
            page_size: number;
            results: components["schemas"]["WorkFileOutput"][];
        };
        WorkFilePublicPreparationOutput: {
            required: boolean;
            status: string;
            can_prepare: boolean;
            prepare_url: string;
            detail: string;
        };
        WorkFilePublicPreparationResult: {
            /** Format: uuid */
            request_key: string;
            /** Format: uuid */
            asset_id: string;
            status: string;
            detail: string;
        };
        WorkFileRightsOutput: {
            note: string;
            access_status: string;
            /** Format: uuid */
            source_asset_id: string | null;
            /** Format: date-time */
            updated_at: string | null;
            can_edit: boolean;
        };
        WorkFileRightsUpdateOutput: {
            /** Format: uuid */
            request_key: string;
            /** Format: uuid */
            asset_id: string;
            rights_note: string;
            /** Format: date-time */
            updated_at: string;
        };
        WorkFileTaskOutput: {
            /** Format: uuid */
            id: string;
            status: string;
            dispatch_status: string;
            progress: number;
            is_active: boolean;
            error_message: string;
            retry_url: string;
            resume_url: string;
            processing_href: string;
            source_filename: string;
            /** Format: uuid */
            original_asset_id: string | null;
            /** Format: uuid */
            reader_asset_id: string | null;
            generate_reader: boolean;
            action: string;
            /** Format: date-time */
            created_at: string;
        };
        WorkFileUploadOutput: {
            accepted: boolean;
            created: boolean;
            /** Format: uuid */
            request_key: string;
            /** Format: uuid */
            item_id: string;
            /** Format: uuid */
            work_id: string;
            /** Format: uuid */
            edition_id: string;
            status: string;
            dispatch_status: string;
            workbench_url: string;
            detail: string;
        };
        WorkFilesCapabilitiesOutput: {
            formats: components["schemas"]["FileFormatCapabilityOutput"][];
            can_edit: boolean;
            can_publish: boolean;
            max_active_tasks_per_edition: number;
        };
        WorkFilesEditionOutput: {
            /** Format: uuid */
            id: string;
            /** Format: date-time */
            updated_at: string;
            /** Format: uuid */
            active_revision_id: string | null;
            /** Format: uuid */
            current_reader_asset_id: string | null;
            /** Format: uuid */
            public_reader_asset_id: string | null;
            rights: components["schemas"]["WorkFileRightsOutput"];
            workbench_url: string;
        };
        WorkFilesStateOutput: {
            work: components["schemas"]["WorkFilesWorkOutput"];
            editions: components["schemas"]["WorkEditionOutput"][];
            /** Format: uuid */
            selected_edition_id: string | null;
            edition: components["schemas"]["WorkFilesEditionOutput"] | null;
            files: components["schemas"]["WorkFilePageOutput"];
            current_reader_file: components["schemas"]["WorkFileOutput"] | null;
            public_reader_file: components["schemas"]["WorkFileOutput"] | null;
            tasks: components["schemas"]["WorkFileTaskOutput"][];
            task_count: number;
            capabilities: components["schemas"]["WorkFilesCapabilitiesOutput"];
            history: components["schemas"]["WorkFileHistoryOutput"];
            impact: components["schemas"]["FileImpactOutput"];
        };
        WorkFilesWorkOutput: {
            /** Format: uuid */
            id: string;
            title: string;
            /** Format: date-time */
            updated_at: string;
            cover_url: string;
            authors: string[];
            document_type: string;
            original_publication_year: number | null;
        };
        WorkIssueContents: {
            /** Format: uuid */
            id: string | null;
            /** Format: uuid */
            article_work_id: string | null;
            title: string;
            author_display: string;
            page_range: string;
            position: number;
            article_href: string;
        };
        WorkNodeRelation: {
            /** Format: uuid */
            readonly id: string;
            /** Format: uuid */
            work: string;
            readonly work_data: components["schemas"]["CompactTheoryWork"] | null;
            /** Format: uuid */
            node: string;
            readonly node_name: string;
            readonly node_slug: string;
            /** @default general_mention */
            role: components["schemas"]["RoleEnum"];
            readonly role_label: string;
            is_primary?: boolean;
            strength?: components["schemas"]["StrengthEnum"];
            /** Format: double */
            confidence?: number;
            status?: components["schemas"]["KnowledgePublicationStatusEnum"];
            source?: string;
            readonly evidence: components["schemas"]["EvidenceSnippet"][];
            /** Format: date-time */
            readonly reviewed_at: string | null;
            /** Format: date-time */
            readonly created_at: string;
            /** Format: date-time */
            readonly updated_at: string;
        };
        WorkRelatedConcept: {
            /** Format: uuid */
            id: string;
            name: string;
            slug: string;
            summary: string;
        };
        WorkRelatedCuration: {
            /** Format: uuid */
            id: string;
            title: string;
            slug: string;
            summary: string;
            cover_url: string;
        };
        WorkRelatedJournal: {
            /** Format: uuid */
            id: string;
            slug: string;
            title: string;
            cover_url: string;
            edition: components["schemas"]["CatalogEdition"];
            contents: components["schemas"]["WorkIssueContents"][];
        };
        WorkRelatedPath: {
            /** Format: uuid */
            id: string;
            title: string;
            slug: string;
            introduction: string;
            cover_url: string;
        };
        WorkRelatedScholar: {
            /** Format: uuid */
            id: string;
            slug: string;
            person: components["schemas"]["PersonCompact"];
            short_description: string;
            roles: string[];
        };
        WorkRelatedTopic: {
            /** Format: uuid */
            id: string;
            name: string;
            slug: string;
            summary: string;
            description: string;
            hero_image: string;
        };
        WorkRelations: {
            scholars: components["schemas"]["WorkRelatedScholar"][];
            concepts: components["schemas"]["WorkRelatedConcept"][];
            topics: components["schemas"]["WorkRelatedTopic"][];
            reading_paths: components["schemas"]["WorkRelatedPath"][];
            curations: components["schemas"]["WorkRelatedCuration"][];
            works: components["schemas"]["CatalogWork"][];
            journal_issues: components["schemas"]["WorkRelatedJournal"][];
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
    catalog_admin_assets_page_mapping_retrieve: {
        parameters: {
            query?: {
                history_page?: number;
                revision_id?: string;
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
                    "application/json": components["schemas"]["MappingReadResponse"];
                };
            };
        };
    };
    catalog_admin_assets_page_mapping_create: {
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
                "application/json": components["schemas"]["MappingCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MappingCommandRequest"];
                "multipart/form-data": components["schemas"]["MappingCommandRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MappingCommandResponse"];
                };
            };
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MappingState"];
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
    catalog_admin_editions_files_create: {
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
                "multipart/form-data": components["schemas"]["EditionFileInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["EditionFileInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkFileUploadOutput"];
                };
            };
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkFileUploadOutput"];
                };
            };
        };
    };
    catalog_admin_editions_files_adopt_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
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
                    "application/json": components["schemas"]["FileAdoptionPreviewOutput"];
                };
            };
        };
    };
    catalog_admin_editions_files_adopt_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
                edition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FileAdoptionInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["FileAdoptionInputRequest"];
                "multipart/form-data": components["schemas"]["FileAdoptionInputRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileAdoptionResultOutput"];
                };
            };
        };
    };
    catalog_admin_editions_files_content_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
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
                    "application/octet-stream": string;
                };
            };
        };
    };
    catalog_admin_editions_files_generate_reader_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
                edition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateReaderInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["GenerateReaderInputRequest"];
                "multipart/form-data": components["schemas"]["GenerateReaderInputRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkFileUploadOutput"];
                };
            };
        };
    };
    catalog_admin_editions_files_prepare_public_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
                edition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PreparePublicFileInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PreparePublicFileInputRequest"];
                "multipart/form-data": components["schemas"]["PreparePublicFileInputRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkFilePublicPreparationResult"];
                };
            };
        };
    };
    catalog_admin_editions_files_rights_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
                edition_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedWorkFileRightsInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedWorkFileRightsInputRequest"];
                "multipart/form-data": components["schemas"]["PatchedWorkFileRightsInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkFileRightsUpdateOutput"];
                };
            };
        };
    };
    "catalog_admin_editions_files_impact.csv_retrieve": {
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
                    "text/csv": string;
                };
            };
        };
    };
    catalog_admin_editions_files_requests_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                edition_id: string;
                request_key: string;
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
                    "application/json": components["schemas"]["WorkFileUploadOutput"];
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
    catalog_admin_public_feedback_list: {
        parameters: {
            query?: {
                /**
                 * @description * `` -
                 *     * `content` - content
                 *     * `function` - function
                 *     * `usage` - usage
                 *     * `suggestion` - suggestion
                 *     * `citation` - citation
                 *     * `accessibility` - accessibility
                 *     * `other` - other
                 */
                category?: "" | "content" | "function" | "usage" | "suggestion" | "citation" | "accessibility" | "other";
                page?: number;
                q?: string;
                /**
                 * @description * `` -
                 *     * `submitted` - submitted
                 *     * `reviewing` - reviewing
                 *     * `resolved` - resolved
                 */
                status?: "" | "submitted" | "reviewing" | "resolved";
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
                    "application/json": components["schemas"]["FeedbackListOutput"];
                };
            };
        };
    };
    catalog_admin_public_feedback_retrieve: {
        parameters: {
            query?: {
                history_page?: number;
            };
            header?: never;
            path: {
                feedback_id: string;
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
                    "application/json": components["schemas"]["FeedbackDetailOutput"];
                };
            };
        };
    };
    catalog_admin_public_feedback_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                feedback_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedFeedbackUpdateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedFeedbackUpdateInputRequest"];
                "multipart/form-data": components["schemas"]["PatchedFeedbackUpdateInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeedbackUpdateOutput"];
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
    catalog_admin_works_editions_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                work_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NewWorkEditionInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["NewWorkEditionInputRequest"];
                "multipart/form-data": components["schemas"]["NewWorkEditionInputRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NewWorkEditionOutput"];
                };
            };
        };
    };
    catalog_admin_works_files_retrieve: {
        parameters: {
            query?: {
                asset?: string;
                edition?: string;
                history_page?: number;
                impact_page?: number;
                page?: number;
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
                    "application/json": components["schemas"]["WorkFilesStateOutput"];
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
                    "application/json": components["schemas"]["PublicReaderManifest"];
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
                /** @description 仅排序本次已取得且重新核验的材料，不触发新检索。 */
                sort?: "relevance" | "year_asc" | "year_desc";
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
    catalog_discovery_search_remove_document_create: {
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
                "application/json": components["schemas"]["DiscoveryRemoveDocumentRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["DiscoveryRemoveDocumentRequest"];
                "multipart/form-data": components["schemas"]["DiscoveryRemoveDocumentRequest"];
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
    catalog_feedback_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PublicFeedbackInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PublicFeedbackInputRequest"];
                "multipart/form-data": components["schemas"]["PublicFeedbackInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicFeedbackReceipt"];
                };
            };
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicFeedbackReceipt"];
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
    catalog_parallel_candidates_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ParallelCandidatesInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ParallelCandidatesInputRequest"];
                "multipart/form-data": components["schemas"]["ParallelCandidatesInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ParallelCandidatesOutput"];
                };
            };
        };
    };
    catalog_parallel_segments_retrieve: {
        parameters: {
            query: {
                asset_id: string;
                document_revision_id?: string;
                focus?: string;
                offset?: number;
                page?: number;
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
                    "application/json": components["schemas"]["ParallelSegmentsOutput"];
                };
            };
        };
    };
    catalog_parallel_versions_retrieve: {
        parameters: {
            query: {
                asset_id: string;
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
                    "application/json": components["schemas"]["ParallelVersionsOutput"];
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
    catalog_search_retrieve: {
        parameters: {
            query?: {
                /** @description Catalog: readable or metadata. Legacy global: online or download. */
                access?: string[];
                author?: string[];
                concept?: string[];
                /**
                 * @description scope=catalog accepts global only. Other non-global contexts return the scoped envelope. Omitting context uses the deprecated legacy global response.
                 *
                 *     * `works` - works
                 *     * `scholars` - scholars
                 *     * `disciplines` - disciplines
                 *     * `subdisciplines` - subdisciplines
                 *     * `theories` - theories
                 *     * `topics` - topics
                 *     * `reading_paths` - reading_paths
                 *     * `global` - global
                 */
                context?: "works" | "scholars" | "disciplines" | "subdisciplines" | "theories" | "topics" | "reading_paths" | "global";
                /** @description Scoped subdisciplines, theories, topics or reading_paths only. */
                discipline?: string;
                document_type?: string[];
                /** @description With an explicit global context, the literal value 1 selects the scoped envelope. Ignored for scope=catalog. */
                envelope?: string;
                language?: string[];
                /** @description Scoped envelope page limit, default 24. Ignored by catalog and legacy global. */
                limit?: number;
                /** @description Catalog only. Repeat the parameter for multiple values. Defaults to title, author, keyword, abstract. */
                match?: ("title" | "author" | "keyword" | "abstract" | "fulltext")[];
                /** @description Scoped theories only, when type is absent. */
                node_type?: string;
                /** @description Defaults to 1. Catalog rejects values over 100000; legacy/scoped branches normalize invalid values. */
                page?: number;
                /** @description Catalog defaults to 24. Legacy defaults to 8 for scope=all, otherwise 24. Scoped envelope uses this only when limit is absent. */
                page_size?: number;
                /** @description Catalog and explicit context searches accept at most 500 characters; catalog also limits whitespace-separated terms to 20. */
                q?: string;
                /** @description catalog selects the snapshot-backed catalog response. Legacy global uses all by default, or book, article, thesis, report, scholar, topic, theory, fulltext to select pagination totals. */
                scope?: string;
                /**
                 * @description Catalog and legacy global only; defaults to relevance.
                 *
                 *     * `relevance` - relevance
                 *     * `newest` - newest
                 *     * `year` - year
                 */
                sort?: "relevance" | "newest" | "year";
                /** @description Legacy global only. */
                tag?: string[];
                theory?: string[];
                topic?: string[];
                /** @description Scoped theories node type; takes precedence over node_type. */
                type?: string;
                /**
                 * @description Scoped envelope only. admin is honored only for authorized staff or admin/editor/reviewer accounts; otherwise public is used.
                 *
                 *     * `public` - public
                 *     * `admin` - admin
                 */
                visibility?: "public" | "admin";
                /** @description Catalog/legacy year buckets: before-1900, 1900-1949, 1950-1999, 2000-2009, 2010-2019, 2020-now. */
                year?: string[];
                /** @description Catalog only; inclusive upper bound, not less than year_min. */
                year_max?: number;
                /** @description Catalog only; inclusive lower bound. */
                year_min?: number;
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
                    "application/json": components["schemas"]["GlobalSearchOutput"];
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
    catalog_theory_system_graph_retrieve: {
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
                    "application/json": components["schemas"]["LocalTheoryGraph"];
                };
            };
        };
    };
    catalog_theory_system_nodes_list: {
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
                    "application/json": components["schemas"]["PaginatedKnowledgeNodeListList"];
                };
            };
        };
    };
    catalog_theory_system_nodes_retrieve: {
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
                    "application/json": components["schemas"]["KnowledgeNodeDetail"];
                };
            };
        };
    };
    catalog_theory_system_nodes_citation_retrieve: {
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
                    "application/json": components["schemas"]["KnowledgeEntryCitation"];
                };
            };
        };
    };
    catalog_theory_system_overview_retrieve: {
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
                    "application/json": components["schemas"]["TheorySystemOverview"];
                };
            };
        };
    };
    catalog_theory_system_reading_paths_list: {
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
                    "application/json": components["schemas"]["PaginatedReadingPathList"];
                };
            };
        };
    };
    catalog_theory_system_reading_paths_retrieve: {
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
                    "application/json": components["schemas"]["ReadingPath"];
                };
            };
        };
    };
    catalog_theory_system_timeline_list: {
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
                    "application/json": components["schemas"]["PaginatedNormalizedTimelineEventList"];
                };
            };
        };
    };
    theory_system_timeline_detail: {
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
                    "application/json": components["schemas"]["PaginatedNormalizedTimelineEventList"];
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
                    "application/json": components["schemas"]["PublicWorkDetail"];
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
    distribution_assets_ocr_status_retrieve: {
        parameters: {
            query?: {
                /** @description 仅管理账户使用：查回本人固定命令回执，必须同时传 X-Reader-Owner。 */
                request_id?: string;
            };
            header?: {
                /** @description 当前账户 ID；普通读取可省略，传入时必须匹配当前登录账户。 */
                "X-Reader-Owner"?: string;
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
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReaderOCRStatusOutput"];
                };
            };
        };
    };
    distribution_assets_ocr_status_create: {
        parameters: {
            query?: never;
            header: {
                /** @description 固定为发起本次命令的当前账户 ID。 */
                "X-Reader-Owner": string;
            };
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReaderOCRCommandInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ReaderOCRCommandInputRequest"];
                "multipart/form-data": components["schemas"]["ReaderOCRCommandInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReaderOCRStatusOutput"];
                };
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
    ingestion_ocr_workspace_retrieve: {
        parameters: {
            query?: {
                detect_garbled?: boolean;
                detect_spreads?: boolean;
                history_page?: number;
                list_page?: number;
                pdf_page?: number;
                quality_threshold?: number;
                /**
                 * @description * `all` - all
                 *     * `issues` - issues
                 *     * `failed` - failed
                 *     * `unread` - unread
                 *     * `needs_review` - needs_review
                 *     * `completed` - completed
                 *     * `manual` - manual
                 *     * `reviewed` - reviewed
                 */
                status?: "all" | "issues" | "failed" | "unread" | "needs_review" | "completed" | "manual" | "reviewed";
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
                    "application/json": components["schemas"]["OCRWorkspace"];
                };
            };
        };
    };
    ingestion_ocr_workspace_create: {
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
                "application/json": components["schemas"]["OCRCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["OCRCommandRequest"];
                "multipart/form-data": components["schemas"]["OCRCommandRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OCRWorkspaceCommandResult"];
                };
            };
        };
    };
    reading_annotations_list: {
        parameters: {
            query?: {
                asset?: string;
                /**
                 * @description * `highlight` - 高亮
                 *     * `underline` - 划线
                 *     * `note` - 笔记
                 */
                kind?: "highlight" | "note" | "underline";
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                p?: number;
                page?: string;
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
                    "application/json": components["schemas"]["PaginatedAnnotationList"];
                };
            };
        };
    };
    reading_annotations_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnotationRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["AnnotationRequest"];
                "multipart/form-data": components["schemas"]["AnnotationRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Annotation"];
                };
            };
        };
    };
    reading_annotations_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 annotation 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["Annotation"];
                };
            };
        };
    };
    reading_annotations_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 annotation 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnotationRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["AnnotationRequest"];
                "multipart/form-data": components["schemas"]["AnnotationRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Annotation"];
                };
            };
        };
    };
    reading_annotations_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 annotation 的 UUID 字符串。 */
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
    reading_annotations_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 annotation 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedAnnotationRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedAnnotationRequest"];
                "multipart/form-data": components["schemas"]["PatchedAnnotationRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Annotation"];
                };
            };
        };
    };
    reading_bookmarks_list: {
        parameters: {
            query?: {
                asset?: string;
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                p?: number;
                page?: string;
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
                    "application/json": components["schemas"]["PaginatedBookmarkList"];
                };
            };
        };
    };
    reading_bookmarks_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BookmarkRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["BookmarkRequest"];
                "multipart/form-data": components["schemas"]["BookmarkRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Bookmark"];
                };
            };
        };
    };
    reading_bookmarks_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 bookmark 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["Bookmark"];
                };
            };
        };
    };
    reading_bookmarks_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 bookmark 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BookmarkRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["BookmarkRequest"];
                "multipart/form-data": components["schemas"]["BookmarkRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Bookmark"];
                };
            };
        };
    };
    reading_bookmarks_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 bookmark 的 UUID 字符串。 */
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
    reading_bookmarks_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 bookmark 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedBookmarkRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedBookmarkRequest"];
                "multipart/form-data": components["schemas"]["PatchedBookmarkRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Bookmark"];
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
    reading_citation_audits_manuscript_retrieve: {
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
                    "application/json": components["schemas"]["CitationTextUnitsOutput"];
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
    reading_citation_audits_preview_retrieve: {
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
                    "application/json": components["schemas"]["PreviewStatus"];
                };
            };
        };
    };
    reading_citation_audits_preview_create: {
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
                "application/json": components["schemas"]["PreviewCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PreviewCommandRequest"];
                "multipart/form-data": components["schemas"]["PreviewCommandRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PreviewStatus"];
                };
            };
        };
    };
    reading_citation_audits_preview_file_retrieve: {
        parameters: {
            query: {
                generation: number;
            };
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
                    "application/pdf": string;
                };
            };
        };
    };
    reading_citation_audits_versions_retrieve: {
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
                    "application/json": components["schemas"]["AuditVersionsOutput"];
                };
            };
        };
    };
    reading_citation_audits_versions_create: {
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
                "multipart/form-data": components["schemas"]["AuditVersionInputRequest"];
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
    reading_citation_preview_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PublicCitationInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PublicCitationInputRequest"];
                "multipart/form-data": components["schemas"]["PublicCitationInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicCitationOutput"];
                };
            };
        };
    };
    reading_citation_sources_list: {
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
    reading_citation_sources_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["CitationSourceCreateInputRequest"];
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
    reading_citation_sources_retrieve: {
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
    reading_citation_sources_destroy: {
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
    reading_citation_sources_command_create: {
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
                "application/json": components["schemas"]["CitationSourceCommandInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CitationSourceCommandInputRequest"];
                "multipart/form-data": components["schemas"]["CitationSourceCommandInputRequest"];
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
    reading_citation_sources_export_retrieve: {
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
    reading_citation_sources_ocr_retrieve: {
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
    reading_citation_sources_original_retrieve: {
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
    reading_citation_sources_preview_retrieve: {
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
                    "application/json": components["schemas"]["PreviewStatus"];
                };
            };
        };
    };
    reading_citation_sources_preview_create: {
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
                "application/json": components["schemas"]["PreviewCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PreviewCommandRequest"];
                "multipart/form-data": components["schemas"]["PreviewCommandRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PreviewStatus"];
                };
            };
        };
    };
    reading_citation_sources_preview_file_retrieve: {
        parameters: {
            query: {
                generation: number;
            };
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
                    "application/pdf": string;
                };
            };
        };
    };
    reading_citation_sources_segments_retrieve: {
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
                    "application/json": components["schemas"]["CitationTextUnitsOutput"];
                };
            };
        };
    };
    reading_history_list: {
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
                    "application/json": components["schemas"]["PaginatedReadingHistoryList"];
                };
            };
        };
    };
    reading_history_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReadingHistoryRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ReadingHistoryRequest"];
                "multipart/form-data": components["schemas"]["ReadingHistoryRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadingHistory"];
                };
            };
        };
    };
    reading_parallel_calibrations_list: {
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
                    "application/json": components["schemas"]["PaginatedParallelCalibrationPageOutputList"];
                };
            };
        };
    };
    reading_parallel_calibrations_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ParallelCalibrationCreateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ParallelCalibrationCreateInputRequest"];
                "multipart/form-data": components["schemas"]["ParallelCalibrationCreateInputRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ParallelCalibrationOutput"];
                };
            };
        };
    };
    reading_parallel_calibrations_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 parallel calibration 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["ParallelCalibrationOutput"];
                };
            };
        };
    };
    reading_parallel_calibrations_admin_list: {
        parameters: {
            query?: {
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                page?: number;
                /** @description 搜索关键词。 */
                search?: string;
                status?: string;
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
                    "application/json": components["schemas"]["PaginatedParallelCalibrationPageOutputList"];
                };
            };
        };
    };
    reading_parallel_calibrations_admin_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 parallel calibration 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["ParallelCalibrationOutput"];
                };
            };
        };
    };
    reading_parallel_calibrations_admin_publish_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 parallel calibration 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ParallelReviewInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ParallelReviewInputRequest"];
                "multipart/form-data": components["schemas"]["ParallelReviewInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ParallelCalibrationOutput"];
                };
            };
        };
    };
    reading_parallel_calibrations_admin_reject_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 parallel calibration 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ParallelReviewInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ParallelReviewInputRequest"];
                "multipart/form-data": components["schemas"]["ParallelReviewInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ParallelCalibrationOutput"];
                };
            };
        };
    };
    reading_parallel_calibrations_admin_review_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 parallel calibration 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ParallelReviewInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ParallelReviewInputRequest"];
                "multipart/form-data": components["schemas"]["ParallelReviewInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ParallelCalibrationOutput"];
                };
            };
        };
    };
    reading_parallel_calibrations_by_request_retrieve: {
        parameters: {
            query: {
                request_id: string;
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
                    "application/json": components["schemas"]["ParallelCalibrationOutput"];
                };
            };
        };
    };
    reading_parallel_calibrations_public_list: {
        parameters: {
            query: {
                left_asset: string;
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                page?: number;
                right_asset?: string;
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
                    "application/json": components["schemas"]["PaginatedPublicParallelCalibrationPageOutputList"];
                };
            };
        };
    };
    reading_parallel_calibrations_public_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 parallel calibration 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["ParallelCalibrationOutput"];
                };
            };
        };
    };
    reading_parallel_tasks_list: {
        parameters: {
            query?: {
                left_asset?: string;
                /** @description 用于排序结果的字段。 */
                ordering?: string;
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
                    "application/json": components["schemas"]["PaginatedParallelTaskPageOutputList"];
                };
            };
        };
    };
    reading_parallel_tasks_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ParallelTaskCreateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ParallelTaskCreateInputRequest"];
                "multipart/form-data": components["schemas"]["ParallelTaskCreateInputRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ParallelTaskOutput"];
                };
            };
        };
    };
    reading_parallel_tasks_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 parallel reading task 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["ParallelTaskOutput"];
                };
            };
        };
    };
    reading_parallel_tasks_destroy: {
        parameters: {
            query: {
                expected_revision: number;
            };
            header?: never;
            path: {
                /** @description 标识此 parallel reading task 的 UUID 字符串。 */
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
    reading_parallel_tasks_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 parallel reading task 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedParallelTaskUpdateInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedParallelTaskUpdateInputRequest"];
                "multipart/form-data": components["schemas"]["PatchedParallelTaskUpdateInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ParallelTaskOutput"];
                };
            };
        };
    };
    reading_parallel_tasks_by_request_retrieve: {
        parameters: {
            query: {
                request_id: string;
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
                    "application/json": components["schemas"]["ParallelTaskOutput"];
                };
            };
        };
    };
    reading_privacy_retrieve: {
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
                    "application/json": components["schemas"]["PrivacySummaryOutput"];
                };
            };
        };
    };
    reading_privacy_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedPrivacyPreferencesInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedPrivacyPreferencesInputRequest"];
                "multipart/form-data": components["schemas"]["PatchedPrivacyPreferencesInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivacySummaryOutput"];
                };
            };
        };
    };
    reading_privacy_items_retrieve: {
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
                    "application/json": components["schemas"]["PrivacyItemsOutput"];
                };
            };
        };
    };
    reading_privacy_operations_list: {
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
                    "application/json": components["schemas"]["PaginatedPrivacyOperationsPageList"];
                };
            };
        };
    };
    reading_privacy_operations_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PrivacyOperationInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PrivacyOperationInputRequest"];
                "multipart/form-data": components["schemas"]["PrivacyOperationInputRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivacyOperationOutput"];
                };
            };
        };
    };
    reading_privacy_operations_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 reader data operation 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["PrivacyOperationOutput"];
                };
            };
        };
    };
    reading_privacy_operations_command_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 reader data operation 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PrivacyCommandInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PrivacyCommandInputRequest"];
                "multipart/form-data": components["schemas"]["PrivacyCommandInputRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrivacyOperationOutput"];
                };
            };
        };
    };
    reading_privacy_operations_download_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 reader data operation 的 UUID 字符串。 */
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    reading_progress_list: {
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
                    "application/json": components["schemas"]["PaginatedReadingProgressList"];
                };
            };
        };
    };
    reading_progress_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReadingProgressRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ReadingProgressRequest"];
                "multipart/form-data": components["schemas"]["ReadingProgressRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadingProgress"];
                };
            };
        };
    };
    reading_progress_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 reading progress 的 UUID 字符串。 */
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
                    "application/json": components["schemas"]["ReadingProgress"];
                };
            };
        };
    };
    reading_progress_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 reading progress 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReadingProgressRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["ReadingProgressRequest"];
                "multipart/form-data": components["schemas"]["ReadingProgressRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadingProgress"];
                };
            };
        };
    };
    reading_progress_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 reading progress 的 UUID 字符串。 */
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
    reading_progress_partial_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 reading progress 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PatchedReadingProgressRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["PatchedReadingProgressRequest"];
                "multipart/form-data": components["schemas"]["PatchedReadingProgressRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadingProgress"];
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
                /**
                 * @description * `all` - all
                 *     * `concept` - concept
                 *     * `understanding` - understanding
                 *     * `question` - question
                 *     * `method` - method
                 *     * `observation` - observation
                 *     * `contradiction` - contradiction
                 */
                kind?: "all" | "concept" | "understanding" | "question" | "method" | "observation" | "contradiction";
                /**
                 * @description * `updated_at` - updated_at
                 *     * `newest` - newest
                 */
                order?: "updated_at" | "newest";
                /** @description 用于排序结果的字段。 */
                ordering?: string;
                /** @description 分页结果集中的页码。 */
                page?: number;
                q?: string;
                /** @description 搜索关键词。 */
                search?: string;
                /**
                 * @description * `all` - all
                 *     * `available` - available
                 *     * `updated` - updated
                 *     * `unavailable` - unavailable
                 *     * `no_source` - no_source
                 */
                source_status?: "all" | "available" | "updated" | "unavailable" | "no_source";
                /**
                 * @description * `all` - all
                 *     * `proposed` - proposed
                 *     * `confirmed` - confirmed
                 *     * `ignored` - ignored
                 */
                state?: "all" | "proposed" | "confirmed" | "ignored";
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
                    "application/json": components["schemas"]["PaginatedMemoryListOutputList"];
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
    reading_research_memories_usage_retrieve: {
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    reading_research_memories_usage_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 标识此 research memory 的 UUID 字符串。 */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MemoryUsageInputRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["MemoryUsageInputRequest"];
                "multipart/form-data": components["schemas"]["MemoryUsageInputRequest"];
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
                /**
                 * @description * `all` - all
                 *     * `search` - search
                 *     * `counterargument` - counterargument
                 */
                mode?: "all" | "search" | "counterargument";
                /**
                 * @description * `oldest` - oldest
                 *     * `newest` - newest
                 */
                order?: "oldest" | "newest";
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
    reading_saved_knowledge_retrieve: {
        parameters: {
            query?: {
                request_id?: string;
            };
            header: {
                "X-Reader-Owner": string;
            };
            path: {
                node_id: string;
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
                    "application/json": components["schemas"]["KnowledgeSaveOutput"];
                };
            };
        };
    };
    reading_saved_knowledge_create: {
        parameters: {
            query?: never;
            header: {
                "X-Reader-Owner": string;
            };
            path: {
                node_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KnowledgeSaveCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["KnowledgeSaveCommandRequest"];
                "multipart/form-data": components["schemas"]["KnowledgeSaveCommandRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeSaveOutput"];
                };
            };
        };
    };
    reading_search_records_retrieve: {
        parameters: {
            query: {
                owner_id: string;
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
                    "application/json": components["schemas"]["SearchRecordsPage"];
                };
            };
        };
    };
    reading_source_follows_list: {
        parameters: {
            query?: {
                page?: number;
                path?: string;
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
                    "application/json": components["schemas"]["SourceFollowsPage"];
                };
            };
        };
    };
    reading_source_follows_create: {
        parameters: {
            query?: never;
            header: {
                "X-Reader-Owner": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SourceFollowCommandRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["SourceFollowCommandRequest"];
                "multipart/form-data": components["schemas"]["SourceFollowCommandRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceFollowOutput"];
                };
            };
        };
    };
    reading_source_follows_retrieve: {
        parameters: {
            query?: {
                history_page?: number;
            };
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
                    "application/json": components["schemas"]["SourceFollowOutput"];
                };
            };
        };
    };
    reading_source_status_retrieve: {
        parameters: {
            query: {
                path: string;
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
                    "application/json": components["schemas"]["PublicSourceStatus"];
                };
            };
        };
    };
}

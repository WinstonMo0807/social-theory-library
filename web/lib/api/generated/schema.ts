/** Generated from DRF/OpenAPI. Do not edit by hand. */
export interface paths {
    "/api/catalog/admin/catalog-field-contracts/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["catalog_field_contracts_retrieve"];
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
        post: operations["cataloging_sessions_create"];
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
        post: operations["cataloging_sessions_abandon_create"];
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
        post: operations["cataloging_sessions_candidates_decision_create"];
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
        post: operations["cataloging_sessions_metadata_decision_create"];
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
        post: operations["cataloging_sessions_metadata_import_create"];
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
        ApiError: {
            code: string;
            message: string;
            field: string | null;
            severity: components["schemas"]["SeverityEnum"];
            details: unknown;
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
            readonly source_type: components["schemas"]["SourceTypeEnum"];
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
            source_type: components["schemas"]["SourceTypeEnum"];
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
         * @description * `book` - 图书
         *     * `journal_article` - 期刊论文
         *     * `journal_issue` - 整期期刊
         *     * `thesis` - 学位论文
         *     * `report` - 研究报告
         * @enum {string}
         */
        DocumentTypeEnum: "book" | "journal_article" | "journal_issue" | "thesis" | "report";
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
         * @description * `blocking` - blocking
         *     * `warning` - warning
         *     * `info` - info
         * @enum {string}
         */
        SeverityEnum: "blocking" | "warning" | "info";
        /**
         * @description * `upload` - 上传文献
         *     * `manual` - 手工编目
         *     * `import` - 导入书目
         *     * `existing` - 编辑馆藏
         * @enum {string}
         */
        SourceTypeEnum: "upload" | "manual" | "import" | "existing";
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
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    catalog_field_contracts_retrieve: {
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
    cataloging_sessions_create: {
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
    cataloging_sessions_abandon_create: {
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
    cataloging_sessions_candidates_decision_create: {
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
    cataloging_sessions_metadata_decision_create: {
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
    cataloging_sessions_metadata_import_create: {
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
}

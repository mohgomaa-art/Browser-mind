"""Capability Taxonomy — 30-category map of expected web capabilities.

Each key is a SITE_CATEGORY string from site_registry.py.
Values are lists of capability_key strings that the explorer should
attempt to discover / observe on sites in that category.

These keys are used to:
  1. Pre-seed CapabilityHypothesisStore before a mission starts
     (CapabilityHypothesisStore.seed_from_taxonomy)
  2. Guide ExplorerPolicy toward high-value affordance patterns
  3. Structure cross-site synthesis reports
"""
from __future__ import annotations
from typing import Dict, List

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

CAPABILITY_TAXONOMY: Dict[str, List[str]] = {

    # 1. Social Networks
    "social": [
        "oauth_sso_login",
        "infinite_scroll_dom",
        "state_mutation_like",
        "state_mutation_share",
        "state_mutation_repost",
        "rich_text_composition",
        "multi_part_media_upload",
        "social_graph_follow",
        "social_graph_followers",
        "algorithmic_feed_reset",
        "websocket_live_indicator",
        "async_messaging_inbox",
        "privacy_control_config",
        "content_moderation_report",
        "ephemeral_story_consumption",
        "hashtag_topology_map",
    ],

    # 2. Forums & Communities
    "forum": [
        "hierarchical_thread_parse",
        "tree_comment_traversal",
        "karma_reputation_vote",
        "bbcode_markdown_generate",
        "pagination_state_management",
        "nested_quote_mechanism",
        "sub_community_discovery",
        "flair_tag_filter",
        "time_sort_new_top_hot",
        "anonymous_vs_auth_session",
        "wiki_sticky_extract",
        "moderation_privilege_action",
    ],

    # 3. Chat & Real-Time Communication
    "chat": [
        "realtime_dom_mutation_observe",
        "websocket_handshake_analysis",
        "channel_workspace_traversal",
        "rbac_role_permission_map",
        "thread_context_isolation",
        "file_attachment_stream",
        "webrtc_voice_video_hook",
        "slash_command_execute",
        "bot_webhook_generate",
        "message_read_receipt",
        "push_notification_service_worker",
        "emoji_reaction_matrix",
    ],

    # 4. Video Platforms
    "video": [
        "html5_player_event_hook",
        "hls_dash_manifest_parse",
        "video_quality_switch",
        "closed_caption_vtt_extract",
        "live_chat_websocket_parse",
        "timestamp_chapter_navigate",
        "playlist_queue_manage",
        "creator_dashboard_analytics",
        "video_upload_pipeline",
        "ad_sponsorship_detect",
    ],

    # 5. Audio Platforms
    "audio": [
        "audio_context_background",
        "audio_blob_intercept",
        "playlist_array_manipulate",
        "radio_station_generate",
        "drm_handshake_observe",
        "podcast_rss_ingest",
        "seek_bar_canvas_interact",
        "offline_sync_trigger",
        "lyrics_sync_parse",
        "artist_graph_traverse",
    ],

    # 6. Image Platforms
    "image": [
        "high_res_asset_extract",
        "exif_metadata_parse",
        "watermark_detect",
        "masonry_grid_traverse",
        "tag_cloud_map",
        "collection_moodboard_manage",
        "canvas_webgl_render_intercept",
        "reverse_image_search_trigger",
        "license_copyright_parse",
        "bulk_batch_upload",
    ],

    # 7. News & Publishing
    "news": [
        "paywall_bypass_attempt",
        "reader_mode_dom_simplify",
        "schema_org_jsonld_parse",
        "newsletter_subscribe_automate",
        "author_archive_traverse",
        "inline_citation_follow",
        "print_css_emulate",
        "comment_disqus_interact",
        "live_blog_poll_intercept",
        "rss_endpoint_discover",
    ],

    # 8. Blogs & Personal Sites
    "blog": [
        "chronological_archive_navigate",
        "tag_category_taxonomy_map",
        "ssg_structure_predict",
        "rss_atom_feed_detect",
        "webmention_trackback",
        "search_endpoint_fuzz",
        "comment_form_submit",
        "local_storage_pref_manipulate",
        "theme_template_identify",
    ],

    # 9. E-Commerce
    "ecommerce": [
        "multi_facet_filter",
        "dynamic_pricing_sku_track",
        "cart_state_manipulate",
        "checkout_pipeline_traverse",
        "payment_gateway_identify",
        "review_sentiment_extract",
        "inventory_stock_poll",
        "shipping_calculator_spoof",
        "promo_code_validate",
        "wishlist_graph_build",
        "recommendation_scrape",
    ],

    # 10. Marketplaces (Services/P2P)
    "marketplace": [
        "two_sided_graph_discover",
        "bid_offer_submit",
        "escrow_simulate",
        "calendar_availability_parse",
        "reputation_score_calculate",
        "dispute_resolution_navigate",
        "geolocation_radius_search",
        "realtime_negotiation_chat",
        "listing_draft_publish",
        "identity_verification_wall",
    ],

    # 11. SaaS Applications
    "saas": [
        "canvas_webgl_extract",
        "crdt_state_sync",
        "multi_tenant_auth",
        "workflow_automation_generate",
        "api_key_token_generate",
        "drag_drop_datatransfer",
        "export_import_pipeline",
        "role_permission_alter",
        "billing_subscription_traverse",
        "audit_log_scrape",
    ],

    # 12. Productivity Systems
    "productivity": [
        "kanban_board_drag_drop",
        "gantt_timeline_extract",
        "custom_field_mutate",
        "sprint_backlog_velocity",
        "bidirectional_link_navigate",
        "block_level_dom_edit",
        "time_tracking_hook",
        "dependency_graph_build",
        "webhook_trigger_config",
        "indexeddb_offline_extract",
    ],

    # 13. Knowledge Systems
    "knowledge": [
        "sparql_endpoint_query",
        "knowledge_graph_triplet_extract",
        "version_history_diff",
        "wysiwyg_markdown_translate",
        "namespace_traverse",
        "transclusion_template_resolve",
        "reference_citation_validate",
        "broken_link_map",
        "taxonomy_ontology_parse",
    ],

    # 14. Developer Platforms
    "dev": [
        "git_protocol_http",
        "commit_tree_navigate",
        "pull_request_diff_parse",
        "ci_cd_log_stream",
        "web_ide_monaco_interact",
        "container_registry_poll",
        "jupyter_cell_execute",
        "fork_clone_trigger",
        "issue_state_mutate",
        "secret_env_inject_flow",
    ],

    # 15. Package Registries
    "registry": [
        "dependency_tree_resolve",
        "semver_constraint_parse",
        "cve_vulnerability_map",
        "checksum_hash_validate",
        "tarball_blob_extract",
        "readme_docs_render",
        "publish_deprecate_flow",
        "maintainer_graph_traverse",
        "download_stat_poll",
    ],

    # 16. Cloud Platforms
    "cloud": [
        "iam_policy_parse",
        "resource_provision_workflow",
        "billing_dashboard_scrape",
        "dns_record_mutate",
        "firewall_security_group_config",
        "serverless_log_tail",
        "storage_bucket_traverse",
        "kubernetes_dashboard_query",
        "vpc_topology_map",
        "ssh_key_inject_flow",
    ],

    # 17. Authentication Systems
    "auth": [
        "oauth2_oidc_redirect_track",
        "jwt_token_extract_decode",
        "saml_assertion_intercept",
        "magic_link_email_poll",
        "mfa_totp_seed_inject",
        "webauthn_passkey_emulate",
        "session_cookie_replay",
        "password_reset_pipeline",
        "social_login_shadow_dom",
        "captcha_token_intercept",
    ],

    # 18. Email Systems
    "email": [
        "imap_pop3_web_emulate",
        "pgp_gpg_keyring_dom",
        "thread_collapse_expand",
        "spam_filter_config",
        "attachment_blob_render",
        "html_email_sanitize",
        "contact_book_sync",
        "alias_disposable_generate",
        "snooze_schedule_trigger",
    ],

    # 19. Government Portals
    "government": [
        "legacy_mainframe_wrapper_navigate",
        "multi_page_session_timeout_circumvent",
        "pdf_form_fill_generate",
        "identity_document_upload",
        "captcha_solve_capability",
        "soap_xml_endpoint_query",
        "appointment_calendar_matrix",
        "digital_signature_verify",
        "bureaucratic_form_taxonomy",
    ],

    # 20. Banking & Finance
    "finance": [
        "open_banking_api_aggregate",
        "transaction_ledger_paginate",
        "statement_pdf_download",
        "iban_routing_validate",
        "virtual_card_generate",
        "fraud_verification_hurdle",
        "exchange_rate_poll",
        "wire_transfer_authorize",
        "dispute_chargeback_form",
    ],

    # 21. Crypto Platforms
    "crypto": [
        "web3_provider_inject",
        "smart_contract_abi_decode",
        "signature_request_intercept",
        "gas_fee_poll_adjust",
        "orderbook_canvas_parse",
        "liquidity_pool_mutate",
        "token_swap_route_simulate",
        "nft_metadata_ipfs_resolve",
        "blockchain_explorer_trace",
        "seed_phrase_vault_interact",
    ],

    # 22. Education Platforms
    "education": [
        "scorm_package_navigate",
        "lms_assignment_upload",
        "video_lecture_progress",
        "quiz_dom_emulate",
        "peer_review_form_manipulate",
        "certificate_pdf_generate",
        "syllabus_curriculum_traverse",
        "flashcard_spaced_repetition",
        "proctoring_sandbox_evasion",
    ],

    # 23. Job Platforms
    "jobs": [
        "ats_field_map",
        "resume_parser_emulate",
        "one_click_apply_hook",
        "cover_letter_inject",
        "salary_range_extract",
        "company_review_aggregate",
        "assessment_skill_test_ui",
        "interview_scheduler_integrate",
        "offer_docusign_pipeline",
    ],

    # 24. CMS & Site Builders
    "cms": [
        "wysiwyg_block_manipulate",
        "taxonomy_routing_configure",
        "plugin_extension_install",
        "theme_css_editor_interact",
        "media_library_manage",
        "seo_metadata_configure",
        "headless_api_generate",
        "draft_publish_revision",
        "webhook_generation_ui",
    ],

    # 25. Search Engines
    "search": [
        "serp_dom_parse",
        "knowledge_graph_extract",
        "dork_query_inject",
        "pagination_infinite_scroll",
        "image_video_tab_navigate",
        "shopping_feed_parse",
        "map_local_pack_extract",
        "autocomplete_api_intercept",
        "cache_archive_follow",
    ],

    # 26. Maps & Local Discovery
    "maps": [
        "tile_vector_canvas_query",
        "geocode_reverse_geocode",
        "routing_polyline_extract",
        "place_poi_card_scrape",
        "review_paginate_filter",
        "operating_hours_parse",
        "street_view_webgl_navigate",
        "menu_cart_state",
        "delivery_fee_calculate",
    ],

    # 27. Travel Systems
    "travel": [
        "gds_interface_emulate",
        "multi_city_routing_input",
        "fare_calendar_matrix_parse",
        "dynamic_pricing_scarcity",
        "seat_map_canvas_svg_interact",
        "baggage_ancillary_toggle",
        "itinerary_pnr_retrieve",
        "loyalty_point_calculate",
        "boarding_pass_qr_extract",
    ],

    # 28. AI Platforms
    "ai": [
        "sse_stream_parse",
        "context_window_manage",
        "prompt_injection_detect",
        "artifact_code_execute",
        "canvas_image_mask_edit",
        "voice_webrtc_hook",
        "custom_agent_create",
        "api_key_rate_limit_poll",
        "model_selection_mutate",
        "temperature_slider_interact",
    ],

    # 29. Dashboards & Admin Panels
    "dashboard": [
        "timeseries_chart_extract",
        "promql_sql_query_input",
        "widget_drag_drop_layout",
        "alert_threshold_configure",
        "log_aggregation_traverse",
        "datasource_connect_flow",
        "user_role_provision",
        "csv_excel_export_trigger",
        "api_interactive_shell",
        "dark_mode_theme_toggle",
    ],

    # 30. Unknown Web (Frontier)
    "frontier": [
        "unknown_affordance_hypothesize",
        "shadow_dom_penetrate",
        "recursive_iframe_switch",
        "undoc_api_endpoint_infer",
        "raw_canvas_webgl_interact",
        "custom_event_listener_detect",
        "fuzzy_unlabeled_input_match",
        "visual_heuristic_ui_map",
        "webpack_chunk_reverse_engineer",
        "dynamic_payload_reconstruct",
        "heuristic_pagination_predict",
        "obfuscated_state_track",
        "legacy_activex_workaround",
        "dead_link_error_path_recover",
        "workflow_reversal_infer",
    ],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def capabilities_for_category(category: str) -> List[str]:
    """Return capability keys for a site category (empty list if unknown)."""
    return CAPABILITY_TAXONOMY.get(category, [])


def all_capability_keys() -> List[str]:
    """Flat deduplicated list of all capability keys across all categories."""
    seen: set = set()
    result = []
    for caps in CAPABILITY_TAXONOMY.values():
        for c in caps:
            if c not in seen:
                seen.add(c)
                result.append(c)
    return result


def categories_for_capability(capability_key: str) -> List[str]:
    """Which categories surface this capability."""
    return [
        cat for cat, caps in CAPABILITY_TAXONOMY.items()
        if capability_key in caps
    ]

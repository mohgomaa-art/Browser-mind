"""Site Registry — 500-site corpus for autonomous exploration campaigns.

30 categories aligned with the BrowserMind Capability Taxonomy.
Each SiteSpec carries:
  - difficulty 1-5  (1=trivial test site, 5=heavily bot-protected)
  - capability_hints  (capability_key strings from capability_taxonomy.py)
  - requires_login  (most affordances gated behind auth)

Usage:
    from browsermind_core.mission.site_registry import (
        resolve_site, list_sites, SITE_CATEGORIES, site_keys_for_campaign,
    )
    env = resolve_site("github")
    social = list_sites(category="social")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from browsermind_core.runtime.environment_registry import EnvironmentEntry


# 30 categories matching capability_taxonomy.py keys
SITE_CATEGORIES: List[str] = [
    "social",       # 1  Social Networks
    "forum",        # 2  Forums & Communities
    "chat",         # 3  Chat & Real-Time Communication
    "video",        # 4  Video Platforms
    "audio",        # 5  Audio Platforms
    "image",        # 6  Image Platforms
    "news",         # 7  News & Publishing
    "blog",         # 8  Blogs & Personal Sites
    "ecommerce",    # 9  E-Commerce
    "marketplace",  # 10 Marketplaces (Services/P2P)
    "saas",         # 11 SaaS Applications
    "productivity", # 12 Productivity Systems
    "knowledge",    # 13 Knowledge Systems
    "dev",          # 14 Developer Platforms
    "registry",     # 15 Package Registries
    "cloud",        # 16 Cloud Platforms
    "auth",         # 17 Authentication Systems
    "email",        # 18 Email Systems
    "government",   # 19 Government Portals
    "finance",      # 20 Banking & Finance
    "crypto",       # 21 Crypto Platforms
    "education",    # 22 Education Platforms
    "jobs",         # 23 Job Platforms
    "cms",          # 24 CMS & Site Builders
    "search",       # 25 Search Engines
    "maps",         # 26 Maps & Local Discovery
    "travel",       # 27 Travel Systems
    "ai",           # 28 AI Platforms
    "dashboard",    # 29 Dashboards & Admin Panels
    "frontier",     # 30 Unknown Web (Frontier / Capability Discovery)
]


@dataclass
class SiteSpec:
    key: str
    start_url: str
    category: str
    difficulty: int                          # 1=easy, 5=hard
    description: str = ""
    login_url: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    shares_auth_with: Optional[str] = None
    requires_login: bool = False
    protected: bool = False                  # True = can't automate login; needs human session
    capability_hints: List[str] = field(default_factory=list)

    def to_env_entry(self) -> EnvironmentEntry:
        return EnvironmentEntry(
            key=self.key,
            start_url=self.start_url,
            aliases=self.aliases,
            family=self.category,
            login_url=self.login_url,
            description=self.description,
        )


# ---------------------------------------------------------------------------
# Registry — 500 sites across 30 categories
# ---------------------------------------------------------------------------

_SITES: List[SiteSpec] = [

    # ── 1. SOCIAL NETWORKS ────────────────────────────────────────────────
    SiteSpec("twitter",        "https://twitter.com/",                 "social", 4, "Twitter/X",             "https://twitter.com/i/flow/login",   ["x", "x.com"],    protected=True, capability_hints=["infinite_scroll_dom","state_mutation_like","state_mutation_repost","hashtag_topology_map"]),
    SiteSpec("facebook",       "https://www.facebook.com/",            "social", 5, "Facebook",              "https://www.facebook.com/",          ["fb"],            protected=True, capability_hints=["oauth_sso_login","social_graph_follow","algorithmic_feed_reset","ephemeral_story_consumption"]),
    SiteSpec("instagram",      "https://www.instagram.com/",           "social", 5, "Instagram",             requires_login=True, shares_auth_with="facebook",       protected=True, capability_hints=["multi_part_media_upload","infinite_scroll_dom","ephemeral_story_consumption"]),
    SiteSpec("linkedin",       "https://www.linkedin.com/",            "social", 3, "LinkedIn",              "https://www.linkedin.com/login",                        protected=True, capability_hints=["oauth_sso_login","social_graph_follow","async_messaging_inbox"]),
    SiteSpec("tiktok",         "https://www.tiktok.com/",              "social", 4, "TikTok",                                                                         protected=True, capability_hints=["infinite_scroll_dom","multi_part_media_upload","algorithmic_feed_reset"]),
    SiteSpec("pinterest",      "https://www.pinterest.com/",           "social", 3, "Pinterest",             "https://www.pinterest.com/login/",                      capability_hints=["infinite_scroll_dom","state_mutation_like","social_graph_follow"]),
    SiteSpec("mastodon",       "https://mastodon.social/",             "social", 2, "Mastodon",              "https://mastodon.social/auth/sign_in",                  capability_hints=["state_mutation_repost","hashtag_topology_map","oauth_sso_login"]),
    SiteSpec("bluesky",        "https://bsky.app/",                    "social", 2, "Bluesky",               "https://bsky.app/",                                     capability_hints=["infinite_scroll_dom","state_mutation_like","social_graph_follow"]),
    SiteSpec("threads",        "https://www.threads.net/",             "social", 3, "Threads",               requires_login=True, shares_auth_with="instagram",       protected=True, capability_hints=["infinite_scroll_dom","state_mutation_like"]),
    SiteSpec("snapchat_web",   "https://web.snapchat.com/",            "social", 4, "Snapchat Web",          requires_login=True,                                     protected=True, capability_hints=["ephemeral_story_consumption","async_messaging_inbox"]),
    SiteSpec("vk",             "https://vk.com/",                      "social", 3, "VKontakte",             "https://vk.com/login",                                  capability_hints=["social_graph_follow","state_mutation_like","infinite_scroll_dom"]),
    SiteSpec("xing",           "https://www.xing.com/",                "social", 2, "Xing",                  "https://www.xing.com/login",                            capability_hints=["social_graph_follow","oauth_sso_login"]),
    SiteSpec("mewe",           "https://mewe.com/",                    "social", 2, "MeWe",                  requires_login=True,                                     capability_hints=["social_graph_follow","state_mutation_like"]),
    SiteSpec("gettr",          "https://gettr.com/",                   "social", 2, "GETTR",                 "https://gettr.com/login",                               capability_hints=["infinite_scroll_dom","state_mutation_like"]),
    SiteSpec("truth_social",   "https://truthsocial.com/",             "social", 3, "Truth Social",          "https://truthsocial.com/login",                         capability_hints=["infinite_scroll_dom","state_mutation_repost"]),
    SiteSpec("gab",            "https://gab.com/",                     "social", 3, "Gab",                   "https://gab.com/auth/sign_in",                          capability_hints=["infinite_scroll_dom","state_mutation_like"]),
    SiteSpec("ello",           "https://ello.co/",                     "social", 2, "Ello",                  "https://ello.co/enter",                                 capability_hints=["infinite_scroll_dom","social_graph_follow"]),

    # ── 2. FORUMS & COMMUNITIES ───────────────────────────────────────────
    SiteSpec("reddit",         "https://www.reddit.com/",              "forum",  3, "Reddit",                "https://www.reddit.com/login/",                         capability_hints=["hierarchical_thread_parse","karma_reputation_vote","time_sort_new_top_hot","flair_tag_filter"]),
    SiteSpec("stackoverflow",  "https://stackoverflow.com/",           "forum",  2, "Stack Overflow",        aliases=["so"],                                          capability_hints=["hierarchical_thread_parse","karma_reputation_vote","tree_comment_traversal"]),
    SiteSpec("quora",          "https://www.quora.com/",               "forum",  3, "Quora",                                                                          capability_hints=["hierarchical_thread_parse","anonymous_vs_auth_session","pagination_state_management"]),
    SiteSpec("hacker_news",    "https://news.ycombinator.com/",        "forum",  1, "Hacker News",           "https://news.ycombinator.com/login", ["hn"],            capability_hints=["hierarchical_thread_parse","karma_reputation_vote","time_sort_new_top_hot"]),
    SiteSpec("lobsters",       "https://lobste.rs/",                   "forum",  1, "Lobsters",              "https://lobste.rs/login",                               capability_hints=["hierarchical_thread_parse","karma_reputation_vote","flair_tag_filter"]),
    SiteSpec("dev_to",         "https://dev.to/",                      "forum",  2, "DEV.to",                "https://dev.to/enter",                                  capability_hints=["tree_comment_traversal","karma_reputation_vote","flair_tag_filter"]),
    SiteSpec("lemmy",          "https://lemmy.world/",                 "forum",  2, "Lemmy",                 "https://lemmy.world/login",                             capability_hints=["sub_community_discovery","karma_reputation_vote","hierarchical_thread_parse"]),
    SiteSpec("tildes",         "https://tildes.net/",                  "forum",  1, "Tildes",                "https://tildes.net/login",                              capability_hints=["hierarchical_thread_parse","flair_tag_filter"]),
    SiteSpec("discourse_meta", "https://meta.discourse.org/",          "forum",  2, "Discourse (Meta)",      "https://meta.discourse.org/session/email-login",        capability_hints=["hierarchical_thread_parse","wiki_sticky_extract","bbcode_markdown_generate"]),
    SiteSpec("myanimelist",    "https://myanimelist.net/",             "forum",  2, "MyAnimeList",           "https://myanimelist.net/login.php",                     capability_hints=["karma_reputation_vote","flair_tag_filter","pagination_state_management"]),
    SiteSpec("fandom",         "https://www.fandom.com/",              "forum",  2, "Fandom",                                                                         capability_hints=["wiki_sticky_extract","nested_quote_mechanism","sub_community_discovery"]),
    SiteSpec("xda_developers", "https://xda-developers.com/",          "forum",  2, "XDA Developers",        "https://forum.xda-developers.com/login/",               capability_hints=["hierarchical_thread_parse","bbcode_markdown_generate"]),
    SiteSpec("resetera",       "https://www.resetera.com/",            "forum",  2, "ResetEra",              "https://www.resetera.com/login/",                       capability_hints=["hierarchical_thread_parse","bbcode_markdown_generate","pagination_state_management"]),
    SiteSpec("4chan",          "https://boards.4chan.org/g/",          "forum",  2, "4chan /g/",                                                                       capability_hints=["anonymous_vs_auth_session","hierarchical_thread_parse"]),
    SiteSpec("mumsnet",        "https://www.mumsnet.com/talk",         "forum",  2, "Mumsnet",               "https://www.mumsnet.com/login",                         capability_hints=["hierarchical_thread_parse","pagination_state_management"]),
    SiteSpec("stackexchange",  "https://stackexchange.com/",           "forum",  2, "StackExchange",         aliases=["se"],                                          capability_hints=["hierarchical_thread_parse","karma_reputation_vote","sub_community_discovery"]),

    # ── 3. CHAT & REAL-TIME COMMUNICATION ────────────────────────────────
    SiteSpec("discord",        "https://discord.com/",                 "chat",   3, "Discord",               "https://discord.com/login",                             capability_hints=["realtime_dom_mutation_observe","websocket_handshake_analysis","channel_workspace_traversal","slash_command_execute"]),
    SiteSpec("slack",          "https://slack.com/",                   "chat",   3, "Slack",                 "https://slack.com/signin",                              capability_hints=["channel_workspace_traversal","rbac_role_permission_map","thread_context_isolation","bot_webhook_generate"]),
    SiteSpec("teams_web",      "https://teams.microsoft.com/",         "chat",   4, "Microsoft Teams Web",   requires_login=True,                                     capability_hints=["channel_workspace_traversal","rbac_role_permission_map","webrtc_voice_video_hook"]),
    SiteSpec("telegram",       "https://web.telegram.org/",            "chat",   3, "Telegram Web",                                                                   capability_hints=["realtime_dom_mutation_observe","channel_workspace_traversal","file_attachment_stream"]),
    SiteSpec("matrix",         "https://app.element.io/",              "chat",   2, "Matrix / Element",      "https://app.element.io/#/login",                        capability_hints=["websocket_handshake_analysis","channel_workspace_traversal","rbac_role_permission_map"]),
    SiteSpec("rocketchat",     "https://open.rocket.chat/",            "chat",   2, "Rocket.Chat",           "https://open.rocket.chat/login",                        capability_hints=["channel_workspace_traversal","bot_webhook_generate","slash_command_execute"]),
    SiteSpec("mattermost",     "https://mattermost.com/demo/",         "chat",   2, "Mattermost",            requires_login=True,                                     capability_hints=["channel_workspace_traversal","webhook_trigger_config"]),
    SiteSpec("zulip",          "https://zulip.com/",                   "chat",   2, "Zulip",                 "https://app.zulip.org/login/",                          capability_hints=["thread_context_isolation","channel_workspace_traversal"]),
    SiteSpec("guilded",        "https://www.guilded.gg/",              "chat",   2, "Guilded",               "https://www.guilded.gg/login",                          capability_hints=["channel_workspace_traversal","slash_command_execute","emoji_reaction_matrix"]),
    SiteSpec("google_chat",    "https://chat.google.com/",             "chat",   3, "Google Chat",           requires_login=True, shares_auth_with="google",          protected=True, capability_hints=["thread_context_isolation","bot_webhook_generate"]),
    SiteSpec("whatsapp_web",   "https://web.whatsapp.com/",            "chat",   4, "WhatsApp Web",          requires_login=True,                                     protected=True, capability_hints=["realtime_dom_mutation_observe","message_read_receipt"]),
    SiteSpec("wire",           "https://app.wire.com/",                "chat",   2, "Wire",                  "https://app.wire.com/auth/",                            capability_hints=["file_attachment_stream","message_read_receipt"]),
    SiteSpec("twist",          "https://twist.com/",                   "chat",   2, "Twist",                 "https://twist.com/login",                               capability_hints=["thread_context_isolation","channel_workspace_traversal"]),
    SiteSpec("groupme",        "https://web.groupme.com/",             "chat",   2, "GroupMe",               "https://web.groupme.com/signin",                        capability_hints=["realtime_dom_mutation_observe","emoji_reaction_matrix"]),

    # ── 4. VIDEO PLATFORMS ────────────────────────────────────────────────
    SiteSpec("youtube",        "https://www.youtube.com/",             "video",  3, "YouTube",               "https://accounts.google.com/", shares_auth_with="google", protected=True, capability_hints=["html5_player_event_hook","hls_dash_manifest_parse","live_chat_websocket_parse","playlist_queue_manage"]),
    SiteSpec("twitch",         "https://www.twitch.tv/",               "video",  3, "Twitch",                "https://www.twitch.tv/login",                           capability_hints=["live_chat_websocket_parse","hls_dash_manifest_parse","creator_dashboard_analytics"]),
    SiteSpec("kick",           "https://kick.com/",                    "video",  2, "Kick",                  "https://kick.com/login",                                capability_hints=["live_chat_websocket_parse","hls_dash_manifest_parse"]),
    SiteSpec("vimeo",          "https://vimeo.com/",                   "video",  2, "Vimeo",                 "https://vimeo.com/log_in",                              capability_hints=["html5_player_event_hook","closed_caption_vtt_extract","video_upload_pipeline"]),
    SiteSpec("rumble",         "https://rumble.com/",                  "video",  2, "Rumble",                "https://rumble.com/login",                              capability_hints=["html5_player_event_hook","hls_dash_manifest_parse"]),
    SiteSpec("dailymotion",    "https://www.dailymotion.com/",         "video",  2, "Dailymotion",           "https://www.dailymotion.com/signin",                    capability_hints=["html5_player_event_hook","closed_caption_vtt_extract"]),
    SiteSpec("bilibili",       "https://www.bilibili.com/",            "video",  3, "Bilibili",              "https://passport.bilibili.com/login",                   capability_hints=["hls_dash_manifest_parse","live_chat_websocket_parse","html5_player_event_hook"]),
    SiteSpec("nebula",         "https://nebula.tv/",                   "video",  2, "Nebula",                "https://nebula.tv/login",                               capability_hints=["html5_player_event_hook","closed_caption_vtt_extract"]),
    SiteSpec("odysee",         "https://odysee.com/",                  "video",  2, "Odysee",                "https://odysee.com/$/signin",                           capability_hints=["html5_player_event_hook","hls_dash_manifest_parse"]),
    SiteSpec("vevo",           "https://www.vevo.com/",                "video",  2, "Vevo",                  capability_hints=["html5_player_event_hook","ad_sponsorship_detect"]),
    SiteSpec("wistia",         "https://wistia.com/",                  "video",  2, "Wistia",                "https://fast.wistia.com/",                              capability_hints=["html5_player_event_hook","video_quality_switch"]),
    SiteSpec("peertu",         "https://joinpeertube.org/",            "video",  1, "PeerTube",              capability_hints=["hls_dash_manifest_parse","html5_player_event_hook"]),
    SiteSpec("trovo",          "https://trovo.live/",                  "video",  2, "Trovo",                 "https://trovo.live/account/login",                      capability_hints=["live_chat_websocket_parse","hls_dash_manifest_parse"]),
    SiteSpec("afreecatv",      "https://afreecatv.com/",               "video",  3, "AfreecaTV",             requires_login=True,                                     capability_hints=["live_chat_websocket_parse","html5_player_event_hook"]),

    # ── 5. AUDIO PLATFORMS ───────────────────────────────────────────────
    SiteSpec("spotify",        "https://open.spotify.com/",            "audio",  3, "Spotify",               "https://accounts.spotify.com/en/login",                 capability_hints=["audio_context_background","playlist_array_manipulate","drm_handshake_observe"]),
    SiteSpec("soundcloud",     "https://soundcloud.com/",              "audio",  2, "SoundCloud",            "https://soundcloud.com/signin",                         capability_hints=["audio_context_background","seek_bar_canvas_interact","artist_graph_traverse"]),
    SiteSpec("bandcamp",       "https://bandcamp.com/",                "audio",  2, "Bandcamp",                                                                       capability_hints=["audio_blob_intercept","artist_graph_traverse"]),
    SiteSpec("tidal",          "https://tidal.com/",                   "audio",  3, "Tidal",                 "https://login.tidal.com/",                              capability_hints=["audio_context_background","drm_handshake_observe","lyrics_sync_parse"]),
    SiteSpec("deezer",         "https://www.deezer.com/",              "audio",  2, "Deezer",                "https://www.deezer.com/en/login",                       capability_hints=["audio_context_background","playlist_array_manipulate","lyrics_sync_parse"]),
    SiteSpec("pandora",        "https://www.pandora.com/",             "audio",  2, "Pandora",               "https://www.pandora.com/account/sign-in",               capability_hints=["radio_station_generate","audio_context_background"]),
    SiteSpec("mixcloud",       "https://www.mixcloud.com/",            "audio",  2, "Mixcloud",              "https://www.mixcloud.com/login/",                       capability_hints=["audio_context_background","seek_bar_canvas_interact"]),
    SiteSpec("audiomack",      "https://audiomack.com/",               "audio",  2, "Audiomack",             "https://audiomack.com/sign-in",                         capability_hints=["audio_blob_intercept","artist_graph_traverse"]),
    SiteSpec("iheartradio",    "https://www.iheart.com/",              "audio",  2, "iHeartRadio",           "https://www.iheart.com/on/logon/",                      capability_hints=["radio_station_generate","podcast_rss_ingest"]),
    SiteSpec("tunein",         "https://tunein.com/",                  "audio",  2, "TuneIn",                capability_hints=["radio_station_generate","podcast_rss_ingest"]),
    SiteSpec("siriusxm",       "https://www.siriusxm.com/",            "audio",  3, "SiriusXM",              "https://player.siriusxm.com/login",                     capability_hints=["audio_context_background","drm_handshake_observe"]),
    SiteSpec("jiosaavn",       "https://www.jiosaavn.com/",            "audio",  2, "JioSaavn",                                                                       capability_hints=["audio_context_background","lyrics_sync_parse"]),
    SiteSpec("anghami",        "https://www.anghami.com/",             "audio",  2, "Anghami",               "https://www.anghami.com/login",                         capability_hints=["audio_context_background","lyrics_sync_parse"]),
    SiteSpec("amazon_music",   "https://music.amazon.com/",            "audio",  3, "Amazon Music",          requires_login=True, shares_auth_with="amazon",          capability_hints=["audio_context_background","playlist_array_manipulate","drm_handshake_observe"]),

    # ── 6. IMAGE PLATFORMS ───────────────────────────────────────────────
    SiteSpec("flickr",         "https://www.flickr.com/",              "image",  2, "Flickr",                "https://www.flickr.com/services/auth/",                 capability_hints=["masonry_grid_traverse","tag_cloud_map","exif_metadata_parse"]),
    SiteSpec("unsplash",       "https://unsplash.com/",                "image",  1, "Unsplash",              "https://unsplash.com/login",                            capability_hints=["high_res_asset_extract","tag_cloud_map","masonry_grid_traverse"]),
    SiteSpec("500px",          "https://500px.com/",                   "image",  2, "500px",                 "https://500px.com/login",                               capability_hints=["masonry_grid_traverse","tag_cloud_map","exif_metadata_parse"]),
    SiteSpec("imgur",          "https://imgur.com/",                   "image",  2, "Imgur",                 "https://imgur.com/signin",                              capability_hints=["masonry_grid_traverse","bulk_batch_upload"]),
    SiteSpec("deviantart",     "https://www.deviantart.com/",          "image",  2, "DeviantArt",            "https://www.deviantart.com/users/login",                capability_hints=["masonry_grid_traverse","tag_cloud_map","collection_moodboard_manage"]),
    SiteSpec("artstation",     "https://www.artstation.com/",          "image",  2, "ArtStation",            "https://www.artstation.com/users/sign_in",              capability_hints=["masonry_grid_traverse","high_res_asset_extract"]),
    SiteSpec("behance",        "https://www.behance.net/",             "image",  2, "Behance",               "https://www.behance.net/",                              capability_hints=["masonry_grid_traverse","collection_moodboard_manage"]),
    SiteSpec("dribbble",       "https://dribbble.com/",                "image",  2, "Dribbble",              "https://dribbble.com/session/new",                      capability_hints=["masonry_grid_traverse","tag_cloud_map"]),
    SiteSpec("pexels",         "https://www.pexels.com/",              "image",  1, "Pexels",                capability_hints=["high_res_asset_extract","tag_cloud_map","masonry_grid_traverse"]),
    SiteSpec("pixabay",        "https://pixabay.com/",                 "image",  1, "Pixabay",               "https://pixabay.com/accounts/login/",                   capability_hints=["high_res_asset_extract","tag_cloud_map"]),
    SiteSpec("shutterstock",   "https://www.shutterstock.com/",        "image",  2, "Shutterstock",          "https://www.shutterstock.com/login",                    capability_hints=["high_res_asset_extract","license_copyright_parse","watermark_detect"]),
    SiteSpec("adobe_stock",    "https://stock.adobe.com/",             "image",  2, "Adobe Stock",           requires_login=True,                                     capability_hints=["high_res_asset_extract","license_copyright_parse"]),
    SiteSpec("vsco",           "https://vsco.co/",                     "image",  2, "VSCO",                  "https://vsco.co/user/login",                            capability_hints=["masonry_grid_traverse","collection_moodboard_manage"]),
    SiteSpec("pixiv",          "https://www.pixiv.net/",               "image",  2, "Pixiv",                 "https://accounts.pixiv.net/login",                      capability_hints=["masonry_grid_traverse","tag_cloud_map","exif_metadata_parse"]),
    SiteSpec("smugmug",        "https://www.smugmug.com/",             "image",  2, "SmugMug",               "https://www.smugmug.com/login/",                        capability_hints=["high_res_asset_extract","collection_moodboard_manage"]),

    # ── 7. NEWS & PUBLISHING ─────────────────────────────────────────────
    SiteSpec("bbc",            "https://www.bbc.com/",                 "news",   2, "BBC News",                                                                       capability_hints=["schema_org_jsonld_parse","rss_endpoint_discover","reader_mode_dom_simplify"]),
    SiteSpec("reuters",        "https://www.reuters.com/",             "news",   2, "Reuters",                                                                        capability_hints=["schema_org_jsonld_parse","rss_endpoint_discover","author_archive_traverse"]),
    SiteSpec("cnn",            "https://www.cnn.com/",                 "news",   3, "CNN",                                                                            capability_hints=["schema_org_jsonld_parse","live_blog_poll_intercept","paywall_bypass_attempt"]),
    SiteSpec("nytimes",        "https://www.nytimes.com/",             "news",   3, "New York Times",        requires_login=True,                                     capability_hints=["paywall_bypass_attempt","schema_org_jsonld_parse","newsletter_subscribe_automate"]),
    SiteSpec("theguardian",    "https://www.theguardian.com/",         "news",   2, "The Guardian",                                                                   capability_hints=["schema_org_jsonld_parse","rss_endpoint_discover","author_archive_traverse"]),
    SiteSpec("washingtonpost", "https://www.washingtonpost.com/",      "news",   3, "Washington Post",       requires_login=True,                                     capability_hints=["paywall_bypass_attempt","live_blog_poll_intercept"]),
    SiteSpec("bloomberg",      "https://www.bloomberg.com/",           "news",   3, "Bloomberg",             requires_login=True,                                     capability_hints=["paywall_bypass_attempt","schema_org_jsonld_parse"]),
    SiteSpec("wsj",            "https://www.wsj.com/",                 "news",   4, "Wall Street Journal",   requires_login=True,                                     capability_hints=["paywall_bypass_attempt","schema_org_jsonld_parse"]),
    SiteSpec("apnews",         "https://apnews.com/",                  "news",   2, "AP News",                                                                        capability_hints=["schema_org_jsonld_parse","rss_endpoint_discover"]),
    SiteSpec("techcrunch",     "https://techcrunch.com/",              "news",   2, "TechCrunch",                                                                     capability_hints=["schema_org_jsonld_parse","author_archive_traverse","rss_endpoint_discover"]),
    SiteSpec("theverge",       "https://www.theverge.com/",            "news",   2, "The Verge",                                                                      capability_hints=["schema_org_jsonld_parse","comment_disqus_interact"]),
    SiteSpec("wired",          "https://www.wired.com/",               "news",   2, "Wired",                                                                          capability_hints=["schema_org_jsonld_parse","paywall_bypass_attempt"]),
    SiteSpec("ars_technica",   "https://arstechnica.com/",             "news",   2, "Ars Technica",                                                                   capability_hints=["schema_org_jsonld_parse","comment_disqus_interact","rss_endpoint_discover"]),
    SiteSpec("npr",            "https://www.npr.org/",                 "news",   2, "NPR",                                                                            capability_hints=["schema_org_jsonld_parse","rss_endpoint_discover"]),
    SiteSpec("vox",            "https://www.vox.com/",                 "news",   2, "Vox",                                                                            capability_hints=["schema_org_jsonld_parse","author_archive_traverse"]),
    SiteSpec("aljazeera",      "https://www.aljazeera.com/",           "news",   2, "Al Jazeera",                                                                     capability_hints=["schema_org_jsonld_parse","live_blog_poll_intercept"]),
    SiteSpec("producthunt",    "https://www.producthunt.com/",         "news",   2, "Product Hunt",          "https://www.producthunt.com/login",                     capability_hints=["karma_reputation_vote","schema_org_jsonld_parse"]),

    # ── 8. BLOGS & PERSONAL SITES ────────────────────────────────────────
    SiteSpec("medium",         "https://medium.com/",                  "blog",   2, "Medium",                "https://medium.com/m/signin",                           capability_hints=["paywall_bypass_attempt","chronological_archive_navigate","newsletter_subscribe_automate"]),
    SiteSpec("substack",       "https://substack.com/",                "blog",   2, "Substack",              capability_hints=["newsletter_subscribe_automate","rss_atom_feed_detect","comment_form_submit"]),
    SiteSpec("tumblr",         "https://www.tumblr.com/",              "blog",   2, "Tumblr",                "https://www.tumblr.com/login",                          capability_hints=["chronological_archive_navigate","tag_category_taxonomy_map","infinite_scroll_dom"]),
    SiteSpec("hashnode",       "https://hashnode.com/",                "blog",   2, "Hashnode",              "https://hashnode.com/login",                            capability_hints=["tag_category_taxonomy_map","rss_atom_feed_detect"]),
    SiteSpec("ghost",          "https://ghost.org/",                   "blog",   2, "Ghost",                                                                          capability_hints=["rss_atom_feed_detect","newsletter_subscribe_automate","ssg_structure_predict"]),
    SiteSpec("write_as",       "https://write.as/",                    "blog",   1, "Write.as",              "https://write.as/login",                                capability_hints=["rss_atom_feed_detect","chronological_archive_navigate"]),
    SiteSpec("microblog",      "https://micro.blog/",                  "blog",   1, "Micro.blog",            "https://micro.blog/login",                              capability_hints=["webmention_trackback","rss_atom_feed_detect"]),
    SiteSpec("bearblog",       "https://bearblog.dev/",                "blog",   1, "Bear Blog",             capability_hints=["rss_atom_feed_detect","ssg_structure_predict"]),
    SiteSpec("svbtle",         "https://svbtle.com/",                  "blog",   1, "Svbtle",                capability_hints=["chronological_archive_navigate","rss_atom_feed_detect"]),
    SiteSpec("mirror_xyz",     "https://mirror.xyz/",                  "blog",   2, "Mirror.xyz",            capability_hints=["chronological_archive_navigate","tag_category_taxonomy_map"]),
    SiteSpec("wordpress_blogs","https://wordpress.com/",               "blog",   2, "WordPress.com",         "https://wordpress.com/log-in",                          capability_hints=["chronological_archive_navigate","tag_category_taxonomy_map","rss_atom_feed_detect"]),
    SiteSpec("blogger",        "https://www.blogger.com/",             "blog",   2, "Blogger",               "https://www.blogger.com/",                              capability_hints=["chronological_archive_navigate","rss_atom_feed_detect"]),

    # ── 9. E-COMMERCE ────────────────────────────────────────────────────
    SiteSpec("amazon",         "https://www.amazon.com/",              "ecommerce", 3, "Amazon",             "https://www.amazon.com/ap/signin",                      capability_hints=["multi_facet_filter","cart_state_manipulate","checkout_pipeline_traverse","review_sentiment_extract","recommendation_scrape"]),
    SiteSpec("ebay",           "https://www.ebay.com/",                "ecommerce", 3, "eBay",                                                                        capability_hints=["multi_facet_filter","dynamic_pricing_sku_track","review_sentiment_extract"]),
    SiteSpec("aliexpress",     "https://www.aliexpress.com/",          "ecommerce", 3, "AliExpress",                                                                   capability_hints=["multi_facet_filter","dynamic_pricing_sku_track","cart_state_manipulate"]),
    SiteSpec("walmart",        "https://www.walmart.com/",             "ecommerce", 3, "Walmart",                                                                      capability_hints=["multi_facet_filter","cart_state_manipulate","shipping_calculator_spoof"]),
    SiteSpec("target",         "https://www.target.com/",              "ecommerce", 3, "Target",                                                                       capability_hints=["multi_facet_filter","cart_state_manipulate","inventory_stock_poll"]),
    SiteSpec("bestbuy",        "https://www.bestbuy.com/",             "ecommerce", 3, "Best Buy",                                                                     capability_hints=["multi_facet_filter","dynamic_pricing_sku_track","inventory_stock_poll"]),
    SiteSpec("etsy",           "https://www.etsy.com/",                "ecommerce", 2, "Etsy",                "https://www.etsy.com/signin",                          capability_hints=["multi_facet_filter","review_sentiment_extract","wishlist_graph_build"]),
    SiteSpec("newegg",         "https://www.newegg.com/",              "ecommerce", 2, "Newegg",                                                                       capability_hints=["multi_facet_filter","dynamic_pricing_sku_track"]),
    SiteSpec("shopee",         "https://shopee.sg/",                   "ecommerce", 3, "Shopee",              requires_login=True,                                     capability_hints=["multi_facet_filter","cart_state_manipulate","dynamic_pricing_sku_track"]),
    SiteSpec("zalando",        "https://www.zalando.com/",             "ecommerce", 2, "Zalando",                                                                      capability_hints=["multi_facet_filter","cart_state_manipulate"]),
    SiteSpec("asos",           "https://www.asos.com/",                "ecommerce", 2, "ASOS",                                                                         capability_hints=["multi_facet_filter","cart_state_manipulate","wishlist_graph_build"]),
    SiteSpec("wayfair",        "https://www.wayfair.com/",             "ecommerce", 2, "Wayfair",                                                                      capability_hints=["multi_facet_filter","cart_state_manipulate"]),
    SiteSpec("shein",          "https://www.shein.com/",               "ecommerce", 3, "Shein",                                                                        capability_hints=["multi_facet_filter","promo_code_validate","dynamic_pricing_sku_track"]),
    SiteSpec("temu",           "https://www.temu.com/",                "ecommerce", 3, "Temu",                                                                         capability_hints=["multi_facet_filter","dynamic_pricing_sku_track","promo_code_validate"]),
    SiteSpec("saucedemo",      "https://www.saucedemo.com/",           "ecommerce", 1, "SauceDemo",           "https://www.saucedemo.com/",                            capability_hints=["cart_state_manipulate","checkout_pipeline_traverse"]),
    SiteSpec("magento_demo",   "https://magento.softwaretestingboard.com/", "ecommerce", 1, "Magento Demo",                                                            capability_hints=["multi_facet_filter","cart_state_manipulate","checkout_pipeline_traverse"]),

    # ── 10. MARKETPLACES (SERVICES / P2P) ────────────────────────────────
    SiteSpec("fiverr",         "https://www.fiverr.com/",              "marketplace", 2, "Fiverr",             "https://www.fiverr.com/login",                        capability_hints=["two_sided_graph_discover","bid_offer_submit","reputation_score_calculate"]),
    SiteSpec("upwork",         "https://www.upwork.com/",              "marketplace", 3, "Upwork",             "https://www.upwork.com/ab/account-security/login",    capability_hints=["two_sided_graph_discover","bid_offer_submit","escrow_simulate"]),
    SiteSpec("freelancer",     "https://www.freelancer.com/",          "marketplace", 2, "Freelancer",         "https://www.freelancer.com/login",                    capability_hints=["bid_offer_submit","reputation_score_calculate"]),
    SiteSpec("airbnb",         "https://www.airbnb.com/",              "marketplace", 3, "Airbnb",             "https://www.airbnb.com/login",                        capability_hints=["calendar_availability_parse","geolocation_radius_search","two_sided_graph_discover"]),
    SiteSpec("booking",        "https://www.booking.com/",             "marketplace", 3, "Booking.com",                                                               capability_hints=["calendar_availability_parse","geolocation_radius_search","dynamic_pricing_sku_track"]),
    SiteSpec("taskrabbit",     "https://www.taskrabbit.com/",          "marketplace", 2, "TaskRabbit",         "https://www.taskrabbit.com/login",                    capability_hints=["calendar_availability_parse","geolocation_radius_search"]),
    SiteSpec("craigslist",     "https://www.craigslist.org/",          "marketplace", 1, "Craigslist",                                                                 capability_hints=["geolocation_radius_search","listing_draft_publish"]),
    SiteSpec("gumtree",        "https://www.gumtree.com/",             "marketplace", 2, "Gumtree",            "https://secure.gumtree.com/login",                    capability_hints=["geolocation_radius_search","listing_draft_publish"]),
    SiteSpec("poshmark",       "https://poshmark.com/",                "marketplace", 2, "Poshmark",           "https://poshmark.com/login",                          capability_hints=["two_sided_graph_discover","listing_draft_publish","reputation_score_calculate"]),
    SiteSpec("depop",          "https://www.depop.com/",               "marketplace", 2, "Depop",              "https://www.depop.com/login/",                        capability_hints=["listing_draft_publish","two_sided_graph_discover"]),
    SiteSpec("vinted",         "https://www.vinted.com/",              "marketplace", 2, "Vinted",             "https://www.vinted.com/login",                        capability_hints=["listing_draft_publish","realtime_negotiation_chat"]),
    SiteSpec("stockx",         "https://stockx.com/",                  "marketplace", 3, "StockX",             "https://stockx.com/login",                            capability_hints=["bid_offer_submit","dynamic_pricing_sku_track"]),
    SiteSpec("grailed",        "https://www.grailed.com/",             "marketplace", 2, "Grailed",            "https://www.grailed.com/users/sign_in",                capability_hints=["listing_draft_publish","bid_offer_submit"]),
    SiteSpec("olx",            "https://www.olx.com/",                 "marketplace", 2, "OLX",                capability_hints=["geolocation_radius_search","listing_draft_publish"]),

    # ── 11. SAAS APPLICATIONS ────────────────────────────────────────────
    SiteSpec("notion",         "https://www.notion.so/",               "saas",   2, "Notion",                "https://www.notion.so/login",                           capability_hints=["block_level_dom_edit","drag_drop_datatransfer","export_import_pipeline","multi_tenant_auth"]),
    SiteSpec("figma",          "https://www.figma.com/",               "saas",   2, "Figma",                 "https://www.figma.com/login",                           capability_hints=["canvas_webgl_extract","drag_drop_datatransfer","crdt_state_sync"]),
    SiteSpec("canva",          "https://www.canva.com/",               "saas",   2, "Canva",                 "https://www.canva.com/login",                           capability_hints=["canvas_webgl_extract","drag_drop_datatransfer","export_import_pipeline"]),
    SiteSpec("miro",           "https://miro.com/",                    "saas",   2, "Miro",                  "https://miro.com/login/",                               capability_hints=["canvas_webgl_extract","drag_drop_datatransfer","crdt_state_sync"]),
    SiteSpec("airtable",       "https://airtable.com/",                "saas",   2, "Airtable",              "https://airtable.com/login",                            capability_hints=["export_import_pipeline","role_permission_alter","workflow_automation_generate"]),
    SiteSpec("zapier",         "https://zapier.com/",                  "saas",   2, "Zapier",                "https://zapier.com/app/login",                          capability_hints=["workflow_automation_generate","webhook_trigger_config","api_key_token_generate"]),
    SiteSpec("typeform",       "https://www.typeform.com/",            "saas",   2, "Typeform",              "https://admin.typeform.com/login",                      capability_hints=["drag_drop_datatransfer","webhook_trigger_config"]),
    SiteSpec("hubspot",        "https://www.hubspot.com/",             "saas",   2, "HubSpot",               "https://app.hubspot.com/login",                         capability_hints=["role_permission_alter","workflow_automation_generate","audit_log_scrape"]),
    SiteSpec("zendesk",        "https://www.zendesk.com/",             "saas",   2, "Zendesk",               "https://support.zendesk.com/hc/en-us",                  capability_hints=["role_permission_alter","audit_log_scrape"]),
    SiteSpec("intercom",       "https://www.intercom.com/",            "saas",   2, "Intercom",              "https://app.intercom.com/",                             capability_hints=["realtime_dom_mutation_observe","workflow_automation_generate"]),
    SiteSpec("mailchimp",      "https://mailchimp.com/",               "saas",   2, "Mailchimp",             "https://login.mailchimp.com/",                          capability_hints=["export_import_pipeline","workflow_automation_generate"]),
    SiteSpec("salesforce",     "https://www.salesforce.com/",          "saas",   3, "Salesforce",            requires_login=True,                                     capability_hints=["role_permission_alter","workflow_automation_generate","audit_log_scrape"]),
    SiteSpec("coda",           "https://coda.io/",                     "saas",   2, "Coda",                  "https://coda.io/login",                                 capability_hints=["block_level_dom_edit","workflow_automation_generate","export_import_pipeline"]),
    SiteSpec("docusign",       "https://www.docusign.com/",            "saas",   3, "DocuSign",              requires_login=True,                                     capability_hints=["digital_signature_verify","export_import_pipeline"]),
    SiteSpec("retool",         "https://retool.com/",                  "saas",   2, "Retool",                "https://login.retool.com/",                             capability_hints=["drag_drop_datatransfer","api_key_token_generate","role_permission_alter"]),

    # ── 12. PRODUCTIVITY SYSTEMS ─────────────────────────────────────────
    SiteSpec("trello",         "https://trello.com/",                  "productivity", 2, "Trello",           "https://trello.com/login",                              capability_hints=["kanban_board_drag_drop","webhook_trigger_config","export_import_pipeline"]),
    SiteSpec("asana",          "https://app.asana.com/",               "productivity", 2, "Asana",            requires_login=True,                                     capability_hints=["gantt_timeline_extract","dependency_graph_build","kanban_board_drag_drop"]),
    SiteSpec("clickup",        "https://app.clickup.com/",             "productivity", 2, "ClickUp",          requires_login=True,                                     capability_hints=["kanban_board_drag_drop","custom_field_mutate","gantt_timeline_extract"]),
    SiteSpec("monday",         "https://monday.com/",                  "productivity", 3, "Monday.com",                                                                capability_hints=["kanban_board_drag_drop","gantt_timeline_extract","webhook_trigger_config"]),
    SiteSpec("jira",           "https://www.atlassian.com/software/jira", "productivity", 2, "Jira",          requires_login=True,                                     capability_hints=["dependency_graph_build","sprint_backlog_velocity","kanban_board_drag_drop"]),
    SiteSpec("linear",         "https://linear.app/",                  "productivity", 2, "Linear",           requires_login=True,                                     capability_hints=["kanban_board_drag_drop","dependency_graph_build","bidirectional_link_navigate"]),
    SiteSpec("basecamp",       "https://basecamp.com/",                "productivity", 2, "Basecamp",         "https://launchpad.37signals.com/session/new",           capability_hints=["kanban_board_drag_drop","webhook_trigger_config"]),
    SiteSpec("wrike",          "https://www.wrike.com/",               "productivity", 2, "Wrike",            requires_login=True,                                     capability_hints=["gantt_timeline_extract","kanban_board_drag_drop","custom_field_mutate"]),
    SiteSpec("todoist",        "https://todoist.com/",                 "productivity", 2, "Todoist",          "https://todoist.com/users/showlogin",                   capability_hints=["dependency_graph_build","kanban_board_drag_drop"]),
    SiteSpec("ticktick",       "https://ticktick.com/",                "productivity", 2, "TickTick",         "https://ticktick.com/login",                            capability_hints=["kanban_board_drag_drop","time_tracking_hook"]),
    SiteSpec("evernote",       "https://evernote.com/",                "productivity", 2, "Evernote",         "https://evernote.com/Login",                            capability_hints=["tag_category_taxonomy_map","indexeddb_offline_extract"]),
    SiteSpec("proofhub",       "https://www.proofhub.com/",            "productivity", 2, "ProofHub",         requires_login=True,                                     capability_hints=["gantt_timeline_extract","kanban_board_drag_drop"]),
    SiteSpec("google_keep",    "https://keep.google.com/",             "productivity", 3, "Google Keep",      requires_login=True, shares_auth_with="google",          protected=True, capability_hints=["kanban_board_drag_drop","indexeddb_offline_extract"]),
    SiteSpec("logseq_app",     "https://logseq.com/",                  "productivity", 2, "Logseq",           capability_hints=["bidirectional_link_navigate","block_level_dom_edit","indexeddb_offline_extract"]),

    # ── 13. KNOWLEDGE SYSTEMS ────────────────────────────────────────────
    SiteSpec("wikipedia",      "https://en.wikipedia.org/",            "knowledge", 1, "Wikipedia",          aliases=["wiki"],                                        capability_hints=["namespace_traverse","transclusion_template_resolve","version_history_diff","reference_citation_validate"]),
    SiteSpec("wikidata",       "https://www.wikidata.org/",            "knowledge", 1, "Wikidata",                                                                     capability_hints=["sparql_endpoint_query","knowledge_graph_triplet_extract"]),
    SiteSpec("confluence",     "https://www.atlassian.com/software/confluence", "knowledge", 2, "Confluence",  requires_login=True,                                    capability_hints=["wysiwyg_markdown_translate","transclusion_template_resolve","version_history_diff"]),
    SiteSpec("mediawiki",      "https://www.mediawiki.org/",           "knowledge", 1, "MediaWiki",                                                                    capability_hints=["namespace_traverse","version_history_diff","transclusion_template_resolve"]),
    SiteSpec("fandom_wiki",    "https://www.fandom.com/",              "knowledge", 2, "Fandom Wikis",                                                                 capability_hints=["namespace_traverse","transclusion_template_resolve","tag_cloud_map"]),
    SiteSpec("readthedocs",    "https://readthedocs.org/",             "knowledge", 1, "Read the Docs",                                                                capability_hints=["taxonomy_ontology_parse","broken_link_map","rss_atom_feed_detect"]),
    SiteSpec("gitbook",        "https://www.gitbook.com/",             "knowledge", 2, "GitBook",             "https://app.gitbook.com/sign-in",                       capability_hints=["namespace_traverse","wysiwyg_markdown_translate"]),
    SiteSpec("notion_wiki",    "https://www.notion.so/",               "knowledge", 2, "Notion Wiki",         "https://www.notion.so/login",                           capability_hints=["bidirectional_link_navigate","transclusion_template_resolve","wysiwyg_markdown_translate"]),
    SiteSpec("slab",           "https://slab.com/",                    "knowledge", 2, "Slab",                requires_login=True,                                     capability_hints=["wysiwyg_markdown_translate","taxonomy_ontology_parse"]),
    SiteSpec("nuclino",        "https://www.nuclino.com/",             "knowledge", 2, "Nuclino",             "https://app.nuclino.com/login",                         capability_hints=["bidirectional_link_navigate","wysiwyg_markdown_translate"]),
    SiteSpec("document360",    "https://document360.com/",             "knowledge", 2, "Document360",         requires_login=True,                                     capability_hints=["taxonomy_ontology_parse","version_history_diff"]),
    SiteSpec("obsidian_pub",   "https://publish.obsidian.md/",         "knowledge", 1, "Obsidian Publish",                                                             capability_hints=["bidirectional_link_navigate","namespace_traverse"]),
    SiteSpec("devdocs",        "https://devdocs.io/",                  "knowledge", 1, "DevDocs",                                                                      capability_hints=["taxonomy_ontology_parse","namespace_traverse"]),

    # ── 14. DEVELOPER PLATFORMS ──────────────────────────────────────────
    SiteSpec("github",         "https://github.com/",                  "dev",    2, "GitHub",                "https://github.com/login",           ["gh"],            capability_hints=["commit_tree_navigate","pull_request_diff_parse","issue_state_mutate","ci_cd_log_stream"]),
    SiteSpec("gitlab",         "https://gitlab.com/",                  "dev",    2, "GitLab",                "https://gitlab.com/users/sign_in",                      capability_hints=["commit_tree_navigate","ci_cd_log_stream","container_registry_poll"]),
    SiteSpec("bitbucket",      "https://bitbucket.org/",               "dev",    2, "Bitbucket",             "https://id.atlassian.com/login",                        capability_hints=["commit_tree_navigate","pull_request_diff_parse"]),
    SiteSpec("huggingface",    "https://huggingface.co/",              "dev",    2, "HuggingFace",           "https://huggingface.co/login",       ["hf"],            capability_hints=["jupyter_cell_execute","container_registry_poll","fork_clone_trigger"]),
    SiteSpec("docker",         "https://hub.docker.com/",              "dev",    2, "Docker Hub",                                                                      capability_hints=["container_registry_poll","fork_clone_trigger"]),
    SiteSpec("replit",         "https://replit.com/",                  "dev",    2, "Replit",                "https://replit.com/login",                              capability_hints=["web_ide_monaco_interact","jupyter_cell_execute","fork_clone_trigger"]),
    SiteSpec("codesandbox",    "https://codesandbox.io/",              "dev",    2, "CodeSandbox",           "https://codesandbox.io/signin",                         capability_hints=["web_ide_monaco_interact","fork_clone_trigger"]),
    SiteSpec("codepen",        "https://codepen.io/",                  "dev",    2, "CodePen",               "https://codepen.io/login",                              capability_hints=["web_ide_monaco_interact","fork_clone_trigger"]),
    SiteSpec("jsfiddle",       "https://jsfiddle.net/",                "dev",    1, "JSFiddle",                                                                        capability_hints=["web_ide_monaco_interact"]),
    SiteSpec("stackblitz",     "https://stackblitz.com/",              "dev",    2, "StackBlitz",            capability_hints=["web_ide_monaco_interact","jupyter_cell_execute"]),
    SiteSpec("kaggle",         "https://www.kaggle.com/",              "dev",    2, "Kaggle",                "https://www.kaggle.com/account/login",                  capability_hints=["jupyter_cell_execute","commit_tree_navigate"]),
    SiteSpec("google_colab",   "https://colab.research.google.com/",  "dev",    3, "Google Colab",          requires_login=True, shares_auth_with="google",          protected=True, capability_hints=["jupyter_cell_execute","web_ide_monaco_interact"]),
    SiteSpec("vercel",         "https://vercel.com/",                  "dev",    2, "Vercel",                "https://vercel.com/login",                              capability_hints=["ci_cd_log_stream","secret_env_inject_flow"]),
    SiteSpec("netlify",        "https://www.netlify.com/",             "dev",    2, "Netlify",               "https://app.netlify.com/login",                         capability_hints=["ci_cd_log_stream","secret_env_inject_flow"]),
    SiteSpec("sourcehut",      "https://sourcehut.org/",               "dev",    1, "Sourcehut",             "https://meta.sr.ht/login",                              capability_hints=["commit_tree_navigate","pull_request_diff_parse"]),
    SiteSpec("gitea",          "https://gitea.com/",                   "dev",    1, "Gitea",                 "https://gitea.com/user/login",                          capability_hints=["commit_tree_navigate","issue_state_mutate"]),

    # ── 15. PACKAGE REGISTRIES ───────────────────────────────────────────
    SiteSpec("pypi",           "https://pypi.org/",                    "registry", 1, "PyPI",                                                                          capability_hints=["dependency_tree_resolve","semver_constraint_parse","cve_vulnerability_map","download_stat_poll"]),
    SiteSpec("npm",            "https://www.npmjs.com/",               "registry", 1, "npm",                                                                           capability_hints=["dependency_tree_resolve","semver_constraint_parse","maintainer_graph_traverse"]),
    SiteSpec("crates_io",      "https://crates.io/",                   "registry", 1, "Crates.io",                                                                     capability_hints=["dependency_tree_resolve","semver_constraint_parse","download_stat_poll"]),
    SiteSpec("rubygems",       "https://rubygems.org/",                "registry", 1, "RubyGems",                                                                      capability_hints=["dependency_tree_resolve","maintainer_graph_traverse"]),
    SiteSpec("nuget",          "https://www.nuget.org/",               "registry", 1, "NuGet",                                                                         capability_hints=["dependency_tree_resolve","semver_constraint_parse"]),
    SiteSpec("packagist",      "https://packagist.org/",               "registry", 1, "Packagist",                                                                     capability_hints=["dependency_tree_resolve","maintainer_graph_traverse"]),
    SiteSpec("hex_pm",         "https://hex.pm/",                      "registry", 1, "Hex.pm",                                                                        capability_hints=["dependency_tree_resolve","semver_constraint_parse"]),
    SiteSpec("pub_dev",        "https://pub.dev/",                     "registry", 1, "pub.dev",                                                                       capability_hints=["dependency_tree_resolve","semver_constraint_parse"]),
    SiteSpec("cocoapods",      "https://cocoapods.org/",               "registry", 1, "CocoaPods",                                                                     capability_hints=["dependency_tree_resolve","maintainer_graph_traverse"]),
    SiteSpec("anaconda",       "https://anaconda.org/",                "registry", 1, "Anaconda.org",                                                                  capability_hints=["dependency_tree_resolve","download_stat_poll"]),
    SiteSpec("mvn_repo",       "https://mvnrepository.com/",           "registry", 1, "MVN Repository",                                                                capability_hints=["dependency_tree_resolve","semver_constraint_parse"]),
    SiteSpec("jitpack",        "https://jitpack.io/",                  "registry", 1, "JitPack",                                                                       capability_hints=["dependency_tree_resolve","tarball_blob_extract"]),
    SiteSpec("cran",           "https://cran.r-project.org/",          "registry", 1, "CRAN (R)",                                                                      capability_hints=["dependency_tree_resolve","readme_docs_render"]),

    # ── 16. CLOUD PLATFORMS ──────────────────────────────────────────────
    SiteSpec("aws",            "https://aws.amazon.com/",              "cloud",  2, "AWS",                   "https://console.aws.amazon.com/",                       capability_hints=["iam_policy_parse","resource_provision_workflow","billing_dashboard_scrape","storage_bucket_traverse"]),
    SiteSpec("gcp",            "https://console.cloud.google.com/",    "cloud",  3, "Google Cloud",          requires_login=True,                                     protected=True, capability_hints=["iam_policy_parse","resource_provision_workflow","billing_dashboard_scrape"]),
    SiteSpec("azure",          "https://portal.azure.com/",            "cloud",  3, "Microsoft Azure",       requires_login=True,                                     capability_hints=["iam_policy_parse","resource_provision_workflow"]),
    SiteSpec("cloudflare",     "https://www.cloudflare.com/",          "cloud",  2, "Cloudflare",            "https://dash.cloudflare.com/login",                     capability_hints=["dns_record_mutate","firewall_security_group_config"]),
    SiteSpec("digitalocean",   "https://www.digitalocean.com/",        "cloud",  2, "DigitalOcean",          "https://cloud.digitalocean.com/login",                  capability_hints=["resource_provision_workflow","ssh_key_inject_flow"]),
    SiteSpec("linode",         "https://www.linode.com/",              "cloud",  2, "Linode / Akamai",       "https://login.linode.com/login",                        capability_hints=["resource_provision_workflow","ssh_key_inject_flow"]),
    SiteSpec("heroku",         "https://www.heroku.com/",              "cloud",  2, "Heroku",                "https://id.heroku.com/login",                           capability_hints=["resource_provision_workflow","serverless_log_tail"]),
    SiteSpec("ibm_cloud",      "https://cloud.ibm.com/",               "cloud",  3, "IBM Cloud",             requires_login=True,                                     capability_hints=["iam_policy_parse","resource_provision_workflow"]),
    SiteSpec("ovhcloud",       "https://www.ovhcloud.com/",            "cloud",  2, "OVHcloud",              "https://www.ovhcloud.com/auth/",                        capability_hints=["resource_provision_workflow","dns_record_mutate"]),
    SiteSpec("hetzner",        "https://www.hetzner.com/",             "cloud",  1, "Hetzner",               "https://accounts.hetzner.com/login",                   capability_hints=["resource_provision_workflow","ssh_key_inject_flow"]),
    SiteSpec("fly_io",         "https://fly.io/",                      "cloud",  2, "Fly.io",                "https://fly.io/app/sign-in",                            capability_hints=["resource_provision_workflow","serverless_log_tail"]),
    SiteSpec("supabase",       "https://supabase.com/",                "cloud",  2, "Supabase",              "https://app.supabase.com/",                             capability_hints=["resource_provision_workflow","api_key_token_generate","storage_bucket_traverse"]),
    SiteSpec("firebase",       "https://firebase.google.com/",         "cloud",  2, "Firebase",              requires_login=True, shares_auth_with="google",          protected=True, capability_hints=["resource_provision_workflow","realtime_dom_mutation_observe"]),
    SiteSpec("render",         "https://render.com/",                  "cloud",  2, "Render",                "https://dashboard.render.com/",                         capability_hints=["ci_cd_log_stream","resource_provision_workflow"]),

    # ── 17. AUTHENTICATION SYSTEMS ───────────────────────────────────────
    SiteSpec("auth0",          "https://auth0.com/",                   "auth",   2, "Auth0",                 "https://manage.auth0.com/",                             capability_hints=["oauth2_oidc_redirect_track","jwt_token_extract_decode","social_login_shadow_dom"]),
    SiteSpec("okta",           "https://www.okta.com/",                "auth",   3, "Okta",                  requires_login=True,                                     capability_hints=["saml_assertion_intercept","mfa_totp_seed_inject","oauth2_oidc_redirect_track"]),
    SiteSpec("clerk",          "https://clerk.com/",                   "auth",   2, "Clerk",                 capability_hints=["magic_link_email_poll","webauthn_passkey_emulate","social_login_shadow_dom"]),
    SiteSpec("keycloak",       "https://www.keycloak.org/",            "auth",   2, "Keycloak",              capability_hints=["saml_assertion_intercept","oauth2_oidc_redirect_track","mfa_totp_seed_inject"]),
    SiteSpec("cognito",        "https://aws.amazon.com/cognito/",      "auth",   2, "AWS Cognito",           capability_hints=["oauth2_oidc_redirect_track","jwt_token_extract_decode"]),
    SiteSpec("magic",          "https://magic.link/",                  "auth",   2, "Magic.link",            capability_hints=["magic_link_email_poll","oauth2_oidc_redirect_track"]),
    SiteSpec("kinde",          "https://kinde.com/",                   "auth",   2, "Kinde",                 capability_hints=["oauth2_oidc_redirect_track","social_login_shadow_dom"]),
    SiteSpec("stytch",         "https://stytch.com/",                  "auth",   2, "Stytch",                capability_hints=["magic_link_email_poll","webauthn_passkey_emulate"]),
    SiteSpec("descope",        "https://www.descope.com/",             "auth",   2, "Descope",               capability_hints=["oauth2_oidc_redirect_track","social_login_shadow_dom"]),
    SiteSpec("supabase_auth",  "https://supabase.com/auth",            "auth",   2, "Supabase Auth",         capability_hints=["jwt_token_extract_decode","oauth2_oidc_redirect_track"]),
    SiteSpec("ory",            "https://www.ory.sh/",                  "auth",   2, "Ory",                   capability_hints=["oauth2_oidc_redirect_track","session_cookie_replay"]),
    SiteSpec("pingidentity",   "https://www.pingidentity.com/",        "auth",   3, "Ping Identity",         requires_login=True,                                     capability_hints=["saml_assertion_intercept","mfa_totp_seed_inject"]),

    # ── 18. EMAIL SYSTEMS ────────────────────────────────────────────────
    SiteSpec("gmail",          "https://mail.google.com/",             "email",  4, "Gmail",                 requires_login=True, shares_auth_with="google",          protected=True, capability_hints=["thread_collapse_expand","attachment_blob_render","spam_filter_config"]),
    SiteSpec("outlook_mail",   "https://outlook.live.com/mail/",       "email",  3, "Outlook.com",           requires_login=True,                                     capability_hints=["thread_collapse_expand","attachment_blob_render","html_email_sanitize"]),
    SiteSpec("protonmail",     "https://mail.proton.me/",              "email",  3, "Proton Mail",           requires_login=True,                                     capability_hints=["pgp_gpg_keyring_dom","attachment_blob_render"]),
    SiteSpec("yahoo_mail",     "https://mail.yahoo.com/",              "email",  3, "Yahoo Mail",            requires_login=True,                                     capability_hints=["thread_collapse_expand","spam_filter_config"]),
    SiteSpec("fastmail",       "https://www.fastmail.com/",            "email",  2, "Fastmail",              "https://www.fastmail.com/login/",                       capability_hints=["thread_collapse_expand","alias_disposable_generate"]),
    SiteSpec("tuta",           "https://tuta.com/",                    "email",  2, "Tuta (Tutanota)",       "https://mail.tuta.com/",                                capability_hints=["pgp_gpg_keyring_dom","alias_disposable_generate"]),
    SiteSpec("zoho_mail",      "https://mail.zoho.com/",               "email",  2, "Zoho Mail",             requires_login=True,                                     capability_hints=["thread_collapse_expand","alias_disposable_generate"]),
    SiteSpec("hey_email",      "https://app.hey.com/",                 "email",  2, "Hey",                   requires_login=True,                                     capability_hints=["thread_collapse_expand","snooze_schedule_trigger"]),
    SiteSpec("gmx",            "https://www.gmx.com/",                 "email",  2, "GMX",                   "https://www.gmx.com/",                                  capability_hints=["thread_collapse_expand","spam_filter_config"]),
    SiteSpec("posteo",         "https://posteo.de/",                   "email",  1, "Posteo",                requires_login=True,                                     capability_hints=["pgp_gpg_keyring_dom","alias_disposable_generate"]),
    SiteSpec("mailbox_org",    "https://mailbox.org/",                 "email",  1, "Mailbox.org",           "https://office.mailbox.org/",                           capability_hints=["pgp_gpg_keyring_dom","contact_book_sync"]),

    # ── 19. GOVERNMENT PORTALS ───────────────────────────────────────────
    SiteSpec("irs_gov",        "https://www.irs.gov/",                 "government", 2, "IRS.gov",                                                                     capability_hints=["legacy_mainframe_wrapper_navigate","pdf_form_fill_generate","multi_page_session_timeout_circumvent"]),
    SiteSpec("ssa_gov",        "https://www.ssa.gov/",                 "government", 2, "SSA.gov",                                                                     capability_hints=["pdf_form_fill_generate","multi_page_session_timeout_circumvent"]),
    SiteSpec("usa_gov",        "https://www.usa.gov/",                 "government", 1, "USA.gov",                                                                     capability_hints=["bureaucratic_form_taxonomy","pdf_form_fill_generate"]),
    SiteSpec("gov_uk",         "https://www.gov.uk/",                  "government", 1, "GOV.UK",                                                                      capability_hints=["bureaucratic_form_taxonomy","appointment_calendar_matrix"]),
    SiteSpec("mygov_au",       "https://www.myGov.au/",                "government", 2, "myGov (Australia)",                                                           capability_hints=["multi_page_session_timeout_circumvent","identity_document_upload"]),
    SiteSpec("canada_ca",      "https://www.canada.ca/",               "government", 1, "Canada.ca",                                                                   capability_hints=["bureaucratic_form_taxonomy","pdf_form_fill_generate"]),
    SiteSpec("healthcare_gov", "https://www.healthcare.gov/",          "government", 2, "Healthcare.gov",                                                              capability_hints=["multi_page_session_timeout_circumvent","pdf_form_fill_generate"]),
    SiteSpec("france_connect", "https://franceconnect.gouv.fr/",       "government", 2, "FranceConnect",                                                               capability_hints=["oauth2_oidc_redirect_track","identity_document_upload"]),
    SiteSpec("e_estonia",      "https://www.eesti.ee/",                "government", 2, "e-Estonia",                                                                   capability_hints=["digital_signature_verify","identity_document_upload"]),
    SiteSpec("singpass",       "https://www.singpass.gov.sg/",         "government", 2, "Singpass (Singapore)",                                                        capability_hints=["digital_signature_verify","oauth2_oidc_redirect_track"]),
    SiteSpec("india_gov",      "https://www.india.gov.in/",            "government", 2, "India.gov.in",                                                                capability_hints=["bureaucratic_form_taxonomy","pdf_form_fill_generate"]),
    SiteSpec("service_ontario","https://www.ontario.ca/page/government-ontario", "government", 2, "ServiceOntario",                                                     capability_hints=["appointment_calendar_matrix","pdf_form_fill_generate"]),

    # ── 20. BANKING & FINANCE ────────────────────────────────────────────
    SiteSpec("paypal",         "https://www.paypal.com/",              "finance", 3, "PayPal",               "https://www.paypal.com/signin",                         capability_hints=["transaction_ledger_paginate","wire_transfer_authorize","virtual_card_generate"]),
    SiteSpec("wise",           "https://wise.com/",                    "finance", 2, "Wise",                 "https://wise.com/login",                                capability_hints=["exchange_rate_poll","iban_routing_validate","transaction_ledger_paginate"]),
    SiteSpec("revolut",        "https://www.revolut.com/",             "finance", 3, "Revolut",              "https://www.revolut.com/app/",                          capability_hints=["virtual_card_generate","exchange_rate_poll","transaction_ledger_paginate"]),
    SiteSpec("stripe_dash",    "https://dashboard.stripe.com/",        "finance", 3, "Stripe Dashboard",     requires_login=True,                                     capability_hints=["transaction_ledger_paginate","api_key_token_generate","billing_dashboard_scrape"]),
    SiteSpec("yahoo_finance",  "https://finance.yahoo.com/",           "finance", 2, "Yahoo Finance",                                                                  capability_hints=["exchange_rate_poll","timeseries_chart_extract"]),
    SiteSpec("tradingview",    "https://www.tradingview.com/",         "finance", 2, "TradingView",                                                                    capability_hints=["timeseries_chart_extract","orderbook_canvas_parse"]),
    SiteSpec("investopedia",   "https://www.investopedia.com/",        "finance", 2, "Investopedia",                                                                   capability_hints=["schema_org_jsonld_parse","exchange_rate_poll"]),
    SiteSpec("marketwatch",    "https://www.marketwatch.com/",         "finance", 2, "MarketWatch",                                                                    capability_hints=["timeseries_chart_extract","exchange_rate_poll"]),
    SiteSpec("nubank",         "https://nubank.com.br/",               "finance", 3, "Nubank",               requires_login=True,                                     capability_hints=["virtual_card_generate","transaction_ledger_paginate"]),
    SiteSpec("monzo",          "https://monzo.com/",                   "finance", 3, "Monzo",                requires_login=True,                                     capability_hints=["virtual_card_generate","transaction_ledger_paginate"]),
    SiteSpec("n26",            "https://n26.com/",                     "finance", 3, "N26",                  requires_login=True,                                     capability_hints=["virtual_card_generate","exchange_rate_poll"]),
    SiteSpec("venmo",          "https://venmo.com/",                   "finance", 3, "Venmo",                requires_login=True,                                     capability_hints=["transaction_ledger_paginate","wire_transfer_authorize"]),
    SiteSpec("cashapp",        "https://cash.app/",                    "finance", 3, "Cash App",             requires_login=True,                                     capability_hints=["wire_transfer_authorize","transaction_ledger_paginate"]),
    SiteSpec("zelle",          "https://www.zellepay.com/",            "finance", 3, "Zelle",                requires_login=True,                                     capability_hints=["wire_transfer_authorize","fraud_verification_hurdle"]),

    # ── 21. CRYPTO PLATFORMS ─────────────────────────────────────────────
    SiteSpec("binance",        "https://www.binance.com/",             "crypto", 4, "Binance",               "https://accounts.binance.com/en/login",                 capability_hints=["orderbook_canvas_parse","token_swap_route_simulate","gas_fee_poll_adjust"]),
    SiteSpec("coinbase",       "https://www.coinbase.com/",            "crypto", 3, "Coinbase",              "https://login.coinbase.com/",                           capability_hints=["transaction_ledger_paginate","virtual_card_generate"]),
    SiteSpec("kraken",         "https://www.kraken.com/",              "crypto", 3, "Kraken",                "https://www.kraken.com/sign-in",                        capability_hints=["orderbook_canvas_parse","liquidity_pool_mutate"]),
    SiteSpec("metamask",       "https://metamask.io/",                 "crypto", 2, "MetaMask",                                                                        capability_hints=["web3_provider_inject","signature_request_intercept","seed_phrase_vault_interact"]),
    SiteSpec("uniswap",        "https://app.uniswap.org/",             "crypto", 2, "Uniswap",                                                                         capability_hints=["web3_provider_inject","token_swap_route_simulate","liquidity_pool_mutate"]),
    SiteSpec("opensea",        "https://opensea.io/",                  "crypto", 2, "OpenSea",                                                                         capability_hints=["nft_metadata_ipfs_resolve","web3_provider_inject","bid_offer_submit"]),
    SiteSpec("etherscan",      "https://etherscan.io/",                "crypto", 1, "Etherscan",                                                                       capability_hints=["blockchain_explorer_trace","smart_contract_abi_decode"]),
    SiteSpec("coingecko",      "https://www.coingecko.com/",           "crypto", 1, "CoinGecko",                                                                       capability_hints=["exchange_rate_poll","timeseries_chart_extract"]),
    SiteSpec("coinmarketcap",  "https://coinmarketcap.com/",           "crypto", 2, "CoinMarketCap",                                                                   capability_hints=["exchange_rate_poll","orderbook_canvas_parse"]),
    SiteSpec("kucoin",         "https://www.kucoin.com/",              "crypto", 3, "KuCoin",                "https://www.kucoin.com/login",                          capability_hints=["orderbook_canvas_parse","gas_fee_poll_adjust"]),
    SiteSpec("okx",            "https://www.okx.com/",                 "crypto", 3, "OKX",                   "https://www.okx.com/login",                             capability_hints=["orderbook_canvas_parse","token_swap_route_simulate"]),
    SiteSpec("phantom",        "https://phantom.app/",                 "crypto", 2, "Phantom Wallet",                                                                  capability_hints=["web3_provider_inject","signature_request_intercept"]),
    SiteSpec("raydium",        "https://raydium.io/",                  "crypto", 2, "Raydium",                                                                         capability_hints=["web3_provider_inject","liquidity_pool_mutate","token_swap_route_simulate"]),
    SiteSpec("magic_eden",     "https://magiceden.io/",                "crypto", 2, "Magic Eden",                                                                      capability_hints=["nft_metadata_ipfs_resolve","web3_provider_inject"]),

    # ── 22. EDUCATION PLATFORMS ──────────────────────────────────────────
    SiteSpec("coursera",       "https://www.coursera.org/",            "education", 2, "Coursera",           "https://www.coursera.org/login",                        capability_hints=["scorm_package_navigate","video_lecture_progress","syllabus_curriculum_traverse"]),
    SiteSpec("udemy",          "https://www.udemy.com/",               "education", 2, "Udemy",              "https://www.udemy.com/join/login-popup/",               capability_hints=["video_lecture_progress","quiz_dom_emulate"]),
    SiteSpec("edx",            "https://www.edx.org/",                 "education", 2, "edX",                "https://courses.edx.org/login",                         capability_hints=["scorm_package_navigate","lms_assignment_upload","certificate_pdf_generate"]),
    SiteSpec("khan_academy",   "https://www.khanacademy.org/",         "education", 1, "Khan Academy",                                                                  capability_hints=["quiz_dom_emulate","video_lecture_progress","flashcard_spaced_repetition"]),
    SiteSpec("duolingo",       "https://www.duolingo.com/",            "education", 2, "Duolingo",           "https://www.duolingo.com/login",                        capability_hints=["quiz_dom_emulate","flashcard_spaced_repetition"]),
    SiteSpec("memrise",        "https://www.memrise.com/",             "education", 2, "Memrise",            "https://www.memrise.com/login/",                        capability_hints=["flashcard_spaced_repetition","video_lecture_progress"]),
    SiteSpec("quizlet",        "https://quizlet.com/",                 "education", 2, "Quizlet",            "https://quizlet.com/login",                             capability_hints=["flashcard_spaced_repetition","quiz_dom_emulate"]),
    SiteSpec("brilliant",      "https://brilliant.org/",               "education", 2, "Brilliant",          "https://brilliant.org/login/",                          capability_hints=["quiz_dom_emulate","video_lecture_progress"]),
    SiteSpec("pluralsight",    "https://www.pluralsight.com/",         "education", 2, "Pluralsight",        requires_login=True,                                     capability_hints=["video_lecture_progress","quiz_dom_emulate"]),
    SiteSpec("skillshare",     "https://www.skillshare.com/",          "education", 2, "Skillshare",         requires_login=True,                                     capability_hints=["video_lecture_progress","peer_review_form_manipulate"]),
    SiteSpec("codecademy",     "https://www.codecademy.com/",          "education", 2, "Codecademy",         "https://www.codecademy.com/login",                      capability_hints=["quiz_dom_emulate","web_ide_monaco_interact"]),
    SiteSpec("teachable",      "https://teachable.com/",               "education", 2, "Teachable",          requires_login=True,                                     capability_hints=["scorm_package_navigate","certificate_pdf_generate"]),
    SiteSpec("udacity",        "https://www.udacity.com/",             "education", 2, "Udacity",            "https://auth.udacity.com/sign-in",                      capability_hints=["video_lecture_progress","peer_review_form_manipulate"]),
    SiteSpec("moodle_demo",    "https://school.moodledemo.net/",       "education", 1, "Moodle Demo",        "https://school.moodledemo.net/login/index.php",         capability_hints=["scorm_package_navigate","lms_assignment_upload","quiz_dom_emulate"]),

    # ── 23. JOB PLATFORMS ────────────────────────────────────────────────
    SiteSpec("indeed",         "https://www.indeed.com/",              "jobs",   2, "Indeed",                "https://secure.indeed.com/account/login",               capability_hints=["ats_field_map","one_click_apply_hook","salary_range_extract"]),
    SiteSpec("glassdoor",      "https://www.glassdoor.com/",           "jobs",   2, "Glassdoor",             "https://www.glassdoor.com/profile/login_input.htm",     capability_hints=["salary_range_extract","company_review_aggregate"]),
    SiteSpec("monster",        "https://www.monster.com/",             "jobs",   2, "Monster",               "https://www.monster.com/profile/detail/",               capability_hints=["ats_field_map","resume_parser_emulate"]),
    SiteSpec("ziprecruiter",   "https://www.ziprecruiter.com/",        "jobs",   2, "ZipRecruiter",          "https://www.ziprecruiter.com/login",                    capability_hints=["one_click_apply_hook","salary_range_extract"]),
    SiteSpec("wellfound",      "https://wellfound.com/",               "jobs",   2, "Wellfound (AngelList)", "https://wellfound.com/login",                           capability_hints=["ats_field_map","company_review_aggregate"]),
    SiteSpec("dice",           "https://www.dice.com/",                "jobs",   2, "Dice",                  "https://www.dice.com/dashboard/login",                  capability_hints=["ats_field_map","resume_parser_emulate"]),
    SiteSpec("remoteco",       "https://remote.co/",                   "jobs",   1, "Remote.co",                                                                       capability_hints=["ats_field_map"]),
    SiteSpec("weworkremotely", "https://weworkremotely.com/",          "jobs",   1, "We Work Remotely",                                                                capability_hints=["ats_field_map","salary_range_extract"]),
    SiteSpec("hired",          "https://hired.com/",                   "jobs",   2, "Hired",                 requires_login=True,                                     capability_hints=["assessment_skill_test_ui","salary_range_extract"]),
    SiteSpec("greenhouse_io",  "https://www.greenhouse.io/",           "jobs",   2, "Greenhouse",            requires_login=True,                                     capability_hints=["ats_field_map","one_click_apply_hook"]),
    SiteSpec("lever",          "https://www.lever.co/",                "jobs",   2, "Lever",                 requires_login=True,                                     capability_hints=["ats_field_map","interview_scheduler_integrate"]),
    SiteSpec("workday",        "https://www.workday.com/",             "jobs",   3, "Workday",               requires_login=True,                                     capability_hints=["ats_field_map","resume_parser_emulate","offer_docusign_pipeline"]),
    SiteSpec("bamboohr",       "https://www.bamboohr.com/",            "jobs",   2, "BambooHR",              requires_login=True,                                     capability_hints=["ats_field_map","custom_field_mutate"]),

    # ── 24. CMS & SITE BUILDERS ──────────────────────────────────────────
    SiteSpec("wordpress_admin","https://wordpress.org/",               "cms",    2, "WordPress",             capability_hints=["wysiwyg_block_manipulate","plugin_extension_install","seo_metadata_configure","draft_publish_revision"]),
    SiteSpec("webflow",        "https://webflow.com/",                 "cms",    2, "Webflow",               "https://webflow.com/dashboard",                         capability_hints=["drag_drop_datatransfer","wysiwyg_block_manipulate","seo_metadata_configure"]),
    SiteSpec("wix",            "https://www.wix.com/",                 "cms",    2, "Wix",                   "https://users.wix.com/signin",                          capability_hints=["wysiwyg_block_manipulate","drag_drop_datatransfer","media_library_manage"]),
    SiteSpec("squarespace",    "https://www.squarespace.com/",         "cms",    2, "Squarespace",           "https://account.squarespace.com/",                      capability_hints=["wysiwyg_block_manipulate","media_library_manage"]),
    SiteSpec("ghost_cms",      "https://ghost.org/",                   "cms",    2, "Ghost CMS",             capability_hints=["draft_publish_revision","seo_metadata_configure","headless_api_generate"]),
    SiteSpec("shopify",        "https://www.shopify.com/",             "cms",    2, "Shopify",               "https://accounts.shopify.com/store-login",              capability_hints=["wysiwyg_block_manipulate","plugin_extension_install","headless_api_generate"]),
    SiteSpec("contentful",     "https://www.contentful.com/",          "cms",    2, "Contentful",            "https://be.contentful.com/login",                       capability_hints=["headless_api_generate","taxonomy_routing_configure","draft_publish_revision"]),
    SiteSpec("sanity_io",      "https://www.sanity.io/",               "cms",    2, "Sanity.io",             "https://www.sanity.io/login",                           capability_hints=["headless_api_generate","wysiwyg_block_manipulate"]),
    SiteSpec("strapi",         "https://strapi.io/",                   "cms",    2, "Strapi",                capability_hints=["headless_api_generate","taxonomy_routing_configure"]),
    SiteSpec("drupal",         "https://www.drupal.org/",              "cms",    2, "Drupal",                capability_hints=["taxonomy_routing_configure","plugin_extension_install","wysiwyg_block_manipulate"]),
    SiteSpec("joomla",         "https://www.joomla.org/",              "cms",    2, "Joomla",                capability_hints=["plugin_extension_install","taxonomy_routing_configure"]),
    SiteSpec("prismic",        "https://prismic.io/",                  "cms",    2, "Prismic",               requires_login=True,                                     capability_hints=["headless_api_generate","draft_publish_revision"]),
    SiteSpec("builder_io",     "https://www.builder.io/",              "cms",    2, "Builder.io",            requires_login=True,                                     capability_hints=["drag_drop_datatransfer","wysiwyg_block_manipulate"]),

    # ── 25. SEARCH ENGINES ───────────────────────────────────────────────
    SiteSpec("google",         "https://www.google.com/",              "search", 2, "Google",                aliases=["google_search"],                               protected=True, capability_hints=["serp_dom_parse","knowledge_graph_extract","dork_query_inject","autocomplete_api_intercept"]),
    SiteSpec("bing",           "https://www.bing.com/",                "search", 2, "Bing",                                                                            capability_hints=["serp_dom_parse","shopping_feed_parse","map_local_pack_extract"]),
    SiteSpec("duckduckgo",     "https://duckduckgo.com/",              "search", 1, "DuckDuckGo",            aliases=["ddg"],                                         capability_hints=["serp_dom_parse","autocomplete_api_intercept"]),
    SiteSpec("brave_search",   "https://search.brave.com/",            "search", 1, "Brave Search",          aliases=["brave"],                                       capability_hints=["serp_dom_parse","autocomplete_api_intercept"]),
    SiteSpec("yandex",         "https://yandex.com/",                  "search", 3, "Yandex",                                                                          capability_hints=["serp_dom_parse","knowledge_graph_extract"]),
    SiteSpec("startpage",      "https://www.startpage.com/",           "search", 1, "Startpage",                                                                       capability_hints=["serp_dom_parse"]),
    SiteSpec("ecosia",         "https://www.ecosia.org/",              "search", 1, "Ecosia",                                                                          capability_hints=["serp_dom_parse","autocomplete_api_intercept"]),
    SiteSpec("kagi",           "https://kagi.com/",                    "search", 2, "Kagi",                  requires_login=True,                                     capability_hints=["serp_dom_parse","knowledge_graph_extract"]),
    SiteSpec("perplexity",     "https://www.perplexity.ai/",           "search", 2, "Perplexity",            capability_hints=["serp_dom_parse","sse_stream_parse","knowledge_graph_extract"]),
    SiteSpec("you_com",        "https://you.com/",                     "search", 2, "You.com",                                                                         capability_hints=["serp_dom_parse","sse_stream_parse"]),
    SiteSpec("qwant",          "https://www.qwant.com/",               "search", 1, "Qwant",                                                                           capability_hints=["serp_dom_parse","map_local_pack_extract"]),
    SiteSpec("naver",          "https://www.naver.com/",               "search", 3, "Naver",                                                                           capability_hints=["serp_dom_parse","knowledge_graph_extract"]),
    SiteSpec("baidu",          "https://www.baidu.com/",               "search", 4, "Baidu",                                                                           capability_hints=["serp_dom_parse","knowledge_graph_extract"]),
    SiteSpec("wolframalpha",   "https://www.wolframalpha.com/",        "search", 2, "Wolfram Alpha",                                                                   capability_hints=["serp_dom_parse","api_interactive_shell"]),

    # ── 26. MAPS & LOCAL DISCOVERY ───────────────────────────────────────
    SiteSpec("google_maps",    "https://maps.google.com/",             "maps",   3, "Google Maps",           protected=True, capability_hints=["tile_vector_canvas_query","geocode_reverse_geocode","routing_polyline_extract","place_poi_card_scrape"]),
    SiteSpec("openstreetmap",  "https://www.openstreetmap.org/",       "maps",   1, "OpenStreetMap",                                                                   capability_hints=["tile_vector_canvas_query","geocode_reverse_geocode","routing_polyline_extract"]),
    SiteSpec("yelp",           "https://www.yelp.com/",                "maps",   2, "Yelp",                  "https://www.yelp.com/login",                            capability_hints=["place_poi_card_scrape","review_paginate_filter","operating_hours_parse"]),
    SiteSpec("tripadvisor",    "https://www.tripadvisor.com/",         "maps",   2, "TripAdvisor",                                                                     capability_hints=["place_poi_card_scrape","review_paginate_filter"]),
    SiteSpec("bing_maps",      "https://www.bing.com/maps",            "maps",   2, "Bing Maps",                                                                       capability_hints=["tile_vector_canvas_query","routing_polyline_extract"]),
    SiteSpec("mapbox",         "https://www.mapbox.com/",              "maps",   2, "Mapbox",                capability_hints=["tile_vector_canvas_query","geocode_reverse_geocode"]),
    SiteSpec("here_maps",      "https://maps.here.com/",               "maps",   2, "HERE Maps",                                                                       capability_hints=["tile_vector_canvas_query","routing_polyline_extract"]),
    SiteSpec("foursquare",     "https://foursquare.com/",              "maps",   2, "Foursquare",            "https://foursquare.com/user/login",                     capability_hints=["place_poi_card_scrape","operating_hours_parse"]),
    SiteSpec("doordash",       "https://www.doordash.com/",            "maps",   3, "DoorDash",              "https://identity.doordash.com/signin",                  capability_hints=["menu_cart_state","delivery_fee_calculate","geolocation_radius_search"]),
    SiteSpec("uber_eats",      "https://www.ubereats.com/",            "maps",   3, "Uber Eats",             requires_login=True,                                     capability_hints=["menu_cart_state","delivery_fee_calculate"]),
    SiteSpec("deliveroo",      "https://deliveroo.co.uk/",             "maps",   2, "Deliveroo",             "https://deliveroo.co.uk/login",                         capability_hints=["menu_cart_state","delivery_fee_calculate"]),
    SiteSpec("zomato",         "https://www.zomato.com/",              "maps",   2, "Zomato",                capability_hints=["place_poi_card_scrape","menu_cart_state","review_paginate_filter"]),
    SiteSpec("waze",           "https://www.waze.com/",                "maps",   2, "Waze",                  capability_hints=["routing_polyline_extract","tile_vector_canvas_query"]),

    # ── 27. TRAVEL SYSTEMS ───────────────────────────────────────────────
    SiteSpec("booking_travel", "https://www.booking.com/flights/",     "travel", 3, "Booking.com Flights",                                                            capability_hints=["fare_calendar_matrix_parse","gds_interface_emulate","dynamic_pricing_scarcity"]),
    SiteSpec("airbnb_travel",  "https://www.airbnb.com/",              "travel", 3, "Airbnb",                "https://www.airbnb.com/login",                          capability_hints=["calendar_availability_parse","gds_interface_emulate"]),
    SiteSpec("expedia",        "https://www.expedia.com/",             "travel", 3, "Expedia",               "https://www.expedia.com/login",                         capability_hints=["fare_calendar_matrix_parse","multi_city_routing_input","dynamic_pricing_scarcity"]),
    SiteSpec("skyscanner",     "https://www.skyscanner.com/",          "travel", 3, "Skyscanner",                                                                      capability_hints=["fare_calendar_matrix_parse","multi_city_routing_input"]),
    SiteSpec("kayak",          "https://www.kayak.com/",               "travel", 3, "Kayak",                                                                           capability_hints=["fare_calendar_matrix_parse","multi_city_routing_input","dynamic_pricing_scarcity"]),
    SiteSpec("priceline",      "https://www.priceline.com/",           "travel", 2, "Priceline",             capability_hints=["fare_calendar_matrix_parse","dynamic_pricing_scarcity"]),
    SiteSpec("agoda",          "https://www.agoda.com/",               "travel", 3, "Agoda",                                                                           capability_hints=["calendar_availability_parse","dynamic_pricing_scarcity"]),
    SiteSpec("hostelworld",    "https://www.hostelworld.com/",         "travel", 2, "Hostelworld",           capability_hints=["calendar_availability_parse","review_paginate_filter"]),
    SiteSpec("rome2rio",       "https://www.rome2rio.com/",            "travel", 1, "Rome2rio",                                                                        capability_hints=["multi_city_routing_input","routing_polyline_extract"]),
    SiteSpec("flightradar24",  "https://www.flightradar24.com/",       "travel", 2, "Flightradar24",                                                                   capability_hints=["tile_vector_canvas_query","itinerary_pnr_retrieve"]),
    SiteSpec("trainline",      "https://www.trainline.com/",           "travel", 2, "Trainline",             "https://www.trainline.com/booking/login",               capability_hints=["seat_map_canvas_svg_interact","boarding_pass_qr_extract"]),
    SiteSpec("viator",         "https://www.viator.com/",              "travel", 2, "Viator",                                                                          capability_hints=["calendar_availability_parse","review_paginate_filter"]),
    SiteSpec("trivago",        "https://www.trivago.com/",             "travel", 2, "Trivago",                                                                         capability_hints=["fare_calendar_matrix_parse","dynamic_pricing_scarcity"]),

    # ── 28. AI PLATFORMS ─────────────────────────────────────────────────
    SiteSpec("chatgpt",        "https://chatgpt.com/",                 "ai",     3, "ChatGPT",               "https://chatgpt.com/auth/login",                        capability_hints=["sse_stream_parse","context_window_manage","artifact_code_execute","custom_agent_create"]),
    SiteSpec("claude_ai",      "https://claude.ai/",                   "ai",     3, "Claude.ai",             "https://claude.ai/login",                               capability_hints=["sse_stream_parse","context_window_manage","artifact_code_execute"]),
    SiteSpec("gemini",         "https://gemini.google.com/",           "ai",     3, "Google Gemini",         requires_login=True,                                     protected=True, capability_hints=["sse_stream_parse","voice_webrtc_hook","context_window_manage"]),
    SiteSpec("perplexity_ai",  "https://www.perplexity.ai/",           "ai",     2, "Perplexity AI",         capability_hints=["sse_stream_parse","knowledge_graph_extract"]),
    SiteSpec("poe",            "https://poe.com/",                     "poe",    2, "Poe",                   "https://poe.com/login",                                 capability_hints=["sse_stream_parse","model_selection_mutate"]),
    SiteSpec("elevenlabs",     "https://elevenlabs.io/",               "ai",     2, "ElevenLabs",            "https://elevenlabs.io/sign-in",                         capability_hints=["voice_webrtc_hook","api_key_token_generate"]),
    SiteSpec("character_ai",   "https://character.ai/",                "ai",     2, "Character.AI",          "https://character.ai/login",                            capability_hints=["sse_stream_parse","custom_agent_create"]),
    SiteSpec("midjourney",     "https://www.midjourney.com/",          "ai",     3, "Midjourney Web",        requires_login=True,                                     capability_hints=["canvas_image_mask_edit","prompt_injection_detect"]),
    SiteSpec("huggingchat",    "https://huggingface.co/chat/",         "ai",     2, "HuggingChat",           "https://huggingface.co/login",                          capability_hints=["sse_stream_parse","model_selection_mutate"]),
    SiteSpec("copilot",        "https://copilot.microsoft.com/",       "ai",     2, "Microsoft Copilot",     requires_login=True,                                     capability_hints=["sse_stream_parse","artifact_code_execute"]),
    SiteSpec("jasper_ai",      "https://www.jasper.ai/",               "ai",     2, "Jasper",                requires_login=True,                                     capability_hints=["sse_stream_parse","custom_agent_create"]),
    SiteSpec("replika",        "https://replika.com/",                 "ai",     2, "Replika",               "https://replika.com/login",                             capability_hints=["sse_stream_parse","voice_webrtc_hook"]),
    SiteSpec("leonardo_ai",    "https://app.leonardo.ai/",             "ai",     2, "Leonardo.ai",           "https://app.leonardo.ai/auth/login",                    capability_hints=["canvas_image_mask_edit","api_key_token_generate"]),
    SiteSpec("mistral_chat",   "https://chat.mistral.ai/",             "ai",     2, "Mistral Chat",          "https://chat.mistral.ai/auth/",                         capability_hints=["sse_stream_parse","model_selection_mutate"]),

    # ── 29. DASHBOARDS & ADMIN PANELS ────────────────────────────────────
    SiteSpec("grafana",        "https://play.grafana.org/",            "dashboard", 1, "Grafana (Demo)",                                                               capability_hints=["timeseries_chart_extract","promql_sql_query_input","alert_threshold_configure","widget_drag_drop_layout"]),
    SiteSpec("metabase",       "https://www.metabase.com/",            "dashboard", 2, "Metabase",           requires_login=True,                                     capability_hints=["promql_sql_query_input","timeseries_chart_extract","csv_excel_export_trigger"]),
    SiteSpec("kibana",         "https://demo.elastic.co/",             "dashboard", 2, "Kibana (Demo)",                                                               capability_hints=["log_aggregation_traverse","timeseries_chart_extract","alert_threshold_configure"]),
    SiteSpec("datadog",        "https://www.datadoghq.com/",           "dashboard", 3, "Datadog",            requires_login=True,                                     capability_hints=["timeseries_chart_extract","alert_threshold_configure","log_aggregation_traverse"]),
    SiteSpec("newrelic",       "https://one.newrelic.com/",            "dashboard", 3, "New Relic",          requires_login=True,                                     capability_hints=["timeseries_chart_extract","alert_threshold_configure"]),
    SiteSpec("mixpanel",       "https://mixpanel.com/",                "dashboard", 2, "Mixpanel",           requires_login=True,                                     capability_hints=["timeseries_chart_extract","csv_excel_export_trigger","user_role_provision"]),
    SiteSpec("amplitude",      "https://amplitude.com/",               "dashboard", 2, "Amplitude",          requires_login=True,                                     capability_hints=["timeseries_chart_extract","user_role_provision"]),
    SiteSpec("matomo",         "https://demo.matomo.cloud/",           "dashboard", 1, "Matomo (Demo)",                                                               capability_hints=["timeseries_chart_extract","csv_excel_export_trigger"]),
    SiteSpec("plausible",      "https://plausible.io/",                "dashboard", 1, "Plausible",          capability_hints=["timeseries_chart_extract","dark_mode_theme_toggle"]),
    SiteSpec("posthog",        "https://app.posthog.com/",             "dashboard", 2, "PostHog",            requires_login=True,                                     capability_hints=["timeseries_chart_extract","api_interactive_shell"]),
    SiteSpec("tableau_public", "https://public.tableau.com/",          "dashboard", 2, "Tableau Public",                                                              capability_hints=["timeseries_chart_extract","csv_excel_export_trigger"]),
    SiteSpec("looker_studio",  "https://lookerstudio.google.com/",     "dashboard", 2, "Looker Studio",      requires_login=True,                                     protected=True, capability_hints=["timeseries_chart_extract","datasource_connect_flow"]),
    SiteSpec("vercel_dash",    "https://vercel.com/dashboard",         "dashboard", 2, "Vercel Dashboard",   requires_login=True,                                     capability_hints=["ci_cd_log_stream","alert_threshold_configure"]),

    # ── 30. FRONTIER / UNKNOWN WEB ───────────────────────────────────────
    SiteSpec("demoqa",              "https://demoqa.com/",                  "frontier", 1, "DemoQA",             aliases=["demo_qa"],                                 capability_hints=["unknown_affordance_hypothesize","shadow_dom_penetrate","fuzzy_unlabeled_input_match"]),
    SiteSpec("the_internet",        "https://the-internet.herokuapp.com/",  "frontier", 1, "The Internet",       "https://the-internet.herokuapp.com/login",          capability_hints=["recursive_iframe_switch","shadow_dom_penetrate","legacy_activex_workaround"]),
    SiteSpec("uitestingplayground", "https://uitestingplayground.com/",     "frontier", 1, "UI Testing Playground",                                                    capability_hints=["fuzzy_unlabeled_input_match","obfuscated_state_track","heuristic_pagination_predict"]),
    SiteSpec("owasp_juice",         "https://juice-shop.herokuapp.com/",    "frontier", 1, "OWASP Juice Shop",                                                         capability_hints=["undoc_api_endpoint_infer","shadow_dom_penetrate","dynamic_payload_reconstruct"]),
    SiteSpec("opencart_demo",       "https://demo.opencart.com/",           "frontier", 1, "OpenCart Demo",                                                            capability_hints=["unknown_affordance_hypothesize","multi_facet_filter"]),
    SiteSpec("automationpractice",  "https://automationpractice.pl/",       "frontier", 1, "Automation Practice",                                                      capability_hints=["checkout_pipeline_traverse","multi_facet_filter"]),
    SiteSpec("magento_test",        "https://magento.softwaretestingboard.com/", "frontier", 1, "Magento Test Store",                                                  capability_hints=["multi_facet_filter","checkout_pipeline_traverse","undoc_api_endpoint_infer"]),
    SiteSpec("w3schools_tryit",     "https://www.w3schools.com/html/tryit.asp", "frontier", 1, "W3Schools Try It",                                                    capability_hints=["recursive_iframe_switch","web_ide_monaco_interact"]),
    SiteSpec("cpanel_demo",         "https://democpanel.com/",              "frontier", 2, "cPanel Demo",                                                              capability_hints=["legacy_mainframe_wrapper_navigate","unknown_affordance_hypothesize"]),
    SiteSpec("routerlogin",         "http://192.168.1.1/",                  "frontier", 2, "Router Admin Panel",                                                       capability_hints=["legacy_mainframe_wrapper_navigate","undoc_api_endpoint_infer"]),
    SiteSpec("phpmyadmin_demo",     "https://demo.phpmyadmin.net/",         "frontier", 2, "phpMyAdmin Demo",                                                          capability_hints=["undoc_api_endpoint_infer","legacy_mainframe_wrapper_navigate"]),
    SiteSpec("wikipedia_simple",    "https://simple.wikipedia.org/",        "frontier", 1, "Simple Wikipedia",                                                         capability_hints=["wiki_sticky_extract","namespace_traverse","workflow_reversal_infer"]),
    SiteSpec("codepen_challenges",  "https://codepen.io/challenges/",       "frontier", 1, "CodePen Challenges",                                                       capability_hints=["web_ide_monaco_interact","unknown_affordance_hypothesize"]),
    SiteSpec("internet_archive",    "https://archive.org/",                 "frontier", 1, "Internet Archive",                                                         capability_hints=["unknown_affordance_hypothesize","dead_link_error_path_recover","cache_archive_follow"]),
    SiteSpec("glitch_editor",       "https://glitch.com/",                  "frontier", 1, "Glitch Editor",         "https://glitch.com/signin",                     capability_hints=["web_ide_monaco_interact","recursive_iframe_switch","undoc_api_endpoint_infer"]),
    SiteSpec("phpbb_demo",          "https://www.phpbb.com/community/",     "frontier", 1, "phpBB Demo",                                                               capability_hints=["bbcode_markdown_generate","legacy_mainframe_wrapper_navigate"]),
    SiteSpec("netlify_cms_demo",    "https://cms-demo.netlify.com/",        "frontier", 1, "Netlify CMS Demo",                                                         capability_hints=["wysiwyg_block_manipulate","unknown_affordance_hypothesize"]),

    # ── Additional sites to reach 500 ────────────────────────────────────

    # More Social
    SiteSpec("weibo",           "https://weibo.com/",                   "social", 4, "Weibo",                 requires_login=True,                                     capability_hints=["infinite_scroll_dom","state_mutation_like","multi_part_media_upload"]),
    SiteSpec("odnoklassniki",   "https://ok.ru/",                       "social", 3, "Odnoklassniki",         "https://ok.ru/login",                                   capability_hints=["social_graph_follow","state_mutation_like"]),
    SiteSpec("vero",            "https://vero.co/",                     "social", 2, "Vero",                  "https://vero.co/sign-in",                               capability_hints=["social_graph_follow","multi_part_media_upload"]),

    # More Forums
    SiteSpec("somethingawful",  "https://forums.somethingawful.com/",   "forum",  2, "Something Awful",       requires_login=True,                                     capability_hints=["hierarchical_thread_parse","bbcode_markdown_generate"]),
    SiteSpec("blind",           "https://www.teamblind.com/",           "forum",  2, "Blind",                 "https://www.teamblind.com/login",                       capability_hints=["anonymous_vs_auth_session","karma_reputation_vote"]),
    SiteSpec("nairaland",       "https://www.nairaland.com/",           "forum",  1, "Nairaland",                                                                       capability_hints=["hierarchical_thread_parse","pagination_state_management"]),

    # More Chat
    SiteSpec("line_web",        "https://line.me/",                     "chat",   3, "LINE Web",              requires_login=True,                                     capability_hints=["realtime_dom_mutation_observe","file_attachment_stream"]),
    SiteSpec("viber_web",       "https://www.viber.com/",               "chat",   3, "Viber Web",             requires_login=True,                                     capability_hints=["realtime_dom_mutation_observe","emoji_reaction_matrix"]),

    # More Video
    SiteSpec("niconico",        "https://www.nicovideo.jp/",            "video",  3, "NicoNico",              "https://secure.nicovideo.jp/secure/login",              capability_hints=["live_chat_websocket_parse","html5_player_event_hook"]),
    SiteSpec("younow",          "https://www.younow.com/",              "video",  2, "YouNow",                "https://www.younow.com/login",                          capability_hints=["live_chat_websocket_parse","html5_player_event_hook"]),

    # More Audio
    SiteSpec("qobuz",           "https://www.qobuz.com/",               "audio",  2, "Qobuz",                 "https://www.qobuz.com/login",                           capability_hints=["audio_context_background","drm_handshake_observe"]),
    SiteSpec("boomplay",        "https://www.boomplay.com/",            "audio",  2, "Boomplay",                                                                        capability_hints=["audio_blob_intercept","artist_graph_traverse"]),
    SiteSpec("napster",         "https://www.napster.com/",             "audio",  2, "Napster",               "https://www.napster.com/login",                         capability_hints=["audio_context_background","playlist_array_manipulate"]),

    # More Image
    SiteSpec("getty_images",    "https://www.gettyimages.com/",         "image",  2, "Getty Images",                                                                   capability_hints=["high_res_asset_extract","license_copyright_parse","watermark_detect"]),
    SiteSpec("alamy",           "https://www.alamy.com/",               "image",  2, "Alamy",                                                                          capability_hints=["high_res_asset_extract","license_copyright_parse"]),

    # More News
    SiteSpec("forbes",          "https://www.forbes.com/",              "news",   2, "Forbes",                                                                         capability_hints=["schema_org_jsonld_parse","paywall_bypass_attempt"]),
    SiteSpec("huffpost",        "https://www.huffpost.com/",            "news",   2, "HuffPost",                                                                       capability_hints=["schema_org_jsonld_parse","author_archive_traverse"]),
    SiteSpec("ft",              "https://www.ft.com/",                  "news",   4, "Financial Times",       requires_login=True,                                     capability_hints=["paywall_bypass_attempt","schema_org_jsonld_parse"]),

    # More Blog
    SiteSpec("typepad",         "https://www.typepad.com/",             "blog",   2, "Typepad",               requires_login=True,                                     capability_hints=["chronological_archive_navigate","rss_atom_feed_detect"]),
    SiteSpec("livejournal",     "https://www.livejournal.com/",         "blog",   2, "LiveJournal",           "https://www.livejournal.com/login.bml",                 capability_hints=["chronological_archive_navigate","tag_category_taxonomy_map"]),

    # More Ecommerce
    SiteSpec("flipkart",        "https://www.flipkart.com/",            "ecommerce", 3, "Flipkart",                                                                    capability_hints=["multi_facet_filter","cart_state_manipulate","dynamic_pricing_sku_track"]),
    SiteSpec("rakuten",         "https://www.rakuten.com/",             "ecommerce", 2, "Rakuten",                                                                     capability_hints=["multi_facet_filter","promo_code_validate"]),
    SiteSpec("mercadolibre",    "https://www.mercadolibre.com/",        "ecommerce", 3, "MercadoLibre",                                                                capability_hints=["multi_facet_filter","bid_offer_submit"]),

    # More Marketplace
    SiteSpec("thumbtack",       "https://www.thumbtack.com/",           "marketplace", 2, "Thumbtack",                                                                 capability_hints=["geolocation_radius_search","calendar_availability_parse"]),
    SiteSpec("peopleperhour",   "https://www.peopleperhour.com/",       "marketplace", 2, "PeoplePerHour",     "https://www.peopleperhour.com/site/login",              capability_hints=["bid_offer_submit","reputation_score_calculate"]),
    SiteSpec("guru",            "https://www.guru.com/",                "marketplace", 2, "Guru.com",          "https://www.guru.com/login.aspx",                      capability_hints=["bid_offer_submit","escrow_simulate"]),

    # More SaaS
    SiteSpec("surveymonkey",    "https://www.surveymonkey.com/",        "saas",   2, "SurveyMonkey",          "https://www.surveymonkey.com/user/sign-in/",            capability_hints=["drag_drop_datatransfer","export_import_pipeline"]),
    SiteSpec("box",             "https://www.box.com/",                 "saas",   3, "Box",                   "https://account.box.com/login",                         capability_hints=["role_permission_alter","export_import_pipeline","storage_bucket_traverse"]),
    SiteSpec("dropbox",         "https://www.dropbox.com/",             "saas",   3, "Dropbox",               "https://www.dropbox.com/login",                         capability_hints=["storage_bucket_traverse","export_import_pipeline","role_permission_alter"]),

    # More Productivity
    SiteSpec("protonmail_cal",  "https://calendar.proton.me/",          "productivity", 2, "Proton Calendar",  requires_login=True,                                    capability_hints=["calendar_availability_parse","bidirectional_link_navigate"]),
    SiteSpec("fantastical",     "https://flexibits.com/fantastical",    "productivity", 2, "Fantastical",                                                               capability_hints=["calendar_availability_parse"]),

    # More Knowledge
    SiteSpec("tiddlywiki",      "https://tiddlywiki.com/",              "knowledge", 1, "TiddlyWiki",                                                                   capability_hints=["bidirectional_link_navigate","namespace_traverse","wysiwyg_markdown_translate"]),
    SiteSpec("bookstack",       "https://www.bookstackapp.com/demo/",   "knowledge", 1, "BookStack Demo",      "https://demo.bookstackapp.com/login",                  capability_hints=["namespace_traverse","version_history_diff"]),

    # More Dev
    SiteSpec("gitpod",          "https://www.gitpod.io/",               "dev",    2, "Gitpod",                "https://gitpod.io/login",                               capability_hints=["web_ide_monaco_interact","jupyter_cell_execute"]),
    SiteSpec("codeium",         "https://codeium.com/",                 "dev",    2, "Codeium",               "https://codeium.com/account/login",                     capability_hints=["web_ide_monaco_interact","api_key_token_generate"]),

    # More Registry
    SiteSpec("go_pkg",          "https://pkg.go.dev/",                  "registry", 1, "Go Packages",                                                                   capability_hints=["dependency_tree_resolve","readme_docs_render"]),
    SiteSpec("cpan",            "https://metacpan.org/",                "registry", 1, "CPAN (MetaCPAN)",                                                               capability_hints=["dependency_tree_resolve","maintainer_graph_traverse"]),

    # More Cloud
    SiteSpec("railway",         "https://railway.app/",                 "cloud",  2, "Railway",               "https://railway.app/login",                             capability_hints=["resource_provision_workflow","serverless_log_tail"]),
    SiteSpec("scaleway",        "https://www.scaleway.com/",            "cloud",  2, "Scaleway",              "https://console.scaleway.com/",                         capability_hints=["resource_provision_workflow","dns_record_mutate"]),

    # More Auth
    SiteSpec("duo",             "https://duo.com/",                     "auth",   3, "Duo Security",          requires_login=True,                                     capability_hints=["mfa_totp_seed_inject","captcha_token_intercept"]),
    SiteSpec("onelogin",        "https://www.onelogin.com/",            "auth",   3, "OneLogin",              requires_login=True,                                     capability_hints=["saml_assertion_intercept","oauth2_oidc_redirect_track"]),

    # More Email
    SiteSpec("skiff_mail",      "https://app.skiff.com/mail/",          "email",  2, "Skiff Mail",            requires_login=True,                                     capability_hints=["pgp_gpg_keyring_dom","alias_disposable_generate"]),
    SiteSpec("startmail",       "https://www.startmail.com/",           "email",  2, "StartMail",             "https://www.startmail.com/login/",                      capability_hints=["pgp_gpg_keyring_dom","alias_disposable_generate"]),

    # More Government
    SiteSpec("portal_gov_br",   "https://www.gov.br/",                  "government", 2, "Portal Gov.br",                                                              capability_hints=["bureaucratic_form_taxonomy","pdf_form_fill_generate"]),
    SiteSpec("edevlet",         "https://www.turkiye.gov.tr/",          "government", 2, "e-Devlet (Turkey)",                                                           capability_hints=["digital_signature_verify","multi_page_session_timeout_circumvent"]),

    # More Finance
    SiteSpec("square",          "https://squareup.com/",                "finance", 2, "Square",               "https://squareup.com/login",                            capability_hints=["transaction_ledger_paginate","virtual_card_generate"]),
    SiteSpec("chime",           "https://www.chime.com/",               "finance", 3, "Chime",                requires_login=True,                                     capability_hints=["virtual_card_generate","transaction_ledger_paginate"]),
    SiteSpec("starling",        "https://www.starlingbank.com/",        "finance", 3, "Starling Bank",        requires_login=True,                                     capability_hints=["transaction_ledger_paginate","virtual_card_generate"]),

    # More Crypto
    SiteSpec("bybit",           "https://www.bybit.com/",               "crypto", 3, "Bybit",                 "https://www.bybit.com/login",                           capability_hints=["orderbook_canvas_parse","token_swap_route_simulate"]),
    SiteSpec("bitfinex",        "https://www.bitfinex.com/",            "crypto", 3, "Bitfinex",              "https://www.bitfinex.com/login",                        capability_hints=["orderbook_canvas_parse","liquidity_pool_mutate"]),

    # More Education
    SiteSpec("masterclass",     "https://www.masterclass.com/",         "education", 2, "MasterClass",         requires_login=True,                                    capability_hints=["video_lecture_progress","syllabus_curriculum_traverse"]),
    SiteSpec("chegg",           "https://www.chegg.com/",               "education", 2, "Chegg",               "https://www.chegg.com/login",                          capability_hints=["quiz_dom_emulate","peer_review_form_manipulate"]),
    SiteSpec("brainly",         "https://brainly.com/",                 "education", 2, "Brainly",                                                                      capability_hints=["quiz_dom_emulate","karma_reputation_vote"]),

    # More Jobs
    SiteSpec("simplyhired",     "https://www.simplyhired.com/",         "jobs",   1, "SimplyHired",                                                                     capability_hints=["ats_field_map","salary_range_extract"]),
    SiteSpec("otta",            "https://otta.com/",                    "jobs",   2, "Otta",                  "https://otta.com/login",                                capability_hints=["ats_field_map","company_review_aggregate"]),
    SiteSpec("braintrust",      "https://www.usebraintrust.com/",       "jobs",   2, "Braintrust",            "https://app.usebraintrust.com/talent/login/",           capability_hints=["assessment_skill_test_ui","reputation_score_calculate"]),

    # More CMS
    SiteSpec("weebly",          "https://www.weebly.com/",              "cms",    2, "Weebly",                "https://www.weebly.com/login",                          capability_hints=["drag_drop_datatransfer","wysiwyg_block_manipulate"]),
    SiteSpec("bigcommerce",     "https://www.bigcommerce.com/",         "cms",    2, "BigCommerce",           requires_login=True,                                     capability_hints=["headless_api_generate","plugin_extension_install"]),
    SiteSpec("typo3",           "https://typo3.org/",                   "cms",    2, "TYPO3",                 capability_hints=["plugin_extension_install","taxonomy_routing_configure"]),

    # More Search
    SiteSpec("dogpile",         "https://www.dogpile.com/",             "search", 1, "Dogpile",                                                                         capability_hints=["serp_dom_parse","autocomplete_api_intercept"]),
    SiteSpec("swisscows",       "https://swisscows.com/",               "search", 1, "Swisscows",                                                                       capability_hints=["serp_dom_parse"]),
    SiteSpec("mojeek",          "https://www.mojeek.com/",              "search", 1, "Mojeek",                                                                          capability_hints=["serp_dom_parse"]),

    # More Maps
    SiteSpec("grab",            "https://www.grab.com/",                "maps",   3, "Grab",                  requires_login=True,                                     capability_hints=["menu_cart_state","delivery_fee_calculate","routing_polyline_extract"]),
    SiteSpec("gojek",           "https://www.gojek.com/",               "maps",   3, "Gojek",                 requires_login=True,                                     capability_hints=["routing_polyline_extract","delivery_fee_calculate"]),

    # More Travel
    SiteSpec("omio",            "https://www.omio.com/",                "travel", 2, "Omio",                  "https://www.omio.com/login",                            capability_hints=["multi_city_routing_input","seat_map_canvas_svg_interact"]),
    SiteSpec("flightaware",     "https://www.flightaware.com/",         "travel", 1, "FlightAware",                                                                     capability_hints=["tile_vector_canvas_query","itinerary_pnr_retrieve"]),
    SiteSpec("cruisecritic",    "https://www.cruisecritic.com/",        "travel", 2, "CruiseCritic",                                                                    capability_hints=["calendar_availability_parse","review_paginate_filter"]),

    # More AI
    SiteSpec("runway_ml",       "https://runwayml.com/",                "ai",     2, "Runway ML",             "https://runwayml.com/login",                            capability_hints=["canvas_image_mask_edit","sse_stream_parse"]),
    SiteSpec("pika_art",        "https://pika.art/",                    "ai",     2, "Pika",                  requires_login=True,                                     capability_hints=["canvas_image_mask_edit","voice_webrtc_hook"]),

    # More Dashboard
    SiteSpec("splunk",          "https://www.splunk.com/",              "dashboard", 3, "Splunk",              requires_login=True,                                    capability_hints=["log_aggregation_traverse","timeseries_chart_extract","promql_sql_query_input"]),
    SiteSpec("appsignal",       "https://www.appsignal.com/",           "dashboard", 2, "AppSignal",           requires_login=True,                                    capability_hints=["timeseries_chart_extract","alert_threshold_configure"]),
    SiteSpec("honeybadger",     "https://www.honeybadger.io/",          "dashboard", 2, "Honeybadger",         requires_login=True,                                    capability_hints=["alert_threshold_configure","log_aggregation_traverse"]),

    # ── Final 7 to reach 500 ─────────────────────────────────────────────
    SiteSpec("hatena_blog",     "https://hatenablog.com/",              "blog",   2, "Hatena Blog",                                                                    capability_hints=["rss_atom_feed_detect","tag_category_taxonomy_map"]),
    SiteSpec("runbox",          "https://runbox.com/",                  "email",  2, "Runbox",                "https://runbox.com/login/",                             capability_hints=["pgp_gpg_keyring_dom","thread_collapse_expand"]),
    SiteSpec("xenforo_demo",    "https://xenforo.com/community/",       "forum",  1, "XenForo Demo",          "https://xenforo.com/community/login/",                  capability_hints=["hierarchical_thread_parse","bbcode_markdown_generate","pagination_state_management"]),
    SiteSpec("nextcloud_demo",  "https://try.nextcloud.com/",           "saas",   1, "Nextcloud Demo",        capability_hints=["storage_bucket_traverse","role_permission_alter","export_import_pipeline"]),
    SiteSpec("gitea_io",        "https://about.gitea.com/",             "dev",    1, "Gitea.com",             capability_hints=["commit_tree_navigate","issue_state_mutate"]),
    SiteSpec("snyk",            "https://snyk.io/",                     "dev",    2, "Snyk",                  "https://app.snyk.io/login",                             capability_hints=["cve_vulnerability_map","dependency_tree_resolve"]),
    SiteSpec("semrush",         "https://www.semrush.com/",             "dashboard", 2, "SEMrush",              requires_login=True,                                    capability_hints=["serp_dom_parse","timeseries_chart_extract","keyword_research"]),
]


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

_INDEX: Dict[str, SiteSpec] = {}
for _s in _SITES:
    _INDEX[_s.key] = _s
    for _alias in (_s.aliases or []):
        _INDEX[_alias.lower().replace(" ", "_")] = _s


def resolve_site(key: str) -> Optional[EnvironmentEntry]:
    """Resolve a site key (or alias) to an EnvironmentEntry, or None."""
    spec = _INDEX.get(key) or _INDEX.get(key.lower().replace("-", "_"))
    return spec.to_env_entry() if spec else None


def get_spec(key: str) -> Optional[SiteSpec]:
    """Return the full SiteSpec for a key, or None."""
    return _INDEX.get(key) or _INDEX.get(key.lower().replace("-", "_"))


def list_sites(
    category: Optional[str] = None,
    max_difficulty: int = 5,
    require_no_login: bool = False,
) -> List[SiteSpec]:
    """Return deduplicated sites with optional filters."""
    sites = list(_INDEX.values())
    seen: set = set()
    unique = []
    for s in sites:
        if s.key not in seen:
            seen.add(s.key)
            unique.append(s)

    if category:
        unique = [s for s in unique if s.category == category]
    unique = [s for s in unique if s.difficulty <= max_difficulty]
    if require_no_login:
        unique = [s for s in unique if not s.requires_login]
    return unique


def sites_by_category(category: str) -> List[SiteSpec]:
    return list_sites(category=category)


def site_keys_for_campaign(
    categories: Optional[List[str]] = None,
    max_difficulty: int = 3,
    limit: int = 500,
) -> List[str]:
    """
    Return a curated list of site keys for a bulk campaign.
    Sorted by category then difficulty (easiest first).
    Covers all 30 categories when categories=None.
    """
    cats = categories or SITE_CATEGORIES
    result = []
    for cat in cats:
        batch = list_sites(category=cat, max_difficulty=max_difficulty)
        batch.sort(key=lambda s: s.difficulty)
        result.extend(s.key for s in batch)

    # deduplicate preserving order
    seen: set = set()
    deduped = []
    for k in result:
        if k not in seen:
            seen.add(k)
            deduped.append(k)

    return deduped[:limit]

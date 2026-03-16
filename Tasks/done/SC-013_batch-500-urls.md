# SC-013 — Батч 500 URL: расширенный прогон

## Цель

Проверить поведение системы при 500 URL — производительность, coverage нишевых тем,
качество similarity. Сравнить с SC-012 (190 URL, 109 docs).

**Блокер**: SC-011 выполнена (URL-режим + параллельный фетч).

---

## Шаг 1 — Запустить индексацию

```bash
python3 << 'SCRIPT'
import json, subprocess

urls = [
    # === AMPLITUDE ===
    "https://amplitude.com/",
    "https://amplitude.com/product-analytics",
    "https://amplitude.com/session-replay",
    "https://amplitude.com/feature-experimentation",
    "https://amplitude.com/pricing",
    "https://amplitude.com/blog/product-analytics",
    "https://amplitude.com/blog/amplitude-vs-mixpanel",
    "https://amplitude.com/blog/product-analytics-tools",
    "https://amplitude.com/blog/product-analytics-pricing",
    "https://amplitude.com/blog/warehouse-native-analytics",
    "https://amplitude.com/blog/customer-success-stories",
    "https://amplitude.com/customers",
    "https://amplitude.com/mobile-analytics",
    "https://www.docs.developers.amplitude.com/",
    "https://amplitude.com/blog/what-is-product-analytics",
    "https://amplitude.com/blog/product-analytics-metrics",
    "https://amplitude.com/blog/retention-analysis",
    "https://amplitude.com/blog/funnel-analysis",
    "https://amplitude.com/blog/cohort-analysis",
    "https://amplitude.com/blog/user-segmentation",
    # === MIXPANEL ===
    "https://mixpanel.com/",
    "https://mixpanel.com/product-analytics/",
    "https://mixpanel.com/session-replay/",
    "https://mixpanel.com/pricing/",
    "https://mixpanel.com/blog/",
    "https://mixpanel.com/compare/amplitude/",
    "https://mixpanel.com/blog/mixpanel-vs-amplitude/",
    "https://mixpanel.com/blog/product-analytics-tools/",
    "https://mixpanel.com/customers/",
    "https://mixpanel.com/blog/case-studies/",
    "https://mixpanel.com/mobile-analytics/",
    "https://developer.mixpanel.com/docs",
    "https://docs.mixpanel.com/docs/reports/funnels",
    "https://docs.mixpanel.com/docs/reports/retention",
    "https://docs.mixpanel.com/docs/users/cohorts",
    "https://docs.mixpanel.com/docs/reports/funnels/funnels-advanced",
    "https://mixpanel.com/blog/what-is-product-analytics/",
    "https://mixpanel.com/blog/product-analytics-examples/",
    "https://mixpanel.com/blog/retention-rate/",
    "https://mixpanel.com/blog/event-tracking/",
    # === POSTHOG ===
    "https://posthog.com/",
    "https://posthog.com/product-analytics",
    "https://posthog.com/session-replay",
    "https://posthog.com/feature-flags",
    "https://posthog.com/experiments",
    "https://posthog.com/pricing",
    "https://posthog.com/blog/best-product-analytics-tools",
    "https://posthog.com/blog/best-amplitude-alternatives",
    "https://posthog.com/blog/best-mixpanel-alternatives",
    "https://posthog.com/blog/best-heap-alternatives",
    "https://posthog.com/blog/best-open-source-analytics-tools",
    "https://posthog.com/blog/open-source-analytics-tools",
    "https://posthog.com/blog/google-analytics-alternatives",
    "https://posthog.com/blog/product-analytics-tips",
    "https://posthog.com/blog/how-to-choose-analytics-tool",
    "https://posthog.com/blog/what-is-a-data-warehouse",
    "https://posthog.com/blog/cdp-vs-analytics",
    "https://posthog.com/docs",
    "https://posthog.com/customers",
    "https://posthog.com/customers/supabase",
    "https://posthog.com/customers/vendasta",
    "https://posthog.com/blog/what-is-product-analytics",
    "https://posthog.com/blog/product-analytics-vs-web-analytics",
    "https://posthog.com/blog/retention-rate",
    "https://posthog.com/blog/b2b-analytics",
    "https://posthog.com/blog/saas-product-analytics",
    "https://posthog.com/blog/feature-flag-benefits",
    "https://posthog.com/blog/session-recording",
    "https://posthog.com/blog/heatmaps-vs-session-recordings",
    "https://posthog.com/tutorials",
    "https://posthog.com/handbook",
    # === HEAP ===
    "https://heap.io/",
    "https://heap.io/product/analytics",
    "https://heap.io/pricing",
    "https://heap.io/blog/",
    "https://heap.io/resources/product-analytics-guide",
    "https://heap.io/blog/product-analytics",
    "https://heap.io/customers",
    "https://developers.heap.io/docs",
    "https://heap.io/blog/heap-vs-mixpanel",
    "https://heap.io/blog/heap-vs-amplitude",
    "https://heap.io/blog/what-is-autocapture",
    # === FULLSTORY ===
    "https://www.fullstory.com/",
    "https://www.fullstory.com/platform/product-analytics/",
    "https://www.fullstory.com/session-replay/",
    "https://www.fullstory.com/pricing/",
    "https://www.fullstory.com/blog/",
    "https://www.fullstory.com/customers/",
    "https://developer.fullstory.com/",
    "https://www.fullstory.com/blog/what-is-session-replay/",
    "https://www.fullstory.com/blog/product-analytics-guide/",
    # === PENDO ===
    "https://www.pendo.io/",
    "https://www.pendo.io/product/analytics/",
    "https://www.pendo.io/product/in-app-guides/",
    "https://www.pendo.io/pricing/",
    "https://www.pendo.io/blog/",
    "https://www.pendo.io/product/feedback/",
    "https://www.pendo.io/resources/",
    # === HOTJAR ===
    "https://www.hotjar.com/",
    "https://www.hotjar.com/product-analytics/",
    "https://www.hotjar.com/heatmaps/",
    "https://www.hotjar.com/session-recordings/",
    "https://www.hotjar.com/pricing/",
    "https://www.hotjar.com/blog/",
    "https://www.hotjar.com/blog/product-analytics/",
    "https://www.hotjar.com/blog/heatmap-tools/",
    "https://www.hotjar.com/survey-tools/",
    # === MATOMO ===
    "https://matomo.org/",
    "https://matomo.org/what-is-matomo/",
    "https://matomo.org/pricing/",
    "https://matomo.org/blog/",
    "https://matomo.org/blog/product-analytics/",
    "https://matomo.org/faq/",
    "https://matomo.org/docs/",
    # === PLAUSIBLE ===
    "https://plausible.io/",
    "https://plausible.io/privacy-focused-web-analytics",
    "https://plausible.io/pricing",
    "https://plausible.io/blog/",
    "https://plausible.io/blog/google-analytics-alternative",
    "https://plausible.io/blog/open-source-analytics",
    "https://plausible.io/vs-google-analytics",
    # === CONTENTSQUARE ===
    "https://contentsquare.com/",
    "https://contentsquare.com/platform/product-analytics/",
    "https://contentsquare.com/pricing/",
    "https://contentsquare.com/blog/",
    # === LOGROCKET ===
    "https://logrocket.com/",
    "https://logrocket.com/features/product-analytics/",
    "https://logrocket.com/pricing/",
    "https://logrocket.com/blog/",
    "https://logrocket.com/blog/product-analytics-tools/",
    "https://logrocket.com/blog/ux-analytics/",
    # === STATSIG ===
    "https://www.statsig.com/",
    "https://www.statsig.com/product-analytics",
    "https://www.statsig.com/pricing",
    "https://www.statsig.com/comparison/best-product-analytics-tools",
    "https://www.statsig.com/comparison/best-open-source-analytics-tools",
    "https://www.statsig.com/blog",
    "https://www.statsig.com/blog/datadog-acquires-eppo",
    "https://docs.statsig.com/statsig-warehouse-native/introduction",
    "https://www.statsig.com/vs/eppo",
    # === SMARTLOOK ===
    "https://www.smartlook.com/",
    "https://www.smartlook.com/product/analytics/",
    "https://www.smartlook.com/pricing/",
    "https://www.smartlook.com/blog/",
    "https://www.smartlook.com/blog/product-analytics/",
    # === MICROSOFT CLARITY ===
    "https://clarity.microsoft.com/",
    "https://learn.microsoft.com/en-us/clarity/",
    "https://clarity.microsoft.com/blog/",
    # === COUNTLY ===
    "https://count.ly/",
    "https://count.ly/product-analytics",
    "https://count.ly/pricing",
    "https://count.ly/blog/",
    # === SNOWPLOW ===
    "https://snowplow.io/",
    "https://snowplow.io/product/",
    "https://snowplow.io/blog/",
    "https://snowplow.io/blog/product-analytics/",
    # === OPENPANEL ===
    "https://openpanel.dev/",
    "https://openpanel.dev/articles/self-hosted-product-analytics",
    "https://openpanel.dev/articles/open-source-web-analytics",
    "https://openpanel.dev/docs/",
    # === METABASE ===
    "https://www.metabase.com/",
    "https://www.metabase.com/product/",
    "https://www.metabase.com/pricing",
    "https://www.metabase.com/blog/",
    # === GLASSBOX ===
    "https://www.glassbox.com/",
    "https://www.glassbox.com/platform/",
    "https://www.glassbox.com/product-analytics/",
    "https://www.glassbox.com/blog/",
    # === USERMAVEN ===
    "https://usermaven.com/",
    "https://usermaven.com/product-analytics",
    "https://usermaven.com/pricing",
    "https://usermaven.com/blog/",
    "https://usermaven.com/blog/product-analytics-tools/",
    "https://usermaven.com/blog/amplitude-alternatives/",
    # === JUNE.SO ===
    "https://june.so/",
    "https://june.so/blog/",
    "https://june.so/blog/product-analytics-b2b",
    "https://june.so/pricing",
    # === MIXPANEL DOCS ГЛУБЖЕ ===
    "https://docs.mixpanel.com/changelogs/2024-02-13-new-funnels-retention",
    "https://docs.mixpanel.com/changelogs/2024-04-03-save-funnel-retention-behaviors",
    "https://docs.mixpanel.com/docs/tracking-methods/sdks/javascript",
    "https://docs.mixpanel.com/docs/tracking-methods/sdks/python",
    # === AMPLITUDE DOCS ===
    "https://www.docs.developers.amplitude.com/analytics/",
    "https://www.docs.developers.amplitude.com/experiment/",
    "https://www.docs.developers.amplitude.com/data/",
    # === СРАВНИТЕЛЬНЫЕ СТАТЬИ — G2 ===
    "https://www.g2.com/categories/product-analytics",
    "https://www.g2.com/compare/amplitude-vs-mixpanel",
    "https://www.g2.com/compare/posthog-vs-amplitude",
    "https://www.g2.com/compare/heap-vs-amplitude",
    "https://www.g2.com/compare/fullstory-vs-hotjar",
    "https://www.g2.com/compare/pendo-vs-amplitude",
    "https://www.g2.com/compare/mixpanel-vs-posthog",
    "https://www.g2.com/compare/hotjar-vs-fullstory",
    "https://www.g2.com/products/amplitude/reviews",
    "https://www.g2.com/products/mixpanel/reviews",
    "https://www.g2.com/products/posthog/reviews",
    # === CAPTERRA ===
    "https://www.capterra.com/product-analytics-software/",
    "https://www.capterra.com/alternatives/162641/amplitude",
    "https://www.capterra.com/alternatives/155603/mixpanel",
    "https://www.capterra.com/product-analytics-software/compare/mixpanel-vs-amplitude/",
    # === ОБЗОРНЫЕ СТАТЬИ ===
    "https://visionlabs.com/blog/best-product-analytics-tools/",
    "https://cleverx.com/blog/product-analytics-tools-12-best-options-compared",
    "https://productschool.com/blog/analytics/product-analytics-tools",
    "https://sequel.sh/blog/best-product-analytics-tools",
    "https://www.news.aakashg.com/p/product-analytics-market",
    "https://geekflare.com/software/best-open-source-web-analytics-tools/",
    "https://daily.dev/blog/10-best-open-source-analytics-platforms-2024",
    "https://www.restack.io/docs/product-analytics-tools",
    "https://www.geteppo.com/blog/best-self-hosted-open-source-analytics-tools",
    "https://www.crazyegg.com/blog/mixpanel-vs-amplitude/",
    "https://www.getorchestra.io/blog/every-bi-tool-ever-ranked-for-2025",
    "https://blog.growthbook.io/the-best-a-b-testing-platforms-of-2025/",
    "https://www.optimizely.com/insights/blog/optimizely-analytics-versus-amplitude-statsig-and-eppo/",
    "https://dev.to/pambrus/6-product-analytics-tool-for-2025-9gp",
    "https://dev.to/ambrus_pethes_a59563db94b/6-product-analytics-tool-for-2025-9gp",
    # === MEDIUM ===
    "https://userpilot.medium.com/10-best-product-management-analytics-tools-for-saas-companies-47d1a7549470",
    "https://medium.com/@hassan.khattak/best-product-analytics-tools-for-startups-in-2024-9995a70144ec",
    "https://medium.com/product-powerhouse/top-10-analytics-tools-every-product-manager-should-know-because-data-gut-feeling-f5d4f29fe861",
    "https://medium.com/@pambrus7/6-product-analytics-tool-for-2025-ab9766510551",
    "https://medium.com/@salahuddinumer08/9-best-product-analytics-tools-for-2024-what-you-shouldnt-miss-394dfa8a3dc5",
    "https://medium.com/@hassan.khattak/best-tools-for-product-analytics-in-2024-b3e600981263",
    "https://medium.com/productschool/6-analytics-tools-for-product-managers-that-you-should-try-48ba32793df7",
    # === USERPILOT ===
    "https://userpilot.com/blog/product-analytics-tools/",
    "https://userpilot.com/blog/amplitude-alternatives/",
    "https://userpilot.com/blog/mixpanel-alternatives/",
    "https://userpilot.com/blog/posthog-review/",
    "https://userpilot.com/blog/heap-alternatives/",
    "https://userpilot.com/blog/product-analytics/",
    "https://userpilot.com/blog/product-analytics-pricing/",
    "https://userpilot.com/blog/user-analytics/",
    "https://userpilot.com/blog/product-analytics-metrics/",
    "https://userpilot.com/blog/product-analytics-examples/",
    "https://userpilot.com/blog/funnel-analysis/",
    "https://userpilot.com/blog/cohort-analysis/",
    "https://userpilot.com/blog/retention-analytics/",
    # === WHATFIX ===
    "https://whatfix.com/blog/product-analytics-tools/",
    "https://whatfix.com/blog/product-analytics/",
    "https://whatfix.com/blog/product-analytics-metrics/",
    "https://whatfix.com/blog/product-analytics-examples/",
    # === APPCUES ===
    "https://www.appcues.com/blog/product-analytics-tools",
    "https://www.appcues.com/blog/amplitude-vs-mixpanel",
    "https://www.appcues.com/blog/product-analytics",
    "https://www.appcues.com/blog/user-onboarding-analytics",
    # === SEGMENT ===
    "https://segment.com/blog/product-analytics-tools/",
    "https://segment.com/blog/choosing-analytics-platform/",
    "https://segment.com/catalog/",
    "https://segment.com/blog/data-driven-product-development/",
    "https://segment.com/blog/what-is-product-analytics/",
    # === ЦЕНООБРАЗОВАНИЕ ===
    "https://posthog.com/pricing",
    "https://heap.io/pricing",
    "https://www.fullstory.com/pricing/",
    "https://www.pendo.io/pricing/",
    "https://www.hotjar.com/pricing/",
    "https://logrocket.com/pricing/",
    "https://www.statsig.com/pricing",
    "https://count.ly/pricing",
    "https://posthog.com/blog/how-to-choose-analytics-tool",
    "https://userpilot.com/blog/product-analytics-pricing/",
    # === ИНТЕГРАЦИИ И ТЕХНИЧЕСКИЕ ДЕТАЛИ ===
    "https://amplitude.com/blog/warehouse-native-analytics",
    "https://posthog.com/blog/what-is-a-data-warehouse",
    "https://www.hightouch.com/blog/product-analytics-warehouse",
    "https://www.rudderstack.com/blog/product-analytics-integration/",
    "https://posthog.com/blog/cdp-vs-analytics",
    "https://launchdarkly.com/blog/launchdarkly-snowflake-warehouse-native-experimentation/",
    # === КЕЙСЫ ===
    "https://posthog.com/customers/supabase",
    "https://posthog.com/customers/vendasta",
    "https://amplitude.com/blog/customer-success-stories",
    "https://mixpanel.com/blog/case-studies/",
    "https://heap.io/customers",
    "https://www.fullstory.com/customers/",
    # === ТРЕНДЫ РЫНКА ===
    "https://www.news.aakashg.com/p/product-analytics-market",
    "https://techcrunch.com/2025/05/05/datadog-acquires-eppo-a-feature-flagging-and-experimentation-platform/",
    "https://www.producttalk.org/product-analytics/",
    "https://www.producthunt.com/topics/analytics",
    # === MOBILE ANALYTICS ===
    "https://www.appsflyer.com/product/analytics/",
    "https://firebase.google.com/products/analytics",
    "https://www.branch.io/product/analytics/",
    "https://www.adjust.com/product/analytics/",
    "https://www.sensor-tower.com/",
    "https://mixpanel.com/mobile-analytics/",
    "https://amplitude.com/mobile-analytics",
    "https://www.appsflyer.com/blog/mobile-analytics/",
    "https://firebase.google.com/docs/analytics",
    # === ЭКСПЕРИМЕНТИРОВАНИЕ И FEATURE FLAGS ===
    "https://launchdarkly.com/",
    "https://launchdarkly.com/product/feature-flags/",
    "https://launchdarkly.com/pricing/",
    "https://launchdarkly.com/blog/",
    "https://launchdarkly.com/blog/feature-flag-best-practices/",
    "https://www.optimizely.com/",
    "https://www.optimizely.com/products/experiment/web/",
    "https://www.optimizely.com/pricing/",
    "https://split.io/",
    "https://split.io/blog/",
    "https://split.io/blog/feature-flags-vs-feature-toggles/",
    "https://www.geteppo.com/",
    "https://www.geteppo.com/blog/",
    "https://growthbook.io/",
    "https://growthbook.io/feature-flags",
    "https://growthbook.io/blog/",
    "https://growthbook.io/blog/ab-testing-tools/",
    # === OPEN SOURCE SELF-HOSTED ===
    "https://posthog.com/blog/best-open-source-analytics-tools",
    "https://openpanel.dev/articles/self-hosted-product-analytics",
    "https://openpanel.dev/articles/open-source-web-analytics",
    "https://geekflare.com/software/best-open-source-web-analytics-tools/",
    "https://daily.dev/blog/10-best-open-source-analytics-platforms-2024",
    "https://www.geteppo.com/blog/best-self-hosted-open-source-analytics-tools",
    "https://www.restack.io/docs/product-analytics-tools",
    "https://www.restack.io/docs/posthog-knowledge",
    "https://github.com/PostHog/posthog",
    "https://github.com/plausible/analytics",
    "https://github.com/matomo-org/matomo",
    "https://github.com/umami-software/umami",
    "https://github.com/growthbook/growthbook",
    "https://github.com/microsoft/clarity",
    "https://github.com/snowplow/snowplow",
    # === АЛЬТЕРНАТИВНЫЕ ОБЗОРЫ ===
    "https://alternativeto.net/software/amplitude/about/",
    "https://alternativeto.net/software/mixpanel/about/",
    "https://alternativeto.net/software/posthog/about/",
    "https://alternativeto.net/software/heap-analytics/about/",
    "https://stackshare.io/stackups/amplitude-vs-mixpanel",
    "https://stackshare.io/stackups/posthog-vs-amplitude",
    "https://stackshare.io/stackups/heap-vs-mixpanel",
    "https://stackshare.io/stackups/posthog-vs-mixpanel",
    "https://stackshare.io/stackups/amplitude-vs-heap",
    "https://slashdot.org/software/comparison/Amplitude-vs-Mixpanel/",
    "https://www.trustradius.com/product-analytics",
    "https://www.trustradius.com/compare-products/amplitude-vs-mixpanel",
    "https://www.peerspot.com/categories/product-analytics",
    "https://www.peerspot.com/products/comparisons/amplitude_vs_mixpanel",
    # === БЛОГИ И РЕСУРСЫ ===
    "https://www.intercom.com/blog/product-analytics/",
    "https://www.productboard.com/blog/product-analytics-tools/",
    "https://www.reforge.com/blog/product-analytics",
    "https://lenny.substack.com/p/product-analytics-tools",
    "https://www.mindtheproduct.com/product-analytics/",
    "https://www.svpg.com/product-analytics/",
    "https://baremetrics.com/blog/product-analytics",
    "https://www.indicative.com/resource/product-analytics-tools/",
    "https://www.softwareadvice.com/bi/product-analytics-comparison/",
    "https://www.getapp.com/business-intelligence-analytics-software/product-analytics/",
    "https://productschool.com/blog/analytics/product-analytics-tools",
    # === AI В АНАЛИТИКЕ ===
    "https://amplitude.com/blog/ai-analytics",
    "https://posthog.com/blog/llm-analytics",
    "https://mixpanel.com/blog/ai-product-analytics/",
    "https://www.hotjar.com/blog/ai-product-analytics/",
    "https://logrocket.com/blog/ai-user-experience/",
    # === WAREHOUSE-NATIVE ANALYTICS ===
    "https://docs.statsig.com/statsig-warehouse-native/introduction",
    "https://www.hightouch.com/blog/product-analytics-warehouse",
    "https://amplitude.com/blog/warehouse-native-analytics",
    "https://posthog.com/blog/what-is-a-data-warehouse",
    "https://www.getorchestra.io/blog/every-bi-tool-ever-ranked-for-2025",
    # === GOOGLE ANALYTICS / ADOBE ===
    "https://analytics.google.com/analytics/web/",
    "https://support.google.com/analytics/answer/10089681",
    "https://business.adobe.com/products/analytics/adobe-analytics.html",
    "https://posthog.com/blog/google-analytics-alternatives",
    # === SEGMENT / CDP ===
    "https://segment.com/",
    "https://segment.com/product/",
    "https://segment.com/pricing/",
    "https://www.rudderstack.com/",
    "https://www.rudderstack.com/blog/",
    "https://www.rudderstack.com/blog/product-analytics-integration/",
    # === A/B TESTING ===
    "https://blog.growthbook.io/the-best-a-b-testing-platforms-of-2025/",
    "https://www.optimizely.com/insights/blog/optimizely-analytics-versus-amplitude-statsig-and-eppo/",
    "https://vwo.com/",
    "https://vwo.com/ab-testing/",
    "https://vwo.com/pricing/",
    "https://www.convert.com/",
    "https://www.convert.com/blog/ab-testing/",
    # === ДОПОЛНИТЕЛЬНЫЕ ИНСТРУМЕНТЫ ===
    "https://www.crazyegg.com/",
    "https://www.crazyegg.com/blog/mixpanel-vs-amplitude/",
    "https://www.crazyegg.com/blog/product-analytics/",
    "https://mouseflow.com/",
    "https://mouseflow.com/blog/",
    "https://www.luckyorange.com/",
    "https://heap.io/blog/heap-vs-mixpanel",
    "https://heap.io/blog/heap-vs-amplitude",
    "https://www.userlytics.com/",
    "https://www.uxcam.com/",
    "https://www.uxcam.com/blog/mobile-analytics/",
    # === НОВОСТНЫЕ СТАТЬИ ===
    "https://techcrunch.com/2025/05/05/datadog-acquires-eppo-a-feature-flagging-and-experimentation-platform/",
    "https://www.statsig.com/blog/datadog-acquires-eppo",
    # === ДОКУМЕНТАЦИЯ / GUIDES ===
    "https://posthog.com/tutorials",
    "https://posthog.com/docs/product-analytics",
    "https://posthog.com/docs/session-replay",
    "https://posthog.com/docs/feature-flags",
    "https://posthog.com/docs/experiments",
    "https://docs.mixpanel.com/docs/tracking-methods/sdks/javascript",
    "https://docs.mixpanel.com/docs/tracking-methods/sdks/python",
    "https://www.docs.developers.amplitude.com/analytics/",
    "https://developer.mixpanel.com/docs",
    "https://developers.heap.io/docs",
    "https://developer.fullstory.com/",
    "https://launchdarkly.com/docs/",
    "https://docs.growthbook.io/",
    "https://docs.statsig.com/",
    # === RETENTION И CHURN ===
    "https://amplitude.com/blog/retention-analysis",
    "https://mixpanel.com/blog/retention-rate/",
    "https://posthog.com/blog/retention-rate",
    "https://userpilot.com/blog/retention-analytics/",
    "https://chartmogul.com/blog/customer-retention/",
    "https://baremetrics.com/blog/churn",
    # === SAAS METRICS ===
    "https://www.profitwell.com/recur/all/saas-metrics",
    "https://chartmogul.com/",
    "https://chartmogul.com/blog/",
    "https://baremetrics.com/",
    "https://baremetrics.com/blog/",
    "https://www.klipfolio.com/resources/kpi-examples/saas",
    # === PRODUCTHUNT / COMMUNITY ===
    "https://www.producthunt.com/topics/analytics",
    "https://www.producthunt.com/products/posthog",
    "https://www.producthunt.com/products/amplitude",
    "https://www.producthunt.com/products/mixpanel",
    # === ДОПОЛНИТЕЛЬНЫЕ БЛОГИ ===
    "https://www.reforge.com/blog/product-analytics",
    "https://www.productboard.com/blog/product-analytics-tools/",
    "https://www.mindtheproduct.com/product-analytics/",
    "https://lenny.substack.com/p/product-analytics-tools",
    "https://www.svpg.com/product-analytics/",
    "https://www.intercom.com/blog/product-analytics/",
    "https://www.appcues.com/blog/user-onboarding-analytics",
    "https://www.useronboard.com/",
    # === LIGHTDASH / HOLISTICS / BI ===
    "https://www.lightdash.com/",
    "https://www.lightdash.com/blog/",
    "https://www.holistics.io/",
    "https://www.holistics.io/blog/",
    "https://www.holistics.io/blog/product-analytics/",
    "https://cube.dev/",
    "https://cube.dev/blog/",
    "https://cube.dev/blog/product-analytics-with-cube/",
]

# Дедупликация
urls = list(dict.fromkeys(urls))
print(f"Всего уникальных URL: {len(urls)}")

payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "scout_index",
        "arguments": {
            "topic": "product analytics tools 2024 2025",
            "source_type": "urls",
            "source_urls": urls,
            "cache_ttl_hours": 0
        }
    }
}

with open("/tmp/sc013_payload.json", "w") as f:
    json.dump(payload, f)

print("Запускаю индексацию (~5-10 минут)...")
result = subprocess.run(
    ["curl", "-s", "-X", "POST", "http://localhost:8020/mcp",
     "-H", "Content-Type: application/json",
     "-d", "@/tmp/sc013_payload.json"],
    capture_output=True, text=True, timeout=900
)
try:
    out = json.loads(result.stdout)
    r = out.get("result", {})
    print(f"status:          {r.get('status')}")
    print(f"session_id:      {r.get('session_id')}")
    print(f"documents_count: {r.get('documents_count')}")
    print(f"chunks_count:    {r.get('chunks_count')}")
    print(f"failed_count:    {r.get('failed_count')}")
    print(f"message:         {r.get('message')}")
except Exception as e:
    print("Raw output:", result.stdout[:3000])
    print("Error:", e)
SCRIPT
```

---

## Шаг 2 — Проверить PostgreSQL

```bash
docker exec scout-postgres psql -U scout_user -d scout_db -c "
SELECT id, topic, status, documents_count, chunks_count,
       ROUND(EXTRACT(EPOCH FROM (completed_at - created_at))) as seconds
FROM research_sessions ORDER BY created_at DESC LIMIT 3;"
```

---

## Шаг 3 — Поисковые запросы

```bash
SESSION_ID="<session_id из шага 1>"

for QUERY in \
  "event tracking funnel analysis" \
  "pricing plans enterprise" \
  "integrations API data warehouse" \
  "self-hosted open source deployment" \
  "mobile analytics SDK" \
  "AI machine learning analytics" \
  "A/B testing feature flags experimentation"; do
  echo "=== $QUERY ==="
  curl -s -X POST http://localhost:8020/mcp \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",
\"params\":{\"name\":\"scout_search\",\"arguments\":{
\"session_id\":\"$SESSION_ID\",\"query\":\"$QUERY\",\"top_k\":5}}}" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
rs=d.get('result',{}).get('results',[])
print(f'  results: {len(rs)}')
for r in rs: print(f'  {r[\"similarity\"]:.3f} | {r[\"source_title\"][:60]}')
"
done
```

---

## Шаг 4 — Сравнительная таблица

| Метрика | SC-008 DDG (8 docs) | SC-012 URL (109 docs) | SC-013 URL (363 uniq) |
|---------|--------------------|-----------------------|-----------------|
| documents_count | 8 | 109 | 204 |
| chunks_count | 57 | 562 | 1031 |
| failed_count | 2 | 71 | 150 |
| время (сек) | 21 | 49 | 73 |
| Q1 similarity | 0.67–0.71 | 0.688–0.750 | 0.705–0.750 |
| Q2 similarity | 0.63–0.72 | 0.701–0.719 | 0.705–0.725 |
| Q3 similarity | 0.61 (1 res) | 0.682–0.746 | 0.684–0.746 |
| Q4 self-hosted | н/д | 0.665–0.734 | 0.665–0.734 |
| Q5 mobile SDK | н/д | 0.722–0.783 | 0.722–0.783 |
| Q6 AI/ML | н/д | н/д | 0.687–0.700 |
| Q7 A/B testing | н/д | н/д | 0.688–0.746 |
| доменов в топ-10 | ~4 | >8 | >10 |

---

## Критерии готовности

- `scout_index` → статус `ready`
- `documents_count` > 200
- Q6 (AI/ML analytics) и Q7 (A/B testing) дали результаты
- Таблица заполнена

---

*Дата создания: 2026-03-16*

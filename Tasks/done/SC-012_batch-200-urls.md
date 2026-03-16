# SC-012 — Батч 200 URL: большой прогон в URL-режиме

## Цель

Первый прогон в URL-режиме на реальном масштабе: 200 URL → индексация → поиск.

**Блокер**: SC-011 должна быть выполнена (URL-режим + параллельный фетч).

---

## Шаг 1 — Запустить индексацию

URL уже встроены в скрипт ниже. Выполнить через homelab MCP (`run_shell_command`):

```bash
python3 << 'SCRIPT'
import json, subprocess

urls = [
    "https://amplitude.com/",
    "https://amplitude.com/product-analytics",
    "https://amplitude.com/session-replay",
    "https://amplitude.com/feature-experimentation",
    "https://amplitude.com/pricing",
    "https://amplitude.com/blog/product-analytics",
    "https://amplitude.com/blog/amplitude-vs-mixpanel",
    "https://amplitude.com/blog/product-analytics-tools",
    "https://mixpanel.com/",
    "https://mixpanel.com/product-analytics/",
    "https://mixpanel.com/session-replay/",
    "https://mixpanel.com/pricing/",
    "https://mixpanel.com/blog/",
    "https://mixpanel.com/compare/amplitude/",
    "https://mixpanel.com/blog/mixpanel-vs-amplitude/",
    "https://mixpanel.com/blog/product-analytics-tools/",
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
    "https://heap.io/",
    "https://heap.io/product/analytics",
    "https://heap.io/pricing",
    "https://heap.io/blog/",
    "https://heap.io/resources/product-analytics-guide",
    "https://heap.io/blog/product-analytics",
    "https://heap.io/customers",
    "https://developers.heap.io/docs",
    "https://www.fullstory.com/",
    "https://www.fullstory.com/platform/product-analytics/",
    "https://www.fullstory.com/session-replay/",
    "https://www.fullstory.com/pricing/",
    "https://www.fullstory.com/blog/",
    "https://www.fullstory.com/customers/",
    "https://developer.fullstory.com/",
    "https://www.pendo.io/",
    "https://www.pendo.io/product/analytics/",
    "https://www.pendo.io/product/in-app-guides/",
    "https://www.pendo.io/pricing/",
    "https://www.pendo.io/blog/",
    "https://www.hotjar.com/",
    "https://www.hotjar.com/product-analytics/",
    "https://www.hotjar.com/heatmaps/",
    "https://www.hotjar.com/session-recordings/",
    "https://www.hotjar.com/pricing/",
    "https://www.hotjar.com/blog/",
    "https://matomo.org/",
    "https://matomo.org/what-is-matomo/",
    "https://matomo.org/pricing/",
    "https://matomo.org/blog/",
    "https://matomo.org/blog/product-analytics/",
    "https://plausible.io/",
    "https://plausible.io/privacy-focused-web-analytics",
    "https://plausible.io/pricing",
    "https://plausible.io/blog/",
    "https://contentsquare.com/",
    "https://contentsquare.com/platform/product-analytics/",
    "https://contentsquare.com/pricing/",
    "https://www.glassbox.com/",
    "https://www.glassbox.com/platform/",
    "https://www.glassbox.com/product-analytics/",
    "https://logrocket.com/",
    "https://logrocket.com/features/product-analytics/",
    "https://logrocket.com/pricing/",
    "https://logrocket.com/blog/",
    "https://www.statsig.com/",
    "https://www.statsig.com/product-analytics",
    "https://www.statsig.com/pricing",
    "https://www.statsig.com/comparison/best-product-analytics-tools",
    "https://www.statsig.com/comparison/best-open-source-analytics-tools",
    "https://www.smartlook.com/",
    "https://www.smartlook.com/product/analytics/",
    "https://www.smartlook.com/pricing/",
    "https://clarity.microsoft.com/",
    "https://learn.microsoft.com/en-us/clarity/",
    "https://count.ly/",
    "https://count.ly/product-analytics",
    "https://count.ly/pricing",
    "https://snowplow.io/",
    "https://snowplow.io/product/",
    "https://snowplow.io/blog/",
    "https://openpanel.dev/",
    "https://openpanel.dev/articles/self-hosted-product-analytics",
    "https://openpanel.dev/articles/open-source-web-analytics",
    "https://www.metabase.com/",
    "https://www.metabase.com/product/",
    "https://www.metabase.com/pricing",
    "https://visionlabs.com/blog/best-product-analytics-tools/",
    "https://cleverx.com/blog/product-analytics-tools-12-best-options-compared",
    "https://productschool.com/blog/analytics/product-analytics-tools",
    "https://sequel.sh/blog/best-product-analytics-tools",
    "https://www.news.aakashg.com/p/product-analytics-market",
    "https://geekflare.com/software/best-open-source-web-analytics-tools/",
    "https://daily.dev/blog/10-best-open-source-analytics-platforms-2024",
    "https://www.restack.io/docs/product-analytics-tools",
    "https://www.geteppo.com/blog/best-self-hosted-open-source-analytics-tools",
    "https://userpilot.com/blog/product-analytics-tools/",
    "https://userpilot.com/blog/amplitude-alternatives/",
    "https://userpilot.com/blog/mixpanel-alternatives/",
    "https://userpilot.com/blog/posthog-review/",
    "https://userpilot.com/blog/heap-alternatives/",
    "https://userpilot.com/blog/product-analytics/",
    "https://userpilot.com/blog/product-analytics-pricing/",
    "https://whatfix.com/blog/product-analytics-tools/",
    "https://whatfix.com/blog/product-analytics/",
    "https://www.appcues.com/blog/product-analytics-tools",
    "https://www.appcues.com/blog/amplitude-vs-mixpanel",
    "https://segment.com/blog/product-analytics-tools/",
    "https://segment.com/blog/choosing-analytics-platform/",
    "https://segment.com/catalog/",
    "https://baremetrics.com/blog/product-analytics",
    "https://www.amplitude.com/pricing",
    "https://amplitude.com/blog/product-analytics-pricing",
    "https://amplitude.com/customers",
    "https://amplitude.com/blog/customer-success-stories",
    "https://amplitude.com/blog/warehouse-native-analytics",
    "https://www.docs.developers.amplitude.com/",
    "https://mixpanel.com/pricing/",
    "https://mixpanel.com/customers/",
    "https://mixpanel.com/blog/case-studies/",
    "https://developer.mixpanel.com/docs",
    "https://posthog.com/pricing",
    "https://heap.io/pricing",
    "https://www.fullstory.com/pricing/",
    "https://www.pendo.io/pricing/",
    "https://www.hotjar.com/pricing/",
    "https://logrocket.com/pricing/",
    "https://www.statsig.com/pricing",
    "https://count.ly/pricing",
    "https://www.hightouch.com/blog/product-analytics-warehouse",
    "https://www.rudderstack.com/blog/product-analytics-integration/",
    "https://www.producttalk.org/product-analytics/",
    "https://www.productboard.com/blog/product-analytics-tools/",
    "https://www.intercom.com/blog/product-analytics/",
    "https://www.reforge.com/blog/product-analytics",
    "https://lenny.substack.com/p/product-analytics-tools",
    "https://www.mindtheproduct.com/product-analytics/",
    "https://www.appsflyer.com/product/analytics/",
    "https://firebase.google.com/products/analytics",
    "https://www.branch.io/product/analytics/",
    "https://www.adjust.com/product/analytics/",
    "https://mixpanel.com/mobile-analytics/",
    "https://amplitude.com/mobile-analytics",
    "https://launchdarkly.com/",
    "https://launchdarkly.com/product/feature-flags/",
    "https://launchdarkly.com/pricing/",
    "https://www.optimizely.com/",
    "https://www.optimizely.com/products/experiment/web/",
    "https://www.optimizely.com/pricing/",
    "https://split.io/",
    "https://www.geteppo.com/",
    "https://growthbook.io/",
    "https://growthbook.io/feature-flags",
    "https://alternativeto.net/software/amplitude/about/",
    "https://alternativeto.net/software/mixpanel/about/",
    "https://stackshare.io/stackups/amplitude-vs-mixpanel",
    "https://stackshare.io/stackups/posthog-vs-amplitude",
    "https://stackshare.io/stackups/heap-vs-mixpanel",
    "https://www.trustradius.com/product-analytics",
    "https://www.trustradius.com/compare-products/amplitude-vs-mixpanel",
    "https://www.peerspot.com/categories/product-analytics",
    "https://www.peerspot.com/products/comparisons/amplitude_vs_mixpanel",
    "https://github.com/PostHog/posthog",
    "https://github.com/plausible/analytics",
    "https://github.com/matomo-org/matomo",
    "https://github.com/umami-software/umami",
    "https://github.com/growthbook/growthbook",
    "https://www.sensor-tower.com/",
    "https://www.indicative.com/resource/product-analytics-tools/",
    "https://www.softwareadvice.com/bi/product-analytics-comparison/",
    "https://www.getapp.com/business-intelligence-analytics-software/product-analytics/",
    "https://slashdot.org/software/comparison/Amplitude-vs-Mixpanel/",
    "https://www.svpg.com/product-analytics/",
]

print(f"Всего URL: {len(urls)}")

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

with open("/tmp/sc012_payload.json", "w") as f:
    json.dump(payload, f)

print("Запускаю индексацию (~3-7 минут)...")
result = subprocess.run(
    ["curl", "-s", "-X", "POST", "http://localhost:8020/mcp",
     "-H", "Content-Type: application/json",
     "-d", "@/tmp/sc012_payload.json"],
    capture_output=True, text=True, timeout=600
)
import sys
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

Подставить `session_id` из шага 1:

```bash
SESSION_ID="<вставить session_id>"

for QUERY in \
  "event tracking funnel analysis" \
  "pricing plans enterprise" \
  "integrations API data warehouse" \
  "self-hosted open source deployment" \
  "mobile analytics SDK"; do
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

## Шаг 4 — Заполнить таблицу сравнения

| Метрика | SC-008 DDG quick | SC-012 200 URL |
|---------|-----------------|----------------|
| documents_count | 8 | 109 |
| chunks_count | 57 | 562 |
| failed_count | 2 | 71 |
| время (сек) | 21 | 49 |
| Q1 similarity | 0.67–0.71 | 0.688–0.750 |
| Q2 similarity | 0.63–0.72 | 0.701–0.719 |
| Q3 similarity | 0.61 (1 res) | 0.682–0.746 (5 res) ✅ |
| Q4 результатов | н/д | 5 (0.665–0.734) ✅ |
| Q5 результатов | н/д | 5 (0.722–0.783) ✅ |
| доменов в топ-10 | ~4 | >8 (разнообразнее) |

---

## Критерии готовности

- `scout_index` → статус `ready`
- `documents_count` > 100
- Q3 дал больше 1 результата (в SC-008 был 1 с 0.61)
- Q4 и Q5 дали хотя бы 1 результат
- Таблица заполнена

---

*Дата создания: 2026-03-16*

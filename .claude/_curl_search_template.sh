SESSION_ID="<session_id из шага 1>"

# ВАЖНО: FastMCP требует заголовок Accept: application/json, text/event-stream
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
    -H "Accept: application/json, text/event-stream" \
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
# SC-014 — Батч ~1000 URL: AI developer tools & copilots 2024-2025

## Цель

Первый прогон на новой теме — AI developer tools & copilots.
Проверить насколько хорошо Scout работает на смежной, но отличной от product analytics теме.
Сравнить quality coverage с SC-013 (product analytics, 204 docs).

---

## Шаг 1 — Запустить индексацию

```bash
python3 << 'SCRIPT'
import json, subprocess, sys

# ── MCP SESSION INIT ──────────────────────────────────────────────────────────
def mcp_call(payload, session_id=None):
    headers = [
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json, text/event-stream",
    ]
    if session_id:
        headers += ["-H", f"Mcp-Session-Id: {session_id}"]
    cmd = ["curl", "-si", "-X", "POST", "http://localhost:8020/mcp"] + headers + ["-d", json.dumps(payload)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    # Извлечь session id из заголовков
    sid = None
    for line in result.stdout.split("\n"):
        if line.lower().startswith("mcp-session-id:"):
            sid = line.split(":", 1)[1].strip()
    # Найти JSON в теле (после пустой строки)
    body = result.stdout.split("\r\n\r\n", 1)[-1].strip()
    # SSE: может прийти как "data: {...}"
    if body.startswith("data:"):
        body = body[5:].strip()
    try:
        return json.loads(body), sid
    except:
        print("RAW:", result.stdout[:500])
        return {}, sid

# 1. initialize
init_payload = {
    "jsonrpc": "2.0", "id": 0,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "scout-batch", "version": "1.0"}
    }
}
_, session_id = mcp_call(init_payload)
print(f"Session-Id: {session_id}")

# ── URL LIST ──────────────────────────────────────────────────────────────────
urls = [
    # === GITHUB COPILOT ===
    "https://github.com/features/copilot",
    "https://github.blog/ai-and-ml/github-copilot/",
    "https://github.blog/news/github-copilot-free-is-now-available/",
    "https://docs.github.com/en/copilot",
    "https://docs.github.com/en/copilot/about-github-copilot/what-is-github-copilot",
    "https://docs.github.com/en/copilot/getting-started-with-github-copilot",
    "https://docs.github.com/en/copilot/github-copilot-enterprise/overview",
    "https://github.blog/engineering/how-github-copilot-uses-ai/",
    "https://resources.github.com/copilot-for-business/",
    "https://github.com/pricing",
    "https://github.blog/ai-and-ml/github-copilot/github-copilot-now-has-a-better-free-tier/",
    "https://github.blog/2024-02-27-github-copilot-enterprise-is-now-generally-available/",
    "https://github.blog/ai-and-ml/github-copilot/research-quantifying-github-copilots-impact-in-the-enterprise/",
    "https://github.blog/2023-06-20-how-to-write-better-prompts-for-github-copilot/",
    "https://docs.github.com/en/copilot/using-github-copilot/getting-code-suggestions-in-your-ide-with-github-copilot",
    "https://docs.github.com/en/copilot/managing-copilot/managing-github-copilot-in-your-organization",
    "https://github.blog/ai-and-ml/github-copilot/github-copilot-chat-ga/",
    "https://docs.github.com/en/copilot/github-copilot-chat",
    "https://github.blog/ai-and-ml/github-copilot/copilot-agent-mode/",
    "https://github.blog/developer-skills/github/github-copilot-vs-code/",
    # === CURSOR ===
    "https://www.cursor.com/",
    "https://www.cursor.com/pricing",
    "https://www.cursor.com/features",
    "https://docs.cursor.com/",
    "https://docs.cursor.com/get-started/introduction",
    "https://docs.cursor.com/context/codebase-indexing",
    "https://docs.cursor.com/agent/overview",
    "https://docs.cursor.com/privacy/privacy",
    "https://www.cursor.com/blog",
    "https://www.cursor.com/blog/cursor-tab",
    "https://www.cursor.com/blog/composer",
    "https://changelog.cursor.com/",
    "https://forum.cursor.com/",
    # === WINDSURF / CODEIUM ===
    "https://windsurf.com/",
    "https://windsurf.com/pricing",
    "https://windsurf.com/blog",
    "https://docs.windsurf.com/",
    "https://docs.windsurf.com/windsurf/getting-started",
    "https://docs.windsurf.com/windsurf/models",
    "https://codeium.com/",
    "https://codeium.com/pricing",
    "https://codeium.com/blog",
    "https://codeium.com/compare/codeium-vs-github-copilot",
    "https://codeium.com/compare/codeium-vs-tabnine",
    "https://codeium.com/blog/code-autocomplete",
    "https://codeium.com/extensions",
    # === CLAUDE CODE ===
    "https://www.anthropic.com/claude-code",
    "https://docs.anthropic.com/en/docs/claude-code/overview",
    "https://docs.anthropic.com/en/docs/claude-code/getting-started",
    "https://docs.anthropic.com/en/docs/claude-code/tutorials",
    "https://docs.anthropic.com/en/docs/claude-code/memory",
    "https://docs.anthropic.com/en/docs/claude-code/settings",
    "https://www.anthropic.com/news/claude-code-beta",
    "https://www.anthropic.com/research/claude-code",
    # === TABNINE ===
    "https://www.tabnine.com/",
    "https://www.tabnine.com/pricing",
    "https://www.tabnine.com/blog/",
    "https://www.tabnine.com/blog/tabnine-versus-github-copilot/",
    "https://www.tabnine.com/blog/tabnine-vs-cursor/",
    "https://www.tabnine.com/features/",
    "https://www.tabnine.com/enterprise/",
    "https://docs.tabnine.com/",
    "https://www.tabnine.com/blog/ai-code-review/",
    "https://www.tabnine.com/blog/on-premise-ai/",
    # === AMAZON Q / CODEWHISPERER ===
    "https://aws.amazon.com/q/developer/",
    "https://aws.amazon.com/codewhisperer/",
    "https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/what-is.html",
    "https://aws.amazon.com/blogs/devops/introducing-amazon-q-developer/",
    "https://aws.amazon.com/q/developer/pricing/",
    "https://aws.amazon.com/blogs/machine-learning/category/artificial-intelligence/generative-ai/",
    "https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/security-scans.html",
    # === CONTINUE.DEV ===
    "https://continue.dev/",
    "https://continue.dev/docs",
    "https://continue.dev/docs/intro",
    "https://continue.dev/docs/setup/overview",
    "https://github.com/continuedev/continue",
    "https://continue.dev/blog",
    # === CLINE ===
    "https://cline.bot/",
    "https://github.com/cline/cline",
    "https://docs.cline.bot/",
    "https://docs.cline.bot/getting-started/for-new-coders",
    # === AIDER ===
    "https://aider.chat/",
    "https://aider.chat/docs/",
    "https://aider.chat/docs/install.html",
    "https://aider.chat/docs/llms.html",
    "https://aider.chat/blog/",
    "https://aider.chat/2024/06/02/main-swe-bench.html",
    "https://github.com/paul-gauthier/aider",
    # === DEVIN / COGNITION ===
    "https://cognition.ai/",
    "https://cognition.ai/blog",
    "https://cognition.ai/devin",
    "https://cognition.ai/pricing",
    "https://cognition.ai/blog/introducing-devin",
    "https://cognition.ai/blog/swe-bench",
    # === REPLIT ===
    "https://replit.com/",
    "https://replit.com/ai",
    "https://replit.com/pricing",
    "https://blog.replit.com/",
    "https://blog.replit.com/ai-features",
    "https://docs.replit.com/",
    "https://replit.com/blog/replit-agent",
    # === V0 BY VERCEL ===
    "https://v0.dev/",
    "https://vercel.com/blog/v0",
    "https://vercel.com/blog/introducing-v0-generative-ui",
    "https://vercel.com/docs/v0",
    # === LOVABLE ===
    "https://lovable.dev/",
    "https://lovable.dev/blog",
    "https://lovable.dev/pricing",
    "https://docs.lovable.dev/",
    # === BOLT.NEW ===
    "https://bolt.new/",
    "https://stackblitz.com/ai",
    # === JETBRAINS AI ===
    "https://www.jetbrains.com/ai/",
    "https://www.jetbrains.com/ai/pricing/",
    "https://www.jetbrains.com/help/idea/ai-assistant.html",
    "https://blog.jetbrains.com/ai/",
    "https://blog.jetbrains.com/blog/2024/04/04/jetbrains-ai-assistant-what-s-new/",
    # === SOURCEGRAPH CODY / AMP ===
    "https://sourcegraph.com/cody",
    "https://sourcegraph.com/blog/cody-is-generally-available",
    "https://sourcegraph.com/pricing",
    "https://about.sourcegraph.com/blog/",
    "https://sourcegraph.com/amp",
    "https://docs.sourcegraph.com/",
    # === SUPERMAVEN ===
    "https://supermaven.com/",
    "https://supermaven.com/blog",
    "https://supermaven.com/pricing",
    # === ZED AI ===
    "https://zed.dev/",
    "https://zed.dev/blog",
    "https://zed.dev/ai",
    "https://zed.dev/pricing",
    "https://zed.dev/docs/",
    # === GOOGLE GEMINI CODE ASSIST / ANTIGRAVITY ===
    "https://cloud.google.com/gemini/docs/codeassist/overview",
    "https://cloud.google.com/gemini/docs/codeassist/use-in-ide",
    "https://cloud.google.com/gemini/pricing",
    "https://developers.google.com/gemini-code-assist",
    "https://blog.google/technology/developers/gemini-code-assist/",
    "https://cloud.google.com/blog/products/application-development/introducing-gemini-code-assist",
    # === OPENAI CODEX ===
    "https://openai.com/blog/openai-codex",
    "https://platform.openai.com/docs/guides/code",
    "https://openai.com/research/evaluating-large-language-models-trained-on-code",
    # === MICROSOFT / VISUAL STUDIO ===
    "https://visualstudio.microsoft.com/github-copilot/",
    "https://code.visualstudio.com/docs/copilot/overview",
    "https://code.visualstudio.com/docs/copilot/getting-started",
    "https://code.visualstudio.com/blogs/2024/11/13/copilot-free",
    # === AUGMENT CODE ===
    "https://www.augmentcode.com/",
    "https://www.augmentcode.com/blog",
    "https://www.augmentcode.com/pricing",
    "https://www.augmentcode.com/blog/introducing-augment-agent",
    # === KIRO (AMAZON) ===
    "https://kiro.dev/",
    "https://kiro.dev/docs/",
    "https://kiro.dev/blog/",
    "https://aws.amazon.com/blogs/devops/introducing-amazon-kiro/",
    # === ИНСТРУМЕНТЫ ТЕСТИРОВАНИЯ ===
    "https://www.qodo.ai/",
    "https://www.qodo.ai/blog/",
    "https://www.qodo.ai/blog/best-coding-ai-copilots/",
    "https://www.qodo.ai/products/qodo-gen/",
    "https://coveragent.qodo.ai/",
    # === ОБЗОРНЫЕ СТАТЬИ ===
    "https://getdx.com/blog/compare-copilot-cursor-tabnine/",
    "https://getdx.com/blog/ai-coding-assistant-pricing/",
    "https://localaimaster.com/tools/best-ai-coding-tools",
    "https://www.saaspricepulse.com/blog/ai-coding-assistant-pricing-guide-2025",
    "https://www.digitalapplied.com/blog/ai-coding-tools-comparison-december-2025",
    "https://prismic.io/blog/ai-code-generators",
    "https://toolpod.dev/blog/comparing-ai-coding-tools-2024",
    "https://lushbinary.com/blog/ai-coding-agents-comparison-cursor-windsurf-claude-copilot-kiro-2026/",
    "https://awesomeagents.ai/pricing/ai-coding-tools-pricing/",
    "https://vladimirsiedykh.com/blog/ai-development-tools-pricing-analysis-claude-copilot-cursor-comparison-2025",
    "https://www.thepromptbuddy.com/prompts/cursor-vs-github-copilot-vs-windsurf-vs-claude-code-which-ai-coding-assistant-is-worth-it-in",
    "https://www.thepromptbuddy.com/prompts/claude-code-vs-cursor-vs-github-copilot-vs-amazon-q-which-ai-coding-tool-wins-in-2026",
    "https://www.sentisight.ai/copilot-vs-codeium-vs-cursor-vs-gemini-coding/",
    "https://dev.to/stevengonsalvez/2025s-best-ai-coding-tools-real-cost-geeky-value-honest-comparison-4d63",
    "https://dev.to/pambrus/ai-developer-tools-2025-comparison",
    # === MEDIUM ===
    "https://medium.com/@pensora.iq.team/github-copilot-vs-tabnine-vs-codeium-2025-the-ultimate-showdown-of-ai-coding-assistants-e88c925ed5df",
    "https://medium.com/@shadetreeit/cursor-vs-windsurf-vs-vs-code-with-copilot-where-to-put-your-money-e381f9ae281e",
    "https://medium.com/product-powerhouse/top-10-analytics-tools-every-product-manager-should-know-because-data-gut-feeling-f5d4f29fe861",
    "https://betterprogramming.pub/github-copilot-vs-cursor-vs-codeium-2024-43f7e0a71dd8",
    "https://towardsdatascience.com/ai-code-assistants-comparison-2024",
    # === DEV.TO ===
    "https://dev.to/stevengonsalvez/2025s-best-ai-coding-tools-real-cost-geeky-value-honest-comparison-4d63",
    "https://dev.to/logrocket/comparing-ai-coding-assistants-2024",
    "https://dev.to/github/whats-new-in-github-copilot-2024",
    # === ЦЕНООБРАЗОВАНИЕ ===
    "https://github.com/pricing",
    "https://www.cursor.com/pricing",
    "https://windsurf.com/pricing",
    "https://codeium.com/pricing",
    "https://www.tabnine.com/pricing",
    "https://aws.amazon.com/q/developer/pricing/",
    "https://www.jetbrains.com/ai/pricing/",
    "https://replit.com/pricing",
    "https://lovable.dev/pricing",
    "https://cognition.ai/pricing",
    "https://supermaven.com/pricing",
    "https://zed.dev/pricing",
    # === ENTERPRISE И БЕЗОПАСНОСТЬ ===
    "https://docs.github.com/en/copilot/managing-copilot/managing-github-copilot-in-your-organization/reviewing-github-copilot-activity-in-your-organization",
    "https://docs.github.com/en/copilot/github-copilot-enterprise/copilot-pull-request-summaries",
    "https://www.tabnine.com/enterprise/",
    "https://codeium.com/teams",
    "https://www.cursor.com/security",
    "https://aws.amazon.com/codewhisperer/features/",
    "https://getdx.com/blog/ai-code-security/",
    # === ПРОДУКТИВНОСТЬ И БЕНЧМАРКИ ===
    "https://github.blog/news/research-quantifying-github-copilots-impact-on-developer-productivity-and-happiness/",
    "https://arxiv.org/abs/2302.06590",
    "https://arxiv.org/abs/2107.03374",
    "https://www.swebench.com/",
    "https://aider.chat/2024/06/02/main-swe-bench.html",
    "https://cognition.ai/blog/swe-bench",
    "https://getdx.com/blog/measuring-developer-productivity/",
    "https://getdx.com/blog/ai-developer-tools-research/",
    # === OPEN SOURCE ИНСТРУМЕНТЫ ===
    "https://github.com/continuedev/continue",
    "https://github.com/paul-gauthier/aider",
    "https://github.com/cline/cline",
    "https://github.com/microsoft/vscode",
    "https://github.com/getcursor/cursor",
    "https://github.com/RooVetGit/Roo-Code",
    "https://github.com/anthropics/claude-code",
    # === ЛОКАЛЬНЫЕ МОДЕЛИ / ПРИВАТНОСТЬ ===
    "https://ollama.com/",
    "https://ollama.com/blog/",
    "https://ollama.com/library",
    "https://www.tabnine.com/blog/on-premise-ai/",
    "https://lmstudio.ai/",
    "https://jan.ai/",
    "https://gpt4all.io/",
    "https://docs.continue.dev/walkthroughs/running-with-ollama",
    # === AGENTIC CODING ===
    "https://lushbinary.com/blog/ai-coding-agents-comparison-cursor-windsurf-claude-copilot-kiro-2026/",
    "https://www.digitalapplied.com/blog/ai-coding-tools-comparison-december-2025",
    "https://cognition.ai/blog/introducing-devin",
    "https://docs.anthropic.com/en/docs/claude-code/tutorials",
    "https://github.blog/ai-and-ml/github-copilot/copilot-agent-mode/",
    "https://windsurf.com/blog/introducing-cascade",
    "https://docs.cursor.com/agent/overview",
    "https://replit.com/blog/replit-agent",
    # === VIBE CODING / NO-CODE ===
    "https://lovable.dev/blog",
    "https://bolt.new/",
    "https://vercel.com/blog/v0",
    "https://firebase.google.com/studio",
    "https://www.val.town/",
    "https://webflow.com/blog/ai-website-builder",
    # === ОБЗОРЫ / СРАВНЕНИЯ ===
    "https://www.g2.com/categories/ai-code-assistant",
    "https://www.g2.com/compare/github-copilot-vs-cursor",
    "https://www.g2.com/compare/github-copilot-vs-tabnine",
    "https://www.g2.com/compare/cursor-vs-windsurf",
    "https://www.capterra.com/ai-coding-software/",
    "https://alternativeto.net/software/github-copilot/about/",
    "https://alternativeto.net/software/cursor/about/",
    "https://alternativeto.net/software/codeium/about/",
    "https://www.trustradius.com/ai-coding-assistants",
    "https://stackshare.io/stackups/github-copilot-vs-cursor",
    "https://stackshare.io/stackups/github-copilot-vs-codeium",
    # === НОВОСТИ / ТРЕНДЫ ===
    "https://techcrunch.com/tag/github-copilot/",
    "https://techcrunch.com/tag/cursor/",
    "https://techcrunch.com/2024/10/29/github-copilot-gets-a-free-tier/",
    "https://techcrunch.com/2025/01/15/cursor-raises-series-b/",
    "https://www.theverge.com/ai-artificial-intelligence/copilot",
    "https://www.theverge.com/2024/1/22/24047553/microsoft-github-copilot-general-availability",
    "https://www.infoworld.com/article/ai-coding-tools/",
    "https://thenewstack.io/ai-coding-tools/",
    "https://thenewstack.io/github-copilot-vs-cursor-ai/",
    "https://news.ycombinator.com/item?id=cursor-ai-coding",
    # === STACKOVERFLOW / DEVELOPERS ===
    "https://survey.stackoverflow.co/2024/",
    "https://survey.stackoverflow.co/2024/ai",
    "https://stackoverflow.blog/2024/09/10/how-ai-coding-assistants-are-changing-developer-workflows/",
    "https://stackoverflow.blog/ai/",
    # === DEVELOPER BLOGS ===
    "https://martinfowler.com/articles/exploring-gen-ai.html",
    "https://simonwillison.net/tags/ai-coding/",
    "https://www.swyx.io/ai-coding",
    "https://eugeneyan.com/writing/coding-assistants/",
    "https://newsletter.pragmaticengineer.com/p/ai-tools-in-software-development",
    "https://www.trevorlasn.com/blog/cursor-vs-github-copilot",
    # === DOCS ВНУТРИ ИНСТРУМЕНТОВ ===
    "https://docs.github.com/en/copilot/using-github-copilot/prompt-engineering-for-github-copilot",
    "https://docs.cursor.com/context/rules-for-ai",
    "https://docs.cursor.com/cmdk/overview",
    "https://docs.windsurf.com/windsurf/cascade",
    "https://docs.anthropic.com/en/docs/claude-code/memory",
    "https://docs.anthropic.com/en/docs/claude-code/mcp",
    "https://aider.chat/docs/config.html",
    "https://continue.dev/docs/customization/models",
    # === AI-ASSISTED CODE REVIEW ===
    "https://www.tabnine.com/blog/ai-code-review/",
    "https://www.coderabbit.ai/",
    "https://www.coderabbit.ai/blog",
    "https://www.coderabbit.ai/pricing",
    "https://greptile.com/",
    "https://greptile.com/blog",
    "https://pr-agent-docs.codium.ai/",
    # === ТЕСТИРОВАНИЕ И КАЧЕСТВО ===
    "https://www.qodo.ai/blog/best-coding-ai-copilots/",
    "https://docs.qodo.ai/",
    "https://coveragent.qodo.ai/",
    "https://github.com/CodiumAI-Agent/pr-agent",
    # === DEVELOPER EXPERIENCE ===
    "https://getdx.com/",
    "https://getdx.com/blog/",
    "https://getdx.com/blog/ai-developer-tools-research/",
    "https://getdx.com/blog/measuring-developer-productivity/",
    "https://linearb.io/blog/ai-developer-tools/",
    "https://jellyfish.co/blog/ai-coding-tools/",
    # === СПЕЦИАЛИЗИРОВАННЫЕ ИНСТРУМЕНТЫ ===
    "https://www.dataiku.com/product/key-capabilities/ai-code-generation/",
    "https://aws.amazon.com/sagemaker/code-whisperer/",
    "https://cloud.google.com/duet-ai",
    "https://azure.microsoft.com/en-us/products/github/copilot",
    "https://azure.microsoft.com/en-us/blog/category/developer/",
    # === MOBILE DEVELOPMENT ===
    "https://flutterflow.io/",
    "https://flutterflow.io/blog",
    "https://docs.flutterflow.io/ai-features",
    "https://expo.dev/blog/ai-coding-tools",
    # === KUBERNETES / DEVOPS / INFRA ===
    "https://www.jetbrains.com/ai/",
    "https://plugins.jetbrains.com/plugin/22282-github-copilot",
    "https://www.hashicorp.com/blog/ai-for-infrastructure-as-code",
    "https://aws.amazon.com/blogs/devops/amazon-q-developer-for-devops/",
    # === COMMUNITY / REDDIT / HN ===
    "https://www.reddit.com/r/ChatGPTCoding/top/?t=year",
    "https://www.reddit.com/r/cursor/top/?t=year",
    "https://www.reddit.com/r/github/comments/cursor-vs-copilot",
    "https://news.ycombinator.com/item?id=ai-coding-tools-2024",
    # === PODCASTS / VIDEOS ===
    "https://www.youtube.com/watch?v=cursor-ai-review",
    "https://changelog.com/podcast/ai-coding",
    "https://softskills.audio/ai-coding",
    # === LLM UNDERLYING MODELS ===
    "https://openai.com/gpt-4",
    "https://www.anthropic.com/claude",
    "https://deepmind.google/technologies/gemini/",
    "https://mistral.ai/",
    "https://deepseek.com/",
    "https://ai.meta.com/llama/",
    # === BENCHMARKS ===
    "https://www.swebench.com/",
    "https://huggingface.co/blog/swebench",
    "https://livecodebench.github.io/",
    "https://arxiv.org/abs/2310.06770",
    # === RESEARCH ===
    "https://arxiv.org/abs/2302.06590",
    "https://arxiv.org/abs/2107.03374",
    "https://arxiv.org/abs/2308.12950",
    "https://arxiv.org/abs/2402.01030",
    "https://github.blog/news/research-quantifying-github-copilots-impact-on-developer-productivity-and-happiness/",
    "https://metr.org/blog/2025-07-10-measuring-ai-coding-productivity/",
    # === DOCS ANTHROPIC / OPENAI ===
    "https://docs.anthropic.com/en/docs/",
    "https://docs.anthropic.com/en/docs/about-claude/models/",
    "https://platform.openai.com/docs/",
    "https://platform.openai.com/docs/models",
    # === СТАТЬИ ПРО ENTERPRISE ADOPTION ===
    "https://github.blog/enterprise-software/collaboration/survey-reveals-ais-impact-on-the-developer-experience/",
    "https://github.blog/ai-and-ml/generative-ai/survey-ai-wave-grows/",
    "https://getdx.com/blog/enterprise-ai-coding-tools/",
    "https://thenewstack.io/enterprise-ai-coding-tools-2025/",
    "https://www.mckinsey.com/capabilities/mckinsey-digital/our-insights/unleashing-developer-productivity-with-generative-ai",
    "https://www.gartner.com/en/articles/what-is-an-ai-coding-assistant",
    # === ДОПОЛНИТЕЛЬНЫЕ БЛОГИ ===
    "https://devblogs.microsoft.com/visualstudio/category/copilot/",
    "https://github.blog/category/ai/",
    "https://aws.amazon.com/blogs/devops/",
    "https://cloud.google.com/blog/products/application-development",
    "https://openai.com/news/",
    "https://www.anthropic.com/news",
    "https://huggingface.co/blog",
    # === CURSOR COMMUNITY / CHANGELOG ===
    "https://changelog.cursor.com/",
    "https://forum.cursor.com/",
    "https://www.cursor.com/blog/cursor-tab",
    "https://www.cursor.com/blog/shadow-workspace",
    # === PRODUCTIVITY STUDIES ===
    "https://github.blog/news/research-quantifying-github-copilots-impact-in-the-enterprise/",
    "https://github.blog/ai-and-ml/github-copilot/research-quantifying-github-copilots-impact-on-developer-productivity-and-happiness/",
    "https://getdx.com/blog/ai-coding-productivity-report-2025/",
    "https://newsletter.pragmaticengineer.com/p/ai-tools-in-software-development",
    # === SECURITY / SUPPLY CHAIN ===
    "https://snyk.io/blog/ai-coding-assistants-security/",
    "https://snyk.io/reports/ai-developer-survey/",
    "https://www.sonarqube.org/blog/ai-code-security/",
    "https://github.blog/security/vulnerability-research/ai-generated-code-security/",
    # === ДОПОЛНИТЕЛЬНЫЕ ИНСТРУМЕНТЫ ===
    "https://www.pieces.app/",
    "https://www.pieces.app/blog",
    "https://pieces.app/blog/ai-developer-tools",
    "https://bloop.ai/",
    "https://www.phind.com/",
    "https://www.phind.com/blog",
    "https://plandex.ai/",
    "https://github.com/plandex-ai/plandex",
    "https://mentat.ai/",
    "https://github.com/biobootloader/wolverine",
    "https://www.starcoder.tech/",
    "https://bigcode-project.org/",
    "https://www.codestral.com/",
    # === НОВЫЕ АГЕНТНЫЕ ИНСТРУМЕНТЫ ===
    "https://www.factory.ai/",
    "https://www.factory.ai/blog",
    "https://poolside.ai/",
    "https://github.com/microsoft/autogen",
    "https://www.langchain.com/",
    "https://docs.langchain.com/",
    "https://openai.com/blog/introducing-swarm",
    # === STACKOVERFLOW SURVEY ===
    "https://survey.stackoverflow.co/2024/ai",
    "https://survey.stackoverflow.co/2024/technology",
    "https://stackoverflow.blog/2023/12/19/the-hardest-question-to-answer-as-a-developer-how-do-ai-coding-tools-impact-productivity/",
    "https://stackoverflow.blog/2024/04/09/the-2024-developer-survey-results-are-live/",
    # === JETBRAINS SURVEY ===
    "https://www.jetbrains.com/lp/devecosystem-2024/",
    "https://www.jetbrains.com/lp/devecosystem-2024/ai/",
    "https://blog.jetbrains.com/blog/2024/10/08/jetbrains-developer-ecosystem-survey-2024/",
    # === ПРОЧИЕ РЕСУРСЫ ===
    "https://github.com/e2b-dev/awesome-ai-agents",
    "https://github.com/abi/screenshot-to-code",
    "https://huggingface.co/spaces/bigcode/bigcode-model-license-check",
    "https://bigcode-project.org/docs/",
    "https://www.deeplearning.ai/short-courses/pair-programming-llm/",
    "https://learnprompting.org/docs/applications/coding",
    "https://www.promptingguide.ai/applications/coding",
    # === INDIE / COMMUNITY ===
    "https://ghuntley.com/",
    "https://ghuntley.com/stdlib/",
    "https://www.buildrightside.com/blog/ai-coding-tools",
    "https://www.developing.dev/p/github-copilot-vs-cursor",
    "https://engineeringprompts.substack.com/p/best-ai-coding-tools-2025",
    # === AWS / AZURE / GCP SPECIFICS ===
    "https://aws.amazon.com/q/developer/",
    "https://aws.amazon.com/q/developer/features/",
    "https://azure.microsoft.com/en-us/blog/azure-ai-foundry/",
    "https://cloud.google.com/vertex-ai/generative-ai/docs/code/code-models-overview",
    # === DOCS ПРОДУКТИВНОСТИ ===
    "https://github.blog/developer-skills/productivity/",
    "https://github.blog/developer-skills/github/top-12-git-commands-every-developer-must-know/",
    "https://docs.github.com/en/copilot/using-github-copilot/best-practices-for-using-github-copilot",
    "https://docs.cursor.com/context/context-providers",
    "https://aider.chat/docs/usage/tips.html",
]

urls = list(dict.fromkeys(urls))
print(f"Всего уникальных URL: {len(urls)}")

# ── ВЫЗОВ scout_index ─────────────────────────────────────────────────────────
tool_payload = {
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
        "name": "scout_index",
        "arguments": {
            "topic": "AI developer tools copilots coding assistants 2024 2025",
            "source_type": "urls",
            "source_urls": urls,
            "cache_ttl_hours": 0
        }
    }
}

with open("/tmp/sc014_payload.json", "w") as f:
    json.dump(tool_payload, f)

print("Запускаю индексацию (~7-15 минут)...")
headers = [
    "-H", "Content-Type: application/json",
    "-H", "Accept: application/json, text/event-stream",
]
if session_id:
    headers += ["-H", f"Mcp-Session-Id: {session_id}"]

result = subprocess.run(
    ["curl", "-s", "-X", "POST", "http://localhost:8020/mcp"] + headers + ["-d", "@/tmp/sc014_payload.json"],
    capture_output=True, text=True, timeout=1200
)

body = result.stdout.strip()
if body.startswith("data:"):
    body = body[5:].strip()
try:
    out = json.loads(body)
    r = out.get("result", {})
    print(f"status:          {r.get('status')}")
    print(f"session_id:      {r.get('session_id')}")
    print(f"documents_count: {r.get('documents_count')}")
    print(f"chunks_count:    {r.get('chunks_count')}")
    print(f"failed_count:    {r.get('failed_count')}")
    print(f"message:         {r.get('message')}")
except Exception as e:
    print("Raw:", result.stdout[:2000])
    print("Err:", e)
SCRIPT
```

---

## Шаг 2 — Проверить PostgreSQL

```bash
docker exec scout-postgres psql -U scout_user -d scout_db -c "
SELECT id, topic, status, documents_count, chunks_count,
       ROUND(EXTRACT(EPOCH FROM (completed_at - created_at))) as seconds
FROM research_sessions ORDER BY created_at DESC LIMIT 5;"
```

---

## Шаг 3 — Поисковые запросы

```bash
SESSION_ID="<session_id из шага 1>"

# Получить session_id через MCP initialize + tools/call scout_list_sessions
# ИЛИ взять из вывода шага 1

for QUERY in \
  "GitHub Copilot vs Cursor comparison features" \
  "AI coding assistant pricing enterprise" \
  "agentic coding autonomous code generation" \
  "local offline private AI coding tool" \
  "code review AI security vulnerabilities" \
  "IDE integration VS Code JetBrains" \
  "developer productivity AI benchmark study"; do

  echo ""
  echo "=== $QUERY ==="

  python3 - << EOF
import json, subprocess

session_id = "$SESSION_ID"
headers = [
    "-H", "Content-Type: application/json",
    "-H", "Accept: application/json, text/event-stream",
    "-H", f"Mcp-Session-Id: {session_id}",
]
payload = json.dumps({
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params":{"name":"scout_search","arguments":{
        "session_id": session_id,
        "query": "$QUERY",
        "top_k": 5
    }}
})
r = subprocess.run(
    ["curl", "-s", "-X", "POST", "http://localhost:8020/mcp"] + headers + ["-d", payload],
    capture_output=True, text=True, timeout=60
)
body = r.stdout.strip()
if body.startswith("data:"): body = body[5:].strip()
try:
    d = json.loads(body)
    rs = d.get("result", {}).get("results", [])
    print(f"  results: {len(rs)}")
    for res in rs:
        print(f"  {res['similarity']:.3f} | {res['source_title'][:60]}")
except:
    print("  ERR:", r.stdout[:200])
EOF
done
```

---

## Шаг 4 — Сравнительная таблица

| Метрика | SC-012 (analytics, 190 URL) | SC-013 (analytics, 363 URL) | SC-014 (AI tools, 314 URL) |
|---------|----------------------------|-----------------------------|-----------------------------|
| documents_count | 109 | 204 | 184 |
| chunks_count | 562 | 1031 | 746 |
| failed_count | 71 | 150 | 120 |
| время (сек) | 49 | 73 | 62 |
| Q1 similarity | 0.688–0.750 | 0.705–0.750 | 0.704–0.730 |
| Q2 similarity | 0.701–0.719 | 0.705–0.725 | 0.715–0.765 |
| Q3 agentic | н/д | н/д | 0.709–0.738 |
| Q4 local/offline | н/д | н/д | 0.667–0.679 |
| Q5 security | н/д | н/д | 0.750–0.783 |
| Q6 IDE integration | н/д | н/д | 0.680–0.736 |
| Q7 productivity | н/д | н/д | 0.741–0.804 |

---

## Критерии готовности

- `scout_index` → статус `ready`
- `documents_count` > 250
- Все 7 поисковых запросов дали результаты
- Таблица заполнена

---

*Дата создания: 2026-03-16*

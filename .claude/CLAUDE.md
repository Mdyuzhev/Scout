| SC-003 | ingestion | ✅ выполнена |
| SC-004 | retrieval | ✅ выполнена |
| SC-005 | mcp-server | ✅ выполнена |
| SC-006 | postgres-session-store | ✅ выполнена |
| SC-007 | deploy | ✅ выполнена |
| SC-008 | first-real-run | ✅ выполнена |
| SC-009 | connect-llm-brief | 🔲 в очереди |
| SC-010 | three-runs-mini-midi-long | ⚠️ заблокирована (DDG bot-block) |

Задачи: `Tasks/backlog/` (в работе), `Tasks/done/` (выполненные)

---

## Запрещено

- ssh, sshpass — только homelab MCP или paramiko
- Деплоить вручную — только через git push → CI/CD
- Настраивать /opt/scout или runner повторно — уже сделано
- Тянуть новые модели Ollama
- LLM на этапе сбора/фильтрации (только финальный шаг)

---

Полный справочник: `.claude/reference.md`

*Обновлено: 2026-03-16 (SC-010: код done, прогоны заблокированы DDG bot-block)*

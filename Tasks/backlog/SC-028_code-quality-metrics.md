# SC-028 — Метрики качества генерации кода: что и как измеряют

**Статус:** TODO
**Цель:** Систематизировать существующие метрики качества сгенерированного кода — compilation rate, test pass rate, acceptance rate и другие
**Точность:** Высокая — ищем академические работы с конкретными метриками

---

## Параметры запуска Scout

```
topic:              "code generation quality metrics compilation rate test pass rate LLM evaluation benchmark 2023-2025"
query:              "какие метрики используются для оценки качества кода сгенерированного LLM, что такое compilation rate pass@k acceptance rate, как измеряют стабильность вывода при повторных запусках, существуют ли метрики для повторяемости результата code generation"
auto_collect:       True
auto_collect_count: 150
model:              sonnet
language:           ru
top_k:              15
save_to:            "/opt/scout/results/2026-03-21_code-quality-metrics.md"
```

## Что ищем

Академические работы и бенчмарки: HumanEval, MBPP, SWE-bench, pass@k.
Особый интерес — метрики стабильности: что происходит с качеством при
повторных запросах одного и того же задания? Есть ли работы, измеряющие
variance между runs?

Это прямая связь с параметром p_fail(τ) в модели: как в литературе
формализуют «долю неудачных запусков»?

## Куда кладём результат

`E:\Diser\literature\english\sc028_code_quality_metrics.md`

## Зачем диссертации

Параметр p_fail(τ) нужно обосновать через существующую литературу по
метрикам. Также нужно позиционировать метрику EVA (Oracle Strength)
относительно стандартных метрик качества — чем она дополняет pass@k
и compilation rate.

*Создана: март 2026*

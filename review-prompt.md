Сделай ревью текущего GitHub pull request, используя приложенные `pr.json`, `changed-files.txt` и `pr.diff`.

Пиши только на русском языке.

Цель: найти реальные баги, внесённые именно этим PR. Не пиши про стиль, вкусовщину, рефакторинг и общие best practices без конкретного failure mode.

Проверь в первую очередь:
- корректность и регрессии поведения
- data integrity и dangling references
- validation gaps и nullable/empty значения
- frontend/backend mismatch
- rollout/migration/runtime failures
- timeout, retry, rollback, non-JSON/network failure paths
- performance issues только с понятным сценарием деградации

Верни только findings в таком формате:

### [SEVERITY] `path/to/file.py:123`
Коротко опиши проблему, когда она проявится и минимальное исправление. Максимум 80 слов.

Правила:
- SEVERITY: CRITICAL, HIGH, MEDIUM или LOW.
- Один finding = один заголовок и один короткий абзац.
- Не используй подзаголовки, списки, таблицы, code blocks, summary, intro, outro или verdict.
- Не используй line ranges. Указывай одну наиболее близкую строку из изменённого diff.
- Если точную строку определить нельзя, используй ближайшую изменённую строку в том же файле.
- Если сильных findings нет, верни ровно `NO_FINDINGS`.

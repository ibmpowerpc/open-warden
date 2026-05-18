Сделай ревью текущего GitHub pull request, используя приложенные метаданные PR, список изменённых файлов и diff.

Пиши ревью только на русском языке.

Главная цель:
- найти реальные баги, внесённые именно этим PR
- отфильтровать слабые замечания, стиль, вкусовщину и общие architectural risks без конкретного failure mode

Обязательный порядок анализа:
1. Сначала составь внутренний inventory всех changed files и ранжируй их по риску.
2. Глубоко проверь high-risk файлы, затем пройдись по остальным changed files.
3. Для каждого high-risk изменения проверь, какой инвариант оно добавляет или меняет.
4. После первого найденного бага продолжай ревью остальных changed files.
5. Перед финальным ответом ещё раз проверь, не пропущены ли более сильные баги, чем уже найденные.

Классы багов, которые нужно проверить явно:
- изменение схемы БД без миграции или с ручным rollout
- frontend/backend mismatch: значения формы, имена параметров, default selections, routes, JSON shape
- validation gaps: входные данные из формы/API, allowlist, nullable fields, размер данных
- post-validation mutations: код, который меняет уже провалидированные данные и может нарушить инварианты
- data integrity: ссылки между объектами, id, foreign keys, dangling references, duplicate handling
- state-changing endpoints: auth, authorization, CSRF, rate/cost abuse, повторные запросы
- failure paths: timeout, non-JSON response, network failure, rollback, user-visible stuck UI
- deployment/runtime limits: worker timeout, proxy timeout, missing env/config, dependency changes

Правила отбора findings:
- сообщай только о high-confidence проблемах, действительно вызванных этим PR
- finding должен иметь конкретный путь воспроизведения или очень чёткий production failure mode
- если проблема уже существовала до PR и PR её не усиливает, не включай её
- не склеивай независимые баги в один finding
- не включай maintenance notes вроде hardcoded URL, duplicate config, naming, unused dependency, если они не ломают поведение
- не включай cosmetic/UI-style замечания
- лучше 3 сильных finding, чем 10 слабых
- если видишь только слабые пункты, явно не повышай им severity

Для каждого finding:
- укажи severity: CRITICAL, HIGH, MEDIUM или LOW
- укажи точный changed file и строку или hunk
- объясни конкретный failure mode
- объясни, как воспроизвести проблему
- предложи минимальное практичное исправление

Особая проверка перед финалом:
- Если среди findings нет ни одного про data integrity, validation или rollout, перепроверь самые рискованные changed files.
- Если finding похож на совет по поддерживаемости, убери его, если нет доказанного user-visible, runtime или deployment failure.

Верни только итоговое ревью в markdown. Не показывай внутренний inventory и ход рассуждений.

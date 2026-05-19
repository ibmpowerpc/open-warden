# open-warden

CLI-утилита для AI-ревью GitHub pull request через OpenCode.

## Требования

- Python 3.11+
- `opencode`
- GitHub CLI `gh`
- авторизация в GitHub через `gh auth login`
- API-ключ провайдера модели

Для текущего конфига:

```bash
export ROUTERAI_API_KEY=...
```

## Запуск

Из репозитория, где текущая ветка связана с открытым PR:

```bash
/path/to/run_pr_review.py
```

Для конкретного PR:

```bash
/path/to/run_pr_review.py \
  --pr-url https://github.com/owner/repository/pull/123
```

Опубликовать результат в PR одним комментарием:

```bash
/path/to/run_pr_review.py \
  --ci-mode \
  --pr-url https://github.com/owner/repository/pull/123
```

## Настройка

Основные настройки лежат в `config.toml`.

Переопределить модель на один запуск:

```bash
export OPENCODE_REVIEW_MODEL=anthropic/claude-sonnet-4.6
```

Использовать другой конфиг:

```bash
export OPENCODE_REVIEW_CONFIG=/path/to/config.toml
```

## CI

Для публикации комментариев в GitHub PR нужны права:

```yaml
permissions:
  contents: read
  pull-requests: write
  issues: write
```

Минимальный запуск:

```bash
/path/to/run_pr_review.py --ci-mode --pr-url "$PR_URL"
```

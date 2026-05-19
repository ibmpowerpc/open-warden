# open-warden

Локальная CLI-утилита для AI-ревью текущего GitHub pull request через OpenCode.

## Требования

- Python 3.11+
- `opencode`
- GitHub CLI `gh`
- авторизация через `gh auth login`
- открытый GitHub PR для текущей ветки
- API-ключ провайдера из `config.toml`

Для текущего конфига:

```bash
export ROUTERAI_API_KEY=...
```

## Запуск

Из любого репозитория с открытым PR:

```bash
/path/to/run_pr_review.py
```

## Конфиг

Настройки лежат в `config.toml`.

По умолчанию используется RouterAI и Claude Sonnet:

```toml
[provider]
id = "routerai"
base_url = "https://routerai.ru/api/v1"
api_key_env = "ROUTERAI_API_KEY"

[model]
id = "anthropic/claude-sonnet-4.6"

[paths]
prompt = "review-prompt.md"
scratch_dir = "tmp/opencode"
```

Временно переопределить модель:

```bash
export OPENCODE_REVIEW_MODEL=deepseek/deepseek-v4-pro
```

Использовать другой конфиг:

```bash
export OPENCODE_REVIEW_CONFIG=/path/to/config.toml
```


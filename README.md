# open-warden

CLI-утилита для AI-ревью GitHub pull request через OpenCode.

#### 1. Локальный запуск

Запустите ревью для текущего pull request из локального репозитория:

```bash
export ROUTERAI_API_KEY=your_key_here
/path/to/run_pr_review.py
```

Или укажите pull request явно:

```bash
/path/to/run_pr_review.py \
  --pr-url https://github.com/owner/repository/pull/123
```

#### 2. Публикация комментария в PR

Добавьте флаг `--ci-mode`, чтобы опубликовать результат ревью одним комментарием в pull request:

```bash
/path/to/run_pr_review.py \
  --ci-mode \
  --pr-url https://github.com/owner/repository/pull/123
```

Для публикации нужны авторизация GitHub CLI и права на комментарии в PR:

```bash
gh auth login
```

#### 3. GitHub Actions

Минимальный workflow для автоматического ревью pull request:

```yaml
# .github/workflows/open-warden.yml
name: Open Warden

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write
  issues: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run AI review
        run: /path/to/run_pr_review.py --ci-mode --pr-url "$PR_URL"
        env:
          GH_TOKEN: ${{ github.token }}
          ROUTERAI_API_KEY: ${{ secrets.ROUTERAI_API_KEY }}
          PR_URL: ${{ github.event.pull_request.html_url }}
```

#### 4. Настройка

Основные настройки находятся в `config.toml`.

Переопределить модель на один запуск:

```bash
export OPENCODE_REVIEW_MODEL=anthropic/claude-sonnet-4.6
```

Использовать другой конфиг:

```bash
export OPENCODE_REVIEW_CONFIG=/path/to/config.toml
```

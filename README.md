# Tempo — персональный Telegram-ассистент дня

Бот помогает держать расписание, самочувствие и мотивацию. Стек: **Python · aiogram 3 · PostgreSQL · Docker**.

## Возможности

- Пуши при смене блока дня (график + цитата из пула)
- Опрос самочувствия (физическое / моральное) в 07:30 и 22:00
- Режимы **учебное время / каникулы**
- Секундомер, настройки, Apple-style графики
- Доступ только для `ADMIN_ID`

## Быстрый старт

1. Заполни `.env`:

```env
BOT_TOKEN=...
ADMIN_ID=5007535736
POSTGRES_USER=tempo
POSTGRES_PASSWORD=tempo
POSTGRES_DB=tempo
TIMEZONE=Europe/Moscow
```

2. Запуск:

```bash
docker compose up -d --build
```

Логи:

```bash
docker compose logs -f bot
```

Локально без Docker (нужен PostgreSQL на `localhost:5433`):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# DATABASE_URL=postgresql+asyncpg://tempo:tempo@localhost:5433/tempo
python -m app.main
```

## Команды

`/start` · `/menu` · `/physical` · `/moral` · `/state` · `/stopwatch` · `/settings`

## Расписание

| Дни | 16:30–20:30 | 07:30–14:00 |
| --- | --- | --- |
| Пн / Ср / Пт | зал + IT | университет (учёба) / самообучение (каникулы) |
| Вт / Чт | IT | то же |
| Вс | IT | самообучение / IT |
| Сб | Recovery day | — |

- Мотивация берётся из локального пула цитат (без внешнего AI).
- Порт Postgres на хосте: **5433** (чтобы не конфликтовать с другими ботами).

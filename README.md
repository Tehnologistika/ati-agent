# ATI Agent ТехноЛогистики

Отдельный безопасный AI-агент для работы с заявками из MAX Messenger, подготовки черновиков публикаций на ATI.su, поиска перевозчиков, сбора ставок и ведения рыночной аналитики.

## Главный принцип

На первом этапе агент работает только в безопасном режиме `DRY_RUN=true`:

- ничего не публикует на ATI.su автоматически;
- не отправляет сообщения перевозчикам автоматически;
- не меняет боевые системы;
- не трогает Аюба, сайт, webhook-и и systemd;
- готовит только черновики и данные для ручного подтверждения.

## Первый MVP

1. Принять тестовую заявку из MAX Messenger или из файла.
2. Найти ключевое слово `ЗАЯВКА`.
3. Распарсить маршрут, автомобиль, дату, состояние, оплату и комментарий.
4. Сформировать структуру заявки.
5. Сформировать черновик публикации для ATI.su.
6. Вывести результат в консоль и записать audit log.
7. Ничего не отправлять и не публиковать.

## Структура проекта

```text
app/
  main.py               # Точка входа с поддержкой CLI
  config.py             # Настройки (Pydantic Settings)
  orchestrator.py       # Оркестрация процессов
  data_models/          # Pydantic модели данных
    request.py
  integrations/         # Клиенты внешних систем
    ati_client.py
    max_client.py
    gmail_client.py
    sheets_client.py
  services/             # Бизнес-логика
    request_parser.py
    draft_builder.py
    audit_writer.py

docs/                   # Техническая документация
  ATI_AGENT_ARCHITECTURE.md
  ATI_AGENT_MVP_PLAN.md
  ATI_API_FEASIBILITY_REPORT.md
  MAX_INTEGRATION_FEASIBILITY.md

examples/
  sample_max_request.txt # Пример входящей заявки

tests/
  test_request_parser.py # Тесты парсера
```

## Локальный запуск

Для запуска MVP в безопасном режиме выполните следующие команды:

```bash
# Создание и активация окружения
python3 -m venv .venv
source .venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Запуск тестов
export PYTHONPATH=$PYTHONPATH:.
pytest

# Запуск dry-run сценария
python3 -m app.main --input examples/sample_max_request.txt
```

## Результаты работы

После запуска агент:
1. Выведет в консоль JSON с результатами парсинга и черновиком ATI.
2. Создаст (или обновит) файл `events.jsonl` — локальный журнал событий (audit log).

## Переменные окружения

См. `.env.example`. Реальные ключи и токены в репозиторий не добавлять. По умолчанию `DRY_RUN=True`.

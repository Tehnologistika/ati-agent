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
  main.py
  config.py
  orchestrator.py
  integrations/
    ati_client.py
    max_client.py
    gmail_client.py
    sheets_client.py
  services/
    request_parser.py
    draft_builder.py
    audit_log.py
  models/
    request.py

docs/
  ATI_AGENT_ARCHITECTURE.md
  ATI_AGENT_MVP_PLAN.md
  ATI_API_FEASIBILITY_REPORT.md
  MAX_INTEGRATION_FEASIBILITY.md

examples/
  sample_max_request.txt

tests/
  test_request_parser.py
```

## Локальный тест

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main --input examples/sample_max_request.txt
```

## Переменные окружения

См. `.env.example`. Реальные ключи и токены в репозиторий не добавлять.

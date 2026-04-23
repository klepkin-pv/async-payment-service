# Async Payment Service

Микросервис для асинхронной обработки платежей:
- принимает запросы на создание платежа
- сохраняет событие в outbox
- публикует событие в RabbitMQ
- consumer эмулирует платёжный шлюз (2-5 сек, 90%/10%)
- обновляет статус платежа и отправляет webhook
- при неуспехе webhook после 3 попыток отправляет сообщение в DLQ

## Стек
- FastAPI + Pydantic v2
- SQLAlchemy 2.0 (async)
- PostgreSQL
- RabbitMQ + FastStream
- Alembic
- Docker Compose

## Запуск
```bash
docker compose up --build
```

Сервисы:
- API: `http://localhost:8000`
- RabbitMQ UI: `http://localhost:15672` (`guest/guest`)

## Миграции
```bash
alembic upgrade head
```

## Аутентификация
Для всех API-эндпоинтов обязателен заголовок:
`X-API-Key: dev-secret-key`

## API

### Создание платежа
`POST /api/v1/payments`

Headers:
- `X-API-Key: dev-secret-key`
- `Idempotency-Key: some-unique-key`

Body:
```json
{
  "amount": 100.50,
  "currency": "RUB",
  "description": "Order #123",
  "metadata": {"order_id": "123"},
  "webhook_url": "https://example.com/webhook"
}
```

Пример:
```bash
curl -X POST "http://localhost:8000/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: test-123" \
  -d '{"amount":100.50,"currency":"RUB","description":"Order #123","metadata":{"order_id":"123"},"webhook_url":"https://httpbin.org/post"}'
```

### Получение платежа
`GET /api/v1/payments/{payment_id}`

Пример:
```bash
curl "http://localhost:8000/api/v1/payments/<payment_id>" \
  -H "X-API-Key: dev-secret-key"
```

## Очереди и события
- Основной exchange: `payments.exchange`
- Основная очередь: `payments.new`
- DLQ exchange: `payments.dlq.exchange`
- DLQ очередь: `payments.dlq`

## Идемпотентность
`Idempotency-Key` уникален. Повторный запрос с тем же ключом возвращает уже созданный платеж.

БЕЗ:
Добавить уникальность пары `client_id + idempotency_key`, чтобы исключить пересечения между разными клиентами.

## Webhook и DLQ
- Если `webhook_url` доступен, consumer отправит уведомление о результате платежа.
- Если webhook недоступен, consumer делает 3 попытки (экспоненциальная задержка), затем кладёт сообщение в `payments.dlq`.
- DLQ здесь - это очередь для ручного разбора/повторного запуска отдельным воркером.

## Smoke load (быстрая проверка 90/10)
Есть скрипт [`tests/smoke_load.py`](tests/smoke_load.py), который:
- создаёт пачку платежей с уникальными `Idempotency-Key`
- дожидается финальных статусов (`succeeded/failed`)
- печатает сводку по статусам

Запуск:
```bash
python tests/smoke_load.py
```

Если нужно поменять объём/таймаут/адрес API, отредактируйте константы в начале файла:
- `PAYMENTS_COUNT`
- `CONCURRENCY`
- `WAIT_TIMEOUT_SECONDS`
- `BASE_URL`

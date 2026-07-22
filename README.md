# Async Payment Service

![CI](https://github.com/klepkin-pv/async-payment-service/actions/workflows/ci.yml/badge.svg)

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

## Тесты

Запуск unit/интеграционных тестов (требуется PostgreSQL):

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

CI запускает линтер (`ruff`) и тесты в GitHub Actions для каждого `push`/`pull_request`.

## Запуск
```bash
docker compose up --build
```

Сервисы:
- API: `http://localhost:8000`
- RabbitMQ UI: `http://localhost:15672` (`guest/guest`)

## Миграции
```bash
docker compose run --rm api alembic upgrade head
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

`Idempotency-Key` уникален в рамках сервиса. Повторный запрос с тем же ключом возвращает уже созданный платеж, независимо от других полей payload.

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

### List payments
`GET /api/v1/payments?limit=100&offset=0`

Example:
```bash
curl "http://localhost:8000/api/v1/payments?limit=50&offset=0" \
  -H "X-API-Key: dev-secret-key"
```

## Проверка статуса платежа

Создайте платёж, дождитесь обработки consumer (2–5 секунд) и получите результат:

```bash
# 1. Создание платежа
PAYMENT=$(curl -s -X POST "http://localhost:8000/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: demo-1" \
  -d '{"amount":100,"currency":"RUB","description":"Demo","metadata":{},"webhook_url":"https://httpbin.org/post"}' | \
  python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 2. Повторный запрос с тем же Idempotency-Key вернёт тот же платёж
curl -s -X POST "http://localhost:8000/api/v1/payments" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-secret-key" \
  -H "Idempotency-Key: demo-1" \
  -d '{"amount":999,"currency":"USD","description":"Different"}' | \
  python -c "import sys,json; d=json.load(sys.stdin); print(d['id'], d['status'])"

# 3. Получение статуса
curl "http://localhost:8000/api/v1/payments/$PAYMENT" \
  -H "X-API-Key: dev-secret-key"
```

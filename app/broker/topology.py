from faststream.rabbit import RabbitExchange, RabbitQueue

PAYMENTS_EXCHANGE_NAME = "payments.exchange"
PAYMENTS_NEW_ROUTING_KEY = "payments.new"
PAYMENTS_DLQ_EXCHANGE_NAME = "payments.dlq.exchange"
PAYMENTS_DLQ_ROUTING_KEY = "payments.dlq"

PAYMENTS_EXCHANGE = RabbitExchange(PAYMENTS_EXCHANGE_NAME, type="direct", durable=True)
PAYMENTS_NEW_QUEUE = RabbitQueue(
    name="payments.new",
    durable=True,
    routing_key=PAYMENTS_NEW_ROUTING_KEY,
)

PAYMENTS_DLQ_EXCHANGE = RabbitExchange(
    PAYMENTS_DLQ_EXCHANGE_NAME, type="direct", durable=True
)
PAYMENTS_DLQ_QUEUE = RabbitQueue(
    name="payments.dlq",
    durable=True,
    routing_key=PAYMENTS_DLQ_ROUTING_KEY,
)

"""Mismo contrato de recuperacion para Order y Product; ejecutar en ambos."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import rabbitmq, messaging


class MessagingStability(unittest.TestCase):
    def setUp(self):
        self.channel = Mock()
        self.channel.basic_publish.return_value = None
        self.method = SimpleNamespace(delivery_tag=12)
        self.properties = SimpleNamespace(headers={}, message_id="event-1")
        self.body = json.dumps({"event": "PAYMENT_COMPLETED"}).encode()

    def test_temporary_failure_retries_before_acknowledging(self):
        with patch.object(rabbitmq, "process_payment_completed", side_effect=rabbitmq.TemporaryValidationError("offline")):
            rabbitmq.callback(self.channel, self.method, self.properties, self.body)
        call = self.channel.basic_publish.call_args.kwargs
        self.assertEqual(call["exchange"], messaging.RETRY_EXCHANGE)
        self.assertEqual(call["properties"].headers[messaging.ATTEMPT_HEADER], 2)
        self.assertEqual(call["properties"].message_id, "event-1")
        self.assertEqual([c[0] for c in self.channel.method_calls], ["basic_publish", "basic_ack"])

    def test_exhausted_retry_goes_to_dlq(self):
        self.properties.headers[messaging.ATTEMPT_HEADER] = 3
        with patch.object(rabbitmq, "process_payment_completed", side_effect=rabbitmq.TemporaryValidationError("offline")):
            rabbitmq.callback(self.channel, self.method, self.properties, self.body)
        self.assertEqual(self.channel.basic_publish.call_args.kwargs["routing_key"], messaging.DLQ)

    def test_invalid_json_is_saved_in_dlq(self):
        rabbitmq.callback(self.channel, self.method, self.properties, b"invalid json")
        self.assertEqual(self.channel.basic_publish.call_args.kwargs["routing_key"], messaging.DLQ)
        self.channel.basic_ack.assert_called_once()

    def test_failed_forward_does_not_acknowledge_original(self):
        self.channel.basic_publish.return_value = False
        with self.assertRaises(RuntimeError):
            messaging.forward(self.channel, self.method, self.properties, self.body, temporary=True)
        self.channel.basic_ack.assert_not_called()

    def test_nack_exception_does_not_acknowledge_original(self):
        import pika
        self.channel.basic_publish.side_effect = pika.exceptions.NackError([])
        with self.assertRaises(pika.exceptions.NackError):
            messaging.forward(self.channel, self.method, self.properties, self.body, temporary=True)
        self.channel.basic_ack.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)

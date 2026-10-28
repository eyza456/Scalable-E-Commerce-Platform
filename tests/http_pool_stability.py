"""Ejecutar en Order, Payment y Cart; transporte simulado, sin datos reales."""
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock, patch
import httpx
from app import http_client


class HttpPoolStability(unittest.TestCase):
    def setUp(self):
        http_client.close()
        self.requests = []
        self.callback = lambda request: httpx.Response(200, json={"ok": True})

        def handler(request):
            self.requests.append(request)
            return self.callback(request)

        self.transport = httpx.MockTransport(handler)
        self.transport.close = Mock(wraps=self.transport.close)
        patcher = patch.object(http_client, "_new_transport", return_value=self.transport)
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(http_client.close)

    def test_reuses_pool_without_closing_it_after_each_response(self):
        self.assertTrue(http_client.get("http://service/one").json()["ok"])
        self.assertTrue(http_client.get("http://service/two").json()["ok"])
        self.factory.assert_called_once()
        self.transport.close.assert_not_called()
        http_client.close()
        self.transport.close.assert_called_once()

    def test_tokens_and_response_cookies_are_isolated_per_request(self):
        self.callback = lambda request: httpx.Response(200, headers={"Set-Cookie": "session=private; Path=/"}, json={})
        http_client.get("http://service/one", headers={"Authorization": "Bearer alice"})
        http_client.get("http://service/two", headers={"Authorization": "Bearer bob"})
        http_client.get("http://service/three")
        self.assertEqual([r.headers.get("Authorization") for r in self.requests], ["Bearer alice", "Bearer bob", None])
        self.assertTrue(all("Cookie" not in r.headers for r in self.requests))

    def test_concurrent_users_do_not_share_authorization(self):
        self.callback = lambda request: httpx.Response(200, json={"authorization": request.headers["Authorization"]})
        def call(index):
            return http_client.get("http://service/me", headers={"Authorization": f"Bearer {index}"}).json()["authorization"]
        with ThreadPoolExecutor(max_workers=20) as pool:
            self.assertEqual(list(pool.map(call, range(40))), [f"Bearer {i}" for i in range(40)])
        self.factory.assert_called_once()

    def test_status_and_per_call_timeout_are_preserved(self):
        self.callback = lambda request: httpx.Response(503, json={"detail": "offline"})
        response = http_client.get("http://service/offline", timeout=3.5)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.requests[0].extensions["timeout"]["read"], 3.5)

    def test_response_loss_never_retries_post_automatically(self):
        def fail(request):
            raise httpx.ReadTimeout("response lost", request=request)
        self.callback = fail
        with self.assertRaises(httpx.ReadTimeout):
            http_client.post("http://service/orders", json={"quantity": 1})
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].method, "POST")

    def test_shutdown_is_idempotent_and_next_use_opens_new_pool(self):
        http_client.get("http://service/one")
        http_client.close()
        http_client.close()
        self.transport.close.assert_called_once()
        self.factory.return_value = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
        http_client.get("http://service/two")
        self.assertEqual(self.factory.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

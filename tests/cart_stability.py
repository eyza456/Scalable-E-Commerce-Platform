import concurrent.futures
import json
import threading
import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException
from app import cart_operations as cart
from app.schemas import CartItemCreate, CartItemUpdate
from app.storage import atomic, prepare, finish


class CartStability(unittest.TestCase):
    def setUp(self):
        self.uid = "test-cart-" + uuid.uuid4().hex
        self.key = "cart:" + self.uid
        self.user = {"id": self.uid}
        self.redis = cart.redis_client
        self.product = {"id":1,"name":"Test","price":"10.00","stock":100,"is_active":True}
        self.patch = patch.object(cart,"product_snapshot",return_value=self.product)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.redis.delete,self.key)

    def add(self, product_id=1):
        return cart.add_item_to_cart(CartItemCreate(product_id=product_id,quantity=1),self.user)

    def test_concurrent_adds_keep_every_unit(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda _: self.add(),range(20)))
        self.assertEqual(cart.get_cart(self.user)["items"][0]["quantity"],20)

    def test_concurrent_distinct_items_are_not_lost(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(self.add,[1,2]))
        self.assertEqual({i["product_id"] for i in cart.get_cart(self.user)["items"]},{1,2})

    def test_frozen_cart_rejects_all_edits(self):
        self.add()
        version=cart.get_cart(self.user)["version"]
        prepare(self.redis,self.uid,version)
        for action in (self.add,lambda:cart.update_cart_item(1,CartItemUpdate(quantity=2),self.user),
                       lambda:cart.delete_cart_item(1,self.user),lambda:cart.clear_cart(self.user)):
            with self.subTest(action=action),self.assertRaises(HTTPException) as caught:
                action()
            self.assertEqual(caught.exception.status_code,409)

    def test_prepare_is_idempotent_and_versioned(self):
        self.add()
        version=cart.get_cart(self.user)["version"]
        first=prepare(self.redis,self.uid,version)
        second=prepare(self.redis,self.uid,version)
        self.assertEqual(first,second)
        self.assertEqual(second["checkout_id"],version)

    def test_late_commit_cannot_delete_new_cart(self):
        self.add()
        version=cart.get_cart(self.user)["version"]
        prepare(self.redis,self.uid,version)
        finish(self.redis,self.uid,version,True)
        self.add()
        new=cart.get_cart(self.user)
        finish(self.redis,self.uid,version,True)
        self.assertEqual(cart.get_cart(self.user),new)
        self.assertEqual(new["items"][0]["quantity"],1)

    def test_abort_keeps_contents_and_allows_fresh_version(self):
        self.add()
        version=cart.get_cart(self.user)["version"]
        prepare(self.redis,self.uid,version)
        finish(self.redis,self.uid,version,False)
        result=cart.get_cart(self.user)
        self.assertEqual(result["items"][0]["quantity"],1)
        self.assertNotEqual(result["version"],version)
        self.assertIsNone(result["checkout_id"])

    def test_legacy_cart_is_upgraded_without_losing_items(self):
        self.redis.set(self.key,json.dumps({"items":[{"product_id":1,"name":"Old","price":"1.00","quantity":2}]}))
        first=cart.get_cart(self.user)
        self.assertEqual(first["items"][0]["quantity"],2)
        self.assertEqual(first["version"],cart.get_cart(self.user)["version"])

    def test_explicit_quantity_update_refreshes_price(self):
        self.add()
        self.product["price"]="20.00"
        cart.update_cart_item(1,CartItemUpdate(quantity=1),self.user)
        self.assertEqual(str(cart.get_cart(self.user)["items"][0]["price"]),"20.00")

    def test_item_delete_and_clear_are_versioned(self):
        self.add(1); self.add(2)
        before=cart.get_cart(self.user)["version"]
        cart.delete_cart_item(1,self.user)
        self.assertEqual([i["product_id"] for i in cart.get_cart(self.user)["items"]],[2])
        self.assertNotEqual(before,cart.get_cart(self.user)["version"])
        cart.clear_cart(self.user)
        self.assertEqual(cart.get_cart(self.user)["items"],[])


if __name__=="__main__":
    unittest.main(verbosity=2)

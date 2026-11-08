"""Specification tests, including defects deliberately exposed on the starter."""

import json
from supplydesk.service import OrderService
from tests.support import DeskTestCase, item


class ServiceTests(DeskTestCase):
    def test_catalog_and_quote_do_not_save_or_reserve(self):
        before = self.service.catalog()
        quote = self.service.quote("student", [item("hoodie", 2)], "delivery")
        self.assertEqual(
            [quote[key] for key in ("subtotal_cents", "discount_cents", "delivery_cents", "total_cents")],
            [8000, 800, 600, 7800],
        )
        self.assertEqual(self.service.catalog(), before)
        self.assertFalse(self.path.exists())

    def test_quote_matches_placement(self):
        items = [item("hoodie", 2), item("mug", 1)]
        quote = self.service.quote("student", items, "delivery")
        order = self.service.place_order("student", items, "delivery")
        self.assertEqual({key: order[key] for key in quote}, quote)
        self.assertEqual(self.stock("hoodie"), 3)
        self.assertEqual(self.stock("mug"), 7)

    def test_discount_below_and_above_threshold(self):
        below = self.service.quote("student", [item("notebook", 9)])
        above = self.service.quote("student", [item("notebook", 9), item("pen-pack", 1)])
        self.assertEqual(below["discount_cents"], 0)
        self.assertEqual(above["discount_cents"], 525)

    def test_discount_at_exact_threshold(self):
        for operation in (self.service.quote, self.service.place_order):
            with self.subTest(operation=operation.__name__):
                result = operation("student", [item("notebook", 10)])
                self.assertEqual(result["discount_cents"], 500)
                self.assertEqual(result["total_cents"], 4500)

    def test_discount_rounds_half_cent_up_using_integer_money(self):
        for price, expected in ((5004, 500), (5005, 501), (5006, 501)):
            with self.subTest(price=price):
                self.seed_catalog(price)
                result = self.service.quote("student", [item("notebook", 1)])
                self.assertEqual(result["discount_cents"], expected)
                for key in ("subtotal_cents", "discount_cents", "delivery_cents", "total_cents"):
                    self.assertIs(type(result[key]), int)

    def test_regular_customer_has_no_discount(self):
        result = self.service.quote("regular", [item("hoodie", 3)])
        self.assertEqual(result["discount_cents"], 0)
        self.assertEqual(result["total_cents"], 12000)

    def test_standard_delivery_threshold_and_pickup(self):
        for quantity, fee in ((19, 600), (20, 0)):
            with self.subTest(quantity=quantity):
                result = self.service.quote("regular", [item("notebook", quantity)], "delivery")
                self.assertEqual(result["delivery_cents"], fee)
        self.assertEqual(self.service.quote("regular", [item("notebook", 1)])["delivery_cents"], 0)

    def test_free_delivery_uses_discounted_merchandise(self):
        charged = self.service.quote("student", [item("hoodie", 2), item("mug", 2)], "delivery")
        free = self.service.quote("student", [item("hoodie", 2), item("mug", 2), item("notebook", 1)], "delivery")
        self.assertEqual((charged["subtotal_cents"], charged["discount_cents"], charged["delivery_cents"]),
                         (11000, 1100, 600))
        self.assertEqual(free["delivery_cents"], 0)

    def test_quantity_one_and_ninety_nine(self):
        self.seed_catalog(500)
        for quantity in (1, 99):
            with self.subTest(quantity=quantity):
                result = self.service.quote("regular", [item("notebook", quantity)])
                self.assertEqual(result["items"][0]["quantity"], quantity)
                self.assertEqual(result["total_cents"], 500 * quantity)

    def test_invalid_quantities_preserve_saved_state_and_number(self):
        self.service.place_order("regular", [item("mug", 1)])
        before = self.path.read_bytes()
        for quantity in (True, False, "2", 2.5, 0, -1, 100, None):
            for operation in (self.service.quote, self.service.place_order):
                with self.subTest(quantity=quantity, operation=operation.__name__):
                    with self.assertRaises(ValueError):
                        operation("regular", [item("notebook", quantity)])
                    self.assertEqual(self.path.read_bytes(), before)
        order = self.service.place_order("regular", [item("mug", 1)])
        self.assertEqual(order["order_id"], "ORD-0002")

    def test_invalid_requests_do_not_create_a_save(self):
        requests = [
            ("staff", [item("mug", 1)], "pickup"),
            ("regular", [item("mug", 1)], "drone"),
            ("regular", [], "pickup"),
            ("regular", None, "pickup"),
            ("regular", (item("mug", 1),), "pickup"),
            ("regular", ["mug"], "pickup"),
            ("regular", [{}], "pickup"),
            ("regular", [{"product_id": "mug"}], "pickup"),
            ("regular", [item("missing", 1)], "pickup"),
        ]
        for request in requests:
            for operation in (self.service.quote, self.service.place_order):
                with self.subTest(request=request, operation=operation.__name__):
                    with self.assertRaises(ValueError):
                        operation(*request)
                    self.assertFalse(self.path.exists())

    def test_late_invalid_item_preserves_prior_order_and_stock(self):
        self.service.place_order("regular", [item("mug", 1)])
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("notebook", 2), item("missing", 1)])
        self.assertEqual(self.path.read_bytes(), before)

    def test_duplicate_lines_at_stock_limit_are_preserved(self):
        result = self.service.place_order("regular", [item("bag", 2), item("bag", 2)])
        self.assertEqual([line["quantity"] for line in result["items"]], [2, 2])
        self.assertEqual(self.stock("bag"), 0)
        self.assertEqual(result["total_cents"], 10000)

    def test_duplicate_lines_over_stock_rejected_by_quote(self):
        with self.assertRaises(ValueError):
            self.service.quote("regular", [item("bag", 3), item("bag", 2)])
        self.assertFalse(self.path.exists())

    def test_duplicate_lines_over_stock_rejected_by_placement(self):
        self.service.place_order("regular", [item("mug", 1)])
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("bag", 3), item("bag", 2)])
        self.assertEqual(self.path.read_bytes(), before)

    def test_placement_rechecks_stock_after_quote(self):
        self.service.quote("regular", [item("bag", 4)])
        self.service.place_order("regular", [item("bag", 1)])
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("bag", 4)])
        self.assertEqual(self.path.read_bytes(), before)

    def test_unknown_order_preserves_save(self):
        self.service.place_order("regular", [item("mug", 1)])
        before = self.path.read_bytes()
        for operation in (self.service.get_order, self.service.cancel_order):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "Unknown order: ORD-9999"):
                    operation("ORD-9999")
                self.assertEqual(self.path.read_bytes(), before)

    def test_cancellation_preserves_snapshot_and_restores_stock(self):
        before = self.service.catalog()
        placed = self.service.place_order("student", [item("hoodie", 2)], "delivery")
        reopened = OrderService(self.path)
        self.assertEqual(reopened.get_order(placed["order_id"]), placed)
        cancelled = reopened.cancel_order(placed["order_id"])
        self.assertEqual(cancelled, {**placed, "status": "cancelled"})
        self.assertEqual(reopened.catalog(), before)
        self.assertEqual(OrderService(self.path).list_orders(), [cancelled])

    def test_repeated_cancellation_does_not_restore_stock_twice(self):
        order = self.service.place_order("regular", [item("pen-pack", 2)])
        cancelled = self.service.cancel_order(order["order_id"])
        stock = self.service.catalog()
        again = OrderService(self.path).cancel_order(order["order_id"])
        self.assertEqual(again, cancelled)
        self.assertEqual(self.service.catalog(), stock)

    def test_history_order_and_ids_survive_cancellation(self):
        first = self.service.place_order("regular", [item("mug", 1)])
        self.service.cancel_order(first["order_id"])
        second = self.service.place_order("regular", [item("notebook", 1)])
        third = OrderService(self.path).place_order("regular", [item("bag", 1)])
        history = self.service.list_orders()
        self.assertEqual([order["order_id"] for order in history], ["ORD-0001", "ORD-0002", "ORD-0003"])
        self.assertEqual([order["status"] for order in history], ["cancelled", "placed", "placed"])

    def test_historical_prices_do_not_follow_catalog_changes(self):
        order = self.service.place_order("regular", [item("notebook", 2)])
        state = self.service.store.load()
        state["catalog"][0]["unit_price_cents"] = 999
        self.service.store.save(state)
        self.assertEqual(OrderService(self.path).get_order(order["order_id"]), order)

    def test_malformed_or_unreadable_save_reports_error(self):
        self.path.write_text("{broken", encoding="utf-8")
        for operation in (self.service.catalog, self.service.list_orders):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(ValueError):
                    operation()
                self.assertEqual(self.path.read_text(), "{broken")
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaises(OSError):
            self.service.catalog()

    def test_schema_one_save_reopens(self):
        order = self.service.place_order("regular", [item("mug", 1)])
        state = json.loads(self.path.read_text())
        self.assertEqual(state["schema_version"], 1)
        self.assertEqual(OrderService(self.path).get_order(order["order_id"]), order)

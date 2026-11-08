"""Acceptance coverage for the instructor's CR-01 express delivery request."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
from unittest.mock import patch

from supplydesk.menu import run_menu
from supplydesk.service import OrderService
from tests.support import DeskTestCase, item


class ExpressTests(DeskTestCase):
    def test_instructor_pricing_examples(self):
        cases = [
            ("regular", [item("notebook", 2)], 0, 2200),
            ("student", [item("hoodie", 2)], 800, 8400),
            ("regular", [item("hoodie", 3)], 0, 13200),
        ]
        for customer, items, discount, total in cases:
            with self.subTest(customer=customer, items=items):
                quote = self.service.quote(customer, items, "express")
                self.assertEqual(quote["fulfillment"], "express")
                self.assertEqual(quote["delivery_cents"], 1200)
                self.assertEqual(quote["discount_cents"], discount)
                self.assertEqual(quote["total_cents"], total)

    def test_fee_is_never_waived_at_standard_threshold(self):
        for quantity in (19, 20):
            with self.subTest(quantity=quantity):
                quote = self.service.quote("regular", [item("notebook", quantity)], "express")
                self.assertEqual(quote["delivery_cents"], 1200)
        standard = self.service.quote("regular", [item("hoodie", 3)], "delivery")
        express = self.service.quote("regular", [item("hoodie", 3)], "express")
        self.assertEqual((standard["delivery_cents"], standard["total_cents"]), (0, 12000))
        self.assertEqual((express["delivery_cents"], express["total_cents"]), (1200, 13200))

    def test_discount_threshold_and_rounding_exclude_express_fee(self):
        below = self.service.quote("student", [item("notebook", 9)], "express")
        at = self.service.quote("student", [item("notebook", 10)], "express")
        self.assertEqual((below["discount_cents"], below["total_cents"]), (0, 5700))
        self.assertEqual((at["discount_cents"], at["total_cents"]), (500, 5700))
        self.seed_catalog(5005)
        rounded = self.service.quote("student", [item("notebook", 1)], "express")
        self.assertEqual((rounded["discount_cents"], rounded["delivery_cents"], rounded["total_cents"]),
                         (501, 1200, 5704))

    def test_quote_does_not_save_reserve_or_use_id(self):
        before = self.service.catalog()
        quote = self.service.quote("regular", [item("notebook", 2)], "express")
        self.assertNotIn("order_id", quote)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.service.catalog(), before)
        order = self.service.place_order("regular", [item("notebook", 2)], "express")
        self.assertEqual(order["order_id"], "ORD-0001")
        self.assertEqual({key: order[key] for key in quote}, quote)

    def test_snapshot_survives_lookup_reopen_history_and_cancellation(self):
        order = self.service.place_order("student", [item("hoodie", 2)], "express")
        reopened = OrderService(self.path)
        self.assertEqual(reopened.get_order(order["order_id"]), order)
        self.assertEqual(reopened.list_orders(), [order])
        self.assertEqual(self.stock("hoodie"), 3)
        cancelled = reopened.cancel_order(order["order_id"])
        self.assertEqual(cancelled, {**order, "status": "cancelled"})
        self.assertEqual(self.stock("hoodie"), 5)
        saved = self.path.read_bytes()
        self.assertEqual(OrderService(self.path).cancel_order(order["order_id"]), cancelled)
        self.assertEqual(self.path.read_bytes(), saved)
        self.assertEqual(OrderService(self.path).list_orders(), [cancelled])
        next_order = self.service.place_order("regular", [item("mug", 1)])
        self.assertEqual(next_order["order_id"], "ORD-0002")

    def test_invalid_express_requests_preserve_saved_state(self):
        self.service.place_order("regular", [item("mug", 1)])
        before = self.path.read_bytes()
        requests = [
            ("staff", [item("mug", 1)], "express"),
            ("student", [item("mug", True)], "express"),
            ("regular", [item("bag", 3), item("bag", 2)], "express"),
            ("regular", [item("missing", 1)], "express"),
            ("regular", [], "express"),
            ("regular", [item("mug", 1)], "overnight"),
        ]
        for request in requests:
            for operation in (self.service.quote, self.service.place_order):
                with self.subTest(request=request, operation=operation.__name__):
                    with self.assertRaises(ValueError):
                        operation(*request)
                    self.assertEqual(self.path.read_bytes(), before)

    def test_old_schema_one_save_accepts_new_express_order(self):
        fixture = Path(__file__).with_name("fixtures") / "starter-schema1.json"
        shutil.copyfile(fixture, self.path)
        before = self.service.get_order("ORD-0001")
        self.assertEqual((before["fulfillment"], before["total_cents"]), ("delivery", 2100))
        quote = self.service.quote("regular", [item("notebook", 2)], "express")
        order = self.service.place_order("regular", [item("notebook", 2)], "express")
        self.assertEqual(order["order_id"], "ORD-0002")
        self.assertEqual({key: order[key] for key in quote}, quote)
        self.assertEqual(self.service.get_order("ORD-0001"), before)
        self.assertEqual(json.loads(self.path.read_text())["schema_version"], 1)

    def test_commands_quote_place_show_list_cancel_express(self):
        quote = self.command("quote", "--customer", "student", "--fulfillment", "express", "--item", "hoodie:2")
        self.assertEqual(quote.returncode, 0, quote.stderr)
        expected = json.loads(quote.stdout)
        self.assertEqual(expected["total_cents"], 8400)
        placed = self.command("place", "--customer", "student", "--fulfillment", "express", "--item", "hoodie:2")
        self.assertEqual(placed.returncode, 0, placed.stderr)
        order = json.loads(placed.stdout)
        self.assertEqual({key: order[key] for key in expected}, expected)
        shown = self.command("show", order["order_id"])
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(json.loads(shown.stdout), order)
        history = self.command("orders")
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertEqual(json.loads(history.stdout), [order])
        cancelled = self.command("cancel", order["order_id"])
        self.assertEqual(cancelled.returncode, 0, cancelled.stderr)
        self.assertEqual(json.loads(cancelled.stdout), {**order, "status": "cancelled"})

    def test_command_help_advertises_fee_and_choices(self):
        for operation in ("quote", "place"):
            with self.subTest(operation=operation):
                result = self.command(operation, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("pickup,delivery,express", result.stdout)
                self.assertIn("express is always CAD $12", result.stdout)

    def test_menu_quote_and_place_express(self):
        output = self.menu([
            "2", "student", "hoodie", "2", "", "express",
            "3", "student", "hoodie", "2", "", "express", "y", "0",
        ])
        self.assertGreaterEqual(output.count("Total: $84.00"), 2)
        self.assertIn("Delivery: $12.00", output)
        self.assertIn("Fulfillment: express", output)
        self.assertIn("ORD-0001 - placed", output)
        self.assertEqual(self.stock("hoodie"), 3)
        self.assertEqual(self.service.list_orders()[0]["total_cents"], 8400)

    def test_menu_prompt_advertises_express(self):
        answers = iter(["2", "", "notebook", "2", "", "express", "0"])
        prompts = []
        def respond(prompt):
            prompts.append(prompt)
            return next(answers)
        with patch("builtins.input", side_effect=respond), redirect_stdout(StringIO()):
            self.assertEqual(run_menu(self.service), 0)
        self.assertTrue(any("pickup/delivery/express" in prompt and "CAD $12" in prompt for prompt in prompts))

    def test_menu_declined_express_order_does_not_save(self):
        output = self.menu(["3", "", "notebook", "2", "", "express", "n", "0"])
        self.assertIn("Total: $22.00", output)
        self.assertFalse(self.path.exists())

    def test_menu_confirms_and_cancels_express(self):
        order = self.service.place_order("student", [item("hoodie", 2)], "express")
        output = self.menu(["6", order["order_id"], "y", "0"])
        self.assertIn("cancelled", output)
        self.assertIn("Total: $84.00", output)
        self.assertEqual(self.stock("hoodie"), 5)

    def test_real_interactive_entry_point_accepts_express(self):
        result = self.command(input_text="3\nstudent\nhoodie\n2\n\nexpress\ny\n4\n0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Delivery: $12.00", result.stdout)
        self.assertIn("Total: $84.00", result.stdout)
        self.assertIn("ORD-0001 - placed", result.stdout)
        self.assertEqual(self.stock("hoodie"), 3)
        self.assertEqual(self.service.list_orders()[0]["fulfillment"], "express")

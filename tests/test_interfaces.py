"""Checks through the public command and interactive menu entry points."""

import json
from tests.support import DeskTestCase, item


class InterfaceTests(DeskTestCase):
    def test_command_defaults_and_json(self):
        result = self.command("quote", "--item", "notebook:2")
        self.assertEqual(result.returncode, 0, result.stderr)
        quote = json.loads(result.stdout)
        self.assertEqual((quote["customer_type"], quote["fulfillment"], quote["total_cents"]),
                         ("regular", "pickup", 1000))
        self.assertFalse(self.path.exists())

    def test_command_rejects_invalid_quantity_and_fulfillment(self):
        for arguments in (("quote", "--item", "mug:no"), ("quote", "--item", "mug:1", "--fulfillment", "drone")):
            with self.subTest(arguments=arguments):
                result = self.command(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("error", result.stderr.lower())
                self.assertFalse(self.path.exists())

    def test_commands_place_and_cancel_immediately(self):
        placed = self.command("place", "--item", "mug:1")
        self.assertEqual(placed.returncode, 0, placed.stderr)
        order_id = json.loads(placed.stdout)["order_id"]
        shown = self.command("show", order_id)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(json.loads(shown.stdout)["status"], "placed")
        cancelled = self.command("cancel", order_id)
        self.assertEqual(cancelled.returncode, 0, cancelled.stderr)
        self.assertEqual(json.loads(cancelled.stdout)["status"], "cancelled")
        self.assertEqual(self.stock("mug"), 8)

    def test_menu_defaults_and_declined_order_do_not_save(self):
        output = self.menu(["3", "", "notebook", "2", "", "", "n", "0"])
        self.assertIn("Total: $10.00", output)
        self.assertIn("Order not placed.", output)
        self.assertFalse(self.path.exists())

    def test_menu_declined_cancellation_preserves_state(self):
        order = self.service.place_order("regular", [item("mug", 1)])
        before = self.path.read_bytes()
        output = self.menu(["6", order["order_id"], "n", "0"])
        self.assertIn("Cancellation abandoned.", output)
        self.assertEqual(self.path.read_bytes(), before)

    def test_menu_bad_quantity_can_be_reentered(self):
        output = self.menu(["2", "", "mug", "abc", "mug", "1", "", "", "0"])
        self.assertIn("Please enter a whole number.", output)
        self.assertIn("Total: $15.00", output)
        self.assertFalse(self.path.exists())

    def test_menu_service_error_returns_to_menu(self):
        output = self.menu(["2", "", "mug", "0", "", "", "1", "0"])
        self.assertIn("Error:", output)
        self.assertIn("Returning to the menu.", output)
        self.assertIn("Product ID", output)
        self.assertFalse(self.path.exists())

    def test_menu_end_of_input_and_interrupt_exit(self):
        for exception in (EOFError, KeyboardInterrupt):
            with self.subTest(exception=exception):
                self.assertIn("Goodbye.", self.menu([exception]))

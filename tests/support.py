"""Shared isolated state and process helpers for assignment tests."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from supplydesk.menu import run_menu
from supplydesk.service import OrderService


def item(product_id, quantity):
    return {"product_id": product_id, "quantity": quantity}


class DeskTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def stock(self, product_id):
        return next(
            product["stock"] for product in self.service.catalog()
            if product["product_id"] == product_id
        )

    def command(self, *arguments, input_text=""):
        return subprocess.run(
            [sys.executable, "-B", "-m", "supplydesk", "--data", str(self.path), *arguments],
            capture_output=True, text=True, input=input_text,
            cwd=Path(__file__).resolve().parents[1], timeout=10,
        )

    def menu(self, answers):
        output = StringIO()
        with patch("builtins.input", side_effect=answers), redirect_stdout(output):
            status = run_menu(self.service)
        self.assertEqual(status, 0)
        return output.getvalue()

    def seed_catalog(self, price, stock=99):
        # Controlled fixture for cent-rounding and quantity boundaries.
        state = self.service.store.load()
        state["catalog"][0]["unit_price_cents"] = price
        state["catalog"][0]["stock"] = stock
        self.service.store.save(state)

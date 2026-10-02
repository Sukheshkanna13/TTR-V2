from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from payments import utils


class InrToPaiseTests(SimpleTestCase):
    def test_known_float_trouble_amounts(self):
        # float(1.13) * 100 == 112.99999999999999, which truncated to 112
        for amount, paise in [
            ("1.13", 113), ("1.15", 115), ("2.01", 201), ("3358.88", 335888), ("0.29", 29),
        ]:
            self.assertEqual(utils.inr_to_paise(Decimal(amount)), paise, amount)

    def test_every_rupee_paise_amount_roundtrips(self):
        for paise in range(1, 300_000):
            self.assertEqual(utils.inr_to_paise(Decimal(paise) / 100), paise)

    def test_accepts_float_and_str(self):
        self.assertEqual(utils.inr_to_paise(1.15), 115)
        self.assertEqual(utils.inr_to_paise("1.15"), 115)

    def test_rounds_half_up_beyond_two_places(self):
        self.assertEqual(utils.inr_to_paise(Decimal("1.005")), 101)
        self.assertEqual(utils.inr_to_paise(Decimal("1.004")), 100)


class RazorpayAmountTests(SimpleTestCase):
    @patch("payments.utils.get_razorpay_client")
    def test_order_amount_is_exact_paise(self, get_client):
        client = MagicMock()
        client.order.create.return_value = {"id": "order_x", "amount": 113, "currency": "INR"}
        get_client.return_value = client

        utils.create_razorpay_order(Decimal("1.13"), "booking-1")

        self.assertEqual(client.order.create.call_args.kwargs["data"]["amount"], 113)

    @patch("payments.utils.get_razorpay_client")
    def test_partial_refund_amount_is_exact_paise(self, get_client):
        client = MagicMock()
        get_client.return_value = client

        utils.refund_razorpay_payment("pay_x", Decimal("1.13"))

        self.assertEqual(client.payment.refund.call_args.args[1]["amount"], 113)

from django.test import TestCase
from ..models import Payment, Registration


class SelfDeps(TestCase):
    def setUp(self):
        self.r = Registration.objects.create()
        self.r2 = Registration.objects.create()
        self.p1 = Payment.objects.create(amount=1, registration=self.r)
        self.p2 = Payment.objects.create(amount=10, registration=self.r)

    def test_init(self):
        self.r.refresh_from_db()
        self.assertEqual(self.r.total_amount, 11)

    def test_add_payment(self):
        Payment.objects.create(amount=200, registration=self.r)
        self.r.refresh_from_db()
        self.assertEqual(self.r.total_amount, 211)

    def test_change_payment(self):
        self.p1.amount = 3
        self.p1.save(update_fields=['amount'])
        self.r.refresh_from_db()
        self.assertEqual(self.r.total_amount, 13)

    def test_move_payment(self):
        self.p2.registration = self.r2
        self.p2.save(update_fields=['registration']) # currently fails w'o registration in fields
        self.r.refresh_from_db()
        self.r2.refresh_from_db()
        self.assertEqual(self.r.total_amount, 1)
        self.assertEqual(self.r2.total_amount, 10)


from computedfields.models import not_computed
class SelfDepsNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.r = Registration.objects.create()
            self.r2 = Registration.objects.create()
            self.p1 = Payment.objects.create(amount=1, registration=self.r)
            self.p2 = Payment.objects.create(amount=10, registration=self.r)

    def test_init(self):
        self.r.refresh_from_db()
        self.assertEqual(self.r.total_amount, 11)

    def test_add_payment(self):
        with not_computed(recover=True):
            Payment.objects.create(amount=200, registration=self.r)
        self.r.refresh_from_db()
        self.assertEqual(self.r.total_amount, 211)

    def test_change_payment(self):
        with not_computed(recover=True):
            self.p1.amount = 3
            self.p1.save(update_fields=['amount'])
        self.r.refresh_from_db()
        self.assertEqual(self.r.total_amount, 13)

    def test_move_payment(self):
        with not_computed(recover=True):
            self.p2.registration = self.r2
            self.p2.save(update_fields=['registration']) # currently fails w'o registration in fields
        self.r.refresh_from_db()
        self.r2.refresh_from_db()
        self.assertEqual(self.r.total_amount, 1)
        self.assertEqual(self.r2.total_amount, 10)
from django.test import TestCase
from ..models import NotPrecomputed, Precomputed
from computedfields.models import precomputed


class TestPrecomputedDecorator(TestCase):
    def setUp(self):
        self.np = NotPrecomputed.objects.create(name='xy')
        self.p = Precomputed.objects.create(name='xy')

    def test_init(self):
        self.np.refresh_from_db()
        self.p.refresh_from_db()

        self.assertEqual(self.np.upper, 'CHANGED')
        self.assertEqual(self.p.upper, 'CHANGED')

    def test_callsave(self):
        self.np.name = 'ab'
        self.np.save()

        self.p.name = 'ab'
        self.p.save()

        # np still contains old value
        self.assertEqual(self.np._temp, 'CHANGED')
        # p contains new value
        self.assertEqual(self.p._temp, 'AB')

        self.np.refresh_from_db()
        self.p.refresh_from_db()

        self.assertEqual(self.np.upper, 'CHANGED')
        self.assertEqual(self.p.upper, 'CHANGED')

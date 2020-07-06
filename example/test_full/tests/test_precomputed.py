from django.test import TestCase
from ..models import NotPrecomputed, Precomputed, PrecomputedEmptyArgs, PrecomputedNotSkip, PrecomputedSkip
from computedfields.models import precomputed


class TestPrecomputedDecorator(TestCase):
    def setUp(self):
        self.np = NotPrecomputed.objects.create(name='xy')
        self.p = Precomputed.objects.create(name='xy')
        self.pea = PrecomputedEmptyArgs.objects.create(name='xy')
        self.pns = PrecomputedNotSkip.objects.create(name='xy')
        self.ps = PrecomputedSkip.objects.create(name='xy')

    def test_init(self):
        self.np.refresh_from_db()
        self.p.refresh_from_db()
        self.pea.refresh_from_db()
        self.pns.refresh_from_db()
        self.ps.refresh_from_db()

        self.assertEqual(self.np.upper, 'CHANGED')
        self.assertEqual(self.p.upper, 'CHANGED')
        self.assertEqual(self.pea.upper, 'CHANGED')
        self.assertEqual(self.pns.upper, 'CHANGED')
        self.assertEqual(self.ps.upper, 'XY')  # no late re-calc anymore

    def test_callsave(self):
        self.np.name = 'ab'
        self.np.save()

        self.p.name = 'ab'
        self.p.save()

        self.pea.name = 'ab'
        self.pea.save()

        self.pns.name = 'ab'
        self.pns.save()

        self.ps.name = 'ab'
        self.ps.save()

        # np still contains old value
        self.assertEqual(self.np._temp, 'CHANGED')
        # p contains new value
        self.assertEqual(self.p._temp, 'AB')

        self.assertEqual(self.pea._temp, 'AB')
        self.assertEqual(self.pns._temp, 'AB')
        self.assertEqual(self.ps._temp, 'AB')

        self.np.refresh_from_db()
        self.p.refresh_from_db()
        self.pea.refresh_from_db()
        self.pns.refresh_from_db()
        self.ps.refresh_from_db()

        self.assertEqual(self.np.upper, 'CHANGED')
        self.assertEqual(self.p.upper, 'CHANGED')
        self.assertEqual(self.pea.upper, 'CHANGED')
        self.assertEqual(self.pns.upper, 'CHANGED')
        self.assertEqual(self.ps.upper, 'AB')   # again no late re-calc anymore

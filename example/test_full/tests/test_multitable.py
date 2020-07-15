from django.test import TestCase
from ..models import MtBase, MtDerived, MtRelated, MtDerived2, MtSubDerived


class TestMultiTable(TestCase):
    def setUp(self):
        self.r1 = MtRelated.objects.create(name='r1')
        self.r2 = MtRelated.objects.create(name='r2')
        self.d = MtDerived.objects.create(name='b', dname='d', rel_on_base=self.r1, rel_on_derived=self.r2)
        self.d_2 = MtDerived2.objects.create(name='b', z='z', rel_on_base=self.r1)
        self.s = MtSubDerived.objects.create(name='b', z='z', rel_on_base=self.r1, sub='I am sub!')

    def test_init(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper, 'B')
        self.assertEqual(self.d.upper_combined, 'B/D#r1:r2')
        self.assertEqual(self.d.pulled, '###B/D#r1:r2')
        self.d_2.refresh_from_db()
        self.assertEqual(self.d_2.pulled, 'D2:z')
        self.s.refresh_from_db()
        self.assertEqual(self.s.pulled, 'SUB pulled:I am sub!')

    def test_rename_base(self):
        self.d.name = 'bb'
        self.d.save(update_fields=['name'])
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper_combined, 'BB/D#r1:r2')
        self.assertEqual(self.d.pulled, '###BB/D#r1:r2')

    def test_update_from_r1(self):
        self.r1.name = 'rr1'
        self.r1.save(update_fields=['name'])
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper_combined, 'B/D#rr1:r2')
        self.assertEqual(self.d.pulled, '###B/D#rr1:r2')

    def test_update_from_r2(self):
        self.r2.name = 'rr2'
        self.r2.save(update_fields=['name'])
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper_combined, 'B/D#r1:rr2')
        self.assertEqual(self.d.pulled, '###B/D#r1:rr2')

    def test_update_z_on_d2(self):
        self.d_2.z = 'zzzzz'
        self.d_2.save(update_fields=['z'])
        self.d_2.refresh_from_db()
        self.assertEqual(self.d_2.pulled, 'D2:zzzzz')

    def test_change_sub(self):
        self.s.sub = 'does it work?'
        self.s.save(update_fields=['sub'])
        self.s.refresh_from_db()
        self.assertEqual(self.s.pulled, 'SUB pulled:does it work?')

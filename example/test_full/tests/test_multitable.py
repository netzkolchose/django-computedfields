from django.test import TestCase
from ..models import MtBase, MtDerived, MtRelated


class TestMultiTable(TestCase):
    def setUp(self):
        self.r1 = MtRelated.objects.create(name='r1')
        self.r2 = MtRelated.objects.create(name='r2')
        self.d = MtDerived.objects.create(name='b', dname='d', rel_on_base=self.r1, rel_on_derived=self.r2)

    def test_init(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper, 'B')
        self.assertEqual(self.d.upper_combined, 'B/D#r1:r2')

    def test_rename_base(self):
        self.d.name = 'bb'
        self.d.save(update_fields=['name'])
        self.assertEqual(self.d.upper_combined, 'BB/D#r1:r2')

    def test_update_from_r1(self):
        self.r1.name = 'rr1'
        print('pre')
        self.r1.save(update_fields=['name'])
        print('post')
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper_combined, 'B/D#rr1:r2')

    def test_update_from_r2(self):
        self.r2.name = 'rr2'
        print('pre')
        self.r2.save(update_fields=['name'])
        print('post')
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper_combined, 'B/D#r1:rr2')
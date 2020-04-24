from django.test import TestCase
from .. import models


class TestNoReverse(TestCase):
    def setUp(self):
        self.a = models.NoRelatedA.objects.create(name='a')
        self.b = models.NoRelatedB.objects.create(name='b', f_ba=self.a)
        self.c = models.NoRelatedC.objects.create(name='c')
        self.c.m_cb.add(self.b)
        self.d = models.NoRelatedD.objects.create(name='d', o_dc=self.c)

    def test_creation(self):
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd-a:a')
        self.assertEqual(self.a.comp, 'a#b#c#d-a:a')

    def test_insert_a_b(self):
        new_a = models.NoRelatedA.objects.create(name='A')
        new_b = models.NoRelatedB.objects.create(name='B', f_ba=new_a)
        self.c.m_cb.add(new_b)
        self.a.refresh_from_db()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd-a:a#A')
        self.assertEqual(self.a.comp, 'a#b#c#d-a:a#A')
        new_a.refresh_from_db()
        self.assertEqual(new_a.comp, 'A#B#c#d-a:a#A')

    def test_delete_c(self):
        self.c.delete()
        self.a.refresh_from_db()
        # d got deleted as well
        self.assertFalse(models.NoRelatedD.objects.all())
        self.assertEqual(self.a.comp, 'a#b')

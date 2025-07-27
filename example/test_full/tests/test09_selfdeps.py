from django.test import TestCase
from .. import models


class SelfDeps(TestCase):
    def setUp(self):
        self.a = models.SelfA.objects.create(name='a')
        self.b = models.SelfB.objects.create(name='b', a=self.a)
      
    def test_initial(self):
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.c1, 'c1a')
        self.assertEqual(self.a.c2, 'c2c1a')
        self.assertEqual(self.a.c3, 'c3c2c1a')
        self.assertEqual(self.a.c4, 'c4c1ac3c2c1a')
        self.assertEqual(self.b.c1, 'C1b')
        self.assertEqual(self.b.c2, 'C2C1bc4c1ac3c2c1a')

    def test_change_name_a_full_save(self):
        self.a.name = 'A'
        self.a.save()
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.c1, 'c1A')
        self.assertEqual(self.a.c2, 'c2c1A')
        self.assertEqual(self.a.c3, 'c3c2c1A')
        self.assertEqual(self.a.c4, 'c4c1Ac3c2c1A')
        self.assertEqual(self.b.c1, 'C1b')
        self.assertEqual(self.b.c2, 'C2C1bc4c1Ac3c2c1A')

    def test_change_name_a_partial_save(self):
        self.a.name = 'X'
        self.a.save(update_fields=['name'])
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.c1, 'c1X')
        self.assertEqual(self.a.c2, 'c2c1X')
        self.assertEqual(self.a.c3, 'c3c2c1X')
        self.assertEqual(self.a.c4, 'c4c1Xc3c2c1X')
        self.assertEqual(self.b.c1, 'C1b')
        self.assertEqual(self.b.c2, 'C2C1bc4c1Xc3c2c1X')


from computedfields.models import not_computed
class SelfDepsNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.a = models.SelfA.objects.create(name='a')
            self.b = models.SelfB.objects.create(name='b', a=self.a)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
      
    def test_initial(self):
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.c1, 'c1a')
        self.assertEqual(self.a.c2, 'c2c1a')
        self.assertEqual(self.a.c3, 'c3c2c1a')
        self.assertEqual(self.a.c4, 'c4c1ac3c2c1a')
        self.assertEqual(self.b.c1, 'C1b')
        self.assertEqual(self.b.c2, 'C2C1bc4c1ac3c2c1a')

    def test_change_name_a_full_save(self):
        with not_computed(recover=True):
            self.a.name = 'A'
            self.a.save()
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.c1, 'c1A')
        self.assertEqual(self.a.c2, 'c2c1A')
        self.assertEqual(self.a.c3, 'c3c2c1A')
        self.assertEqual(self.a.c4, 'c4c1Ac3c2c1A')
        self.assertEqual(self.b.c1, 'C1b')
        self.assertEqual(self.b.c2, 'C2C1bc4c1Ac3c2c1A')

    def test_change_name_a_partial_save(self):
        with not_computed(recover=True):
            self.a.name = 'X'
            self.a.save(update_fields=['name'])
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.c1, 'c1X')
        self.assertEqual(self.a.c2, 'c2c1X')
        self.assertEqual(self.a.c3, 'c3c2c1X')
        self.assertEqual(self.a.c4, 'c4c1Xc3c2c1X')
        self.assertEqual(self.b.c1, 'C1b')
        self.assertEqual(self.b.c2, 'C2C1bc4c1Xc3c2c1X')

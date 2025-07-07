from django.test import TestCase
from .. import models


class DefaultOnCreate(TestCase):
    def setUp(self):
        self.p1 = models.DefaultParent.objects.create(name='P1')
        self.p2 = models.DefaultParent.objects.create(name='P2')
        self.c1 = models.DefaultChild.objects.create(name='C1', parent=self.p1)
        self.c11 = models.DefaultChild.objects.create(name='C11', parent=self.p1)
        self.t1 = models.DefaultToy.objects.create(name='T1')
        self.t2 = models.DefaultToy.objects.create(name='T2')
        self.c1.toys.add(self.t1)
      
    def test_created_fk(self):
        self.p1.refresh_from_db()
        self.p2.refresh_from_db()
        self.assertEqual(self.p1.children_names, 'C1,C11')
        self.assertEqual(self.p2.children_names, 'NOTHING')

    def test_created_m2m(self):
        self.c1.refresh_from_db()
        self.c11.refresh_from_db()
        self.assertEqual(self.c1.toy_names, 'T1')
        self.assertEqual(self.c11.toy_names, 'NO TOYS, SAD')

    def test_created_m2m_back(self):
        self.t1.refresh_from_db()
        self.t2.refresh_from_db()
        self.assertEqual(self.t1.children_names, 'C1')
        self.assertEqual(self.t2.children_names, 'no one wants to play with this')

    def test_copyclone_fk(self):
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.children_names, 'C1,C11')
        self.p1.pk = None
        self.p1.save()
        self.assertEqual(self.p1.children_names, 'NOTHING')

    def test_copyclone_m2m(self):
        self.c1.refresh_from_db()
        self.assertEqual(self.c1.toy_names, 'T1')
        self.c1.pk = None
        self.c1.save()
        self.assertEqual(list(self.c1.toys.all()), [])
        self.assertEqual(self.c1.toy_names, 'NO TOYS, SAD')

    def test_copyclone_m2m_back(self):
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.children_names, 'C1')
        self.t1.pk = None
        self.t1.save()
        self.assertEqual(list(self.t1.children.all()), [])
        self.assertEqual(self.t1.children_names, 'no one wants to play with this')

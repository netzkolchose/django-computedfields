from django.test import TestCase
from .. import models


# FIXME: to be removed with future version
class TestOldDepends(TestCase):
    def setUp(self):
        self.p = models.OldDependsParent.objects.create(name='p')
        self.c1 = models.OldDependsChild.objects.create(name='c1', parent=self.p)
        self.c2 = models.OldDependsChild.objects.create(name='c2', parent=self.p)
        self.c3 = models.OldDependsChild.objects.create(name='c3', parent=self.p)

    def test_creation(self):
        self.p.refresh_from_db()
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()

        self.assertEqual(self.p.upper, 'P')
        self.assertEqual(self.p.proxy, 'P3')
        self.assertEqual(self.c1.parent_and_self, 'Pc1')
        self.assertEqual(self.c2.parent_and_self, 'Pc2')
        self.assertEqual(self.c3.parent_and_self, 'Pc3')

    def test_change_parent_name(self):
        self.p.name = 'x'
        self.p.save()
        self.p.refresh_from_db()
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()

        self.assertEqual(self.p.upper, 'X')
        self.assertEqual(self.p.proxy, 'X3')
        self.assertEqual(self.c1.parent_and_self, 'Xc1')
        self.assertEqual(self.c2.parent_and_self, 'Xc2')
        self.assertEqual(self.c3.parent_and_self, 'Xc3')

    def test_change_child(self):
        self.c1.name = 'C1'
        self.c1.save()
        self.p.refresh_from_db()
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()

        self.assertEqual(self.p.upper, 'P')
        self.assertEqual(self.p.proxy, 'P3')
        self.assertEqual(self.c1.parent_and_self, 'PC1')
        self.assertEqual(self.c2.parent_and_self, 'Pc2')
        self.assertEqual(self.c3.parent_and_self, 'Pc3')

    def add_child(self):
        self.c4 = models.OldDependsChild.objects.create(name='c4', parent=self.p)
        self.p.refresh_from_db()
        self.assertEqual(self.p.proxy, 'P4')
        self.assertEqual(self.c4.parent_and_self, 'Pc4')

    def remove_child(self):
        self.c3.delete()
        self.p.refresh_from_db()
        self.assertEqual(self.p.proxy, 'P2')

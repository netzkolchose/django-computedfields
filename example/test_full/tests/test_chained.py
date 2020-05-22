from django.test import TestCase
from .. import models


class TestChained(TestCase):
    def setUp(self):
        self.a = models.ChainA.objects.create(name='a')
        self.b = models.ChainB.objects.create(a=self.a)
        self.c = models.ChainC.objects.create(b=self.b)

    def test_init(self):
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.assertEqual(self.b.comp, 'a')
        self.assertEqual(self.c.comp, 'a')

    def test_change_a_name(self):
        self.a.name = 'z'
        self.a.save(update_fields=['name'])
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.assertEqual(self.b.comp, 'z')
        self.assertEqual(self.c.comp, 'z')

    def test_new_a(self):
        new_a = models.ChainA.objects.create(name='x')
        self.b.a = new_a
        # this works
        #self.b.save()
        # also works
        #self.b.save(update_fields=['a', 'comp'])
        # expands automatically to 'comp' with commit 203b9bc
        self.b.save(update_fields=['a'])
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.assertEqual(self.b.comp, 'x')
        self.assertEqual(self.c.comp, 'x')


class TestExpand(TestCase):
    def setUp(self):
        self.a = models.ExpandA.objects.create(name='a')
        self.b = models.ExpandB.objects.create(a=self.a)
        self.c = models.ExpandC.objects.create(b=self.b)
        self.d = models.ExpandD.objects.create(c=self.c)

    def test_init(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'a')

    def test_change_a_name(self):
        self.a.name = 'z'
        self.a.save(update_fields=['name'])
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'z')

    def test_new_a(self):
        new_a = models.ExpandA.objects.create(name='x')
        self.b.a = new_a
        self.b.save(update_fields=['a'])
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'x')

    def test_new_b(self):
        new_a = models.ExpandA.objects.create(name='x')
        new_b = models.ExpandB.objects.create(a=new_a)
        self.c.b = new_b
        self.c.save(update_fields=['b'])
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'x')

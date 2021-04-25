from django.test import TestCase
from ..models import Parent, Child, Subchild


class ObjectCloning(TestCase):
    def setUp(self):
        self.p = Parent.objects.create()
        self.c = Child.objects.create(parent=self.p)
        self.s = Subchild.objects.create(subparent=self.c)

    def test_init(self):
        self.p.refresh_from_db()
        self.assertEqual(self.p.children_count, 1)
        self.assertEqual(self.p.subchildren_count, 1)
        self.c.refresh_from_db()
        self.assertEqual(self.c.subchildren_count, 1)

    def test_copyclone_c(self):
        c2 = self.c
        c2.pk = None
        c2.save()

        # now self.c == c2, thus reload c from db
        c = Child.objects.get(pk=1)

        self.p.refresh_from_db()
        self.assertEqual(self.p.children_count, 2)
        self.assertEqual(self.p.subchildren_count, 1)

        self.assertEqual(c.subchildren_count, 1)
        self.assertEqual(c2.subchildren_count, 0)

    def test_copyclone_s(self):
        s2 = self.s
        s2.pk = None
        s2.save()

        s = Subchild.objects.get(pk=1)

        self.p.refresh_from_db()
        self.assertEqual(self.p.children_count, 1)
        self.assertEqual(self.p.subchildren_count, 2)
        self.c.refresh_from_db()
        self.assertEqual(self.c.subchildren_count, 2)

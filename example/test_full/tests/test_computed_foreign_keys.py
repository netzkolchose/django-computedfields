from django.test import TestCase
from .. import models


class ComputedForeignKeys(TestCase):
    def setUp(self):
        self.names = ['a', 'b', 'c', 'd', 'e', 'f']
        for name in self.names:
            models.CFKCatalogue1.objects.create(name='c1%s' % name)
            models.CFKCatalogue2.objects.create(name='c2%s' % name)

    def test_basic(self):
        for c1 in models.CFKCatalogue1.objects.all():
            for c2 in models.CFKCatalogue2.objects.all():
                m = models.CFKData.objects.create(c1name=c1.name, c2name=c2.name)
                self.assertEqual(m.c1, c1)
                self.assertEqual(m.c2, c2)
                for value in self.names:
                    v = models.CFKRelatedData.objects.create(parent=m, value=value)
                    self.assertEqual(v.c1, c1)
                    self.assertEqual(v.c2, c2)

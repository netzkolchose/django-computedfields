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

    def test_cascade_delete(self):
        for c1 in models.CFKCatalogue1.objects.all():
            for c2 in models.CFKCatalogue2.objects.all():
                m = models.CFKData.objects.create(c1name=c1.name, c2name=c2.name)
                for value in self.names:
                    models.CFKRelatedData.objects.create(parent=m, value=value)
        self.assertGreater(models.CFKData.objects.all().count(), 0)
        self.assertGreater(models.CFKRelatedData.objects.all().count(), 0)

        # on deleting all CFKCatalogue1 instances
        # CFKData and CFKRelatedData should drop to zero count
        # due to cascade deletion
        for c1 in models.CFKCatalogue1.objects.all():
            c1.delete()
        self.assertEqual(models.CFKData.objects.all().count(), 0)
        self.assertEqual(models.CFKRelatedData.objects.all().count(), 0)

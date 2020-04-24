from django.test import TestCase
from .. import models


class TestMultipleComp(TestCase):
    def setUp(self):
        self.source = models.MultipleCompSource.objects.create(name='Source')
        self.ref = models.MultipleCompRef.objects.create(a=self.source, b=self.source)

    def test_creation(self):
        self.source.refresh_from_db()
        self.ref.refresh_from_db()
        self.assertEqual(self.source.upper, 'SOURCE')
        self.assertEqual(self.source.lower, 'source')
        self.assertEqual(self.ref.upper_a, 'SOURCE')
        self.assertEqual(self.ref.lower_a, 'source')
        self.assertEqual(self.ref.upper_b, 'SOURCE')
        self.assertEqual(self.ref.lower_b, 'source')

    def test_change_key(self):
        source_b = models.MultipleCompSource.objects.create(name='SourceB')
        self.ref.b = source_b
        self.ref.save()
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.upper_a, 'SOURCE')
        self.assertEqual(self.ref.lower_a, 'source')
        self.assertEqual(self.ref.upper_b, 'SOURCEB')
        self.assertEqual(self.ref.lower_b, 'sourceb')

    def test_change_text(self):
        self.source.name = 'SourceChanged'
        self.source.save()
        self.source.refresh_from_db()
        self.ref.refresh_from_db()
        self.assertEqual(self.source.upper, 'SOURCECHANGED')
        self.assertEqual(self.source.lower, 'sourcechanged')
        self.assertEqual(self.ref.upper_a, 'SOURCECHANGED')
        self.assertEqual(self.ref.lower_a, 'sourcechanged')
        self.assertEqual(self.ref.upper_b, 'SOURCECHANGED')
        self.assertEqual(self.ref.lower_b, 'sourcechanged')

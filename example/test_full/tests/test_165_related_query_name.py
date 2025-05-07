from django.test import TestCase
from ..models import RNBar, RNFoo


class RelatedName(TestCase):
    def setUp(self):
        self.foo = RNFoo.objects.create()
        self.bar = RNBar.objects.create(b='a', foo=self.foo)

    def test_init(self):
        self.foo.refresh_from_db()
        self.assertEqual(self.foo.comp, 'a')
    
    def test_add_second(self):
        bar = RNBar.objects.create(b='b', foo=self.foo)
        self.foo.refresh_from_db()
        self.assertEqual(self.foo.comp, 'ab')

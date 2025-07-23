from django.test import TestCase
from ..models import RNM2MBar, RNM2MFoo


class RelatedNameM2M(TestCase):
    def setUp(self):
        self.foo = RNM2MFoo.objects.create()
        self.bar = RNM2MBar.objects.create(b='a')
        self.bar.foos.add(self.foo)

    def test_init(self):
        self.foo.refresh_from_db()
        self.assertEqual(self.foo.comp, 'a')
    
    def test_add_second(self):
        bar = RNM2MBar.objects.create(b='b')
        bar.foos.add(self.foo)
        self.foo.refresh_from_db()
        self.assertEqual(self.foo.comp, 'ab')


from computedfields.models import not_computed
class RelatedNameM2MNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.foo = RNM2MFoo.objects.create()
            self.bar = RNM2MBar.objects.create(b='a')
            self.bar.foos.add(self.foo)

    def test_init(self):
        self.foo.refresh_from_db()
        self.assertEqual(self.foo.comp, 'a')
    
    def test_add_second(self):
        with not_computed(recover=True):
            bar = RNM2MBar.objects.create(b='b')
        bar.foos.add(self.foo)
        self.foo.refresh_from_db()
        self.assertEqual(self.foo.comp, 'ab')

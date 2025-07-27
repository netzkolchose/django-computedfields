from django.test import TestCase
from ..models import Ha, HaProxy, HaTag, HaTagProxy


class TestProxyModels(TestCase):
    def setUp(self):
        self.tags = [HaTag.objects.create(name=str(i)) for i in range(10)]
        self.ha1 = Ha.objects.create()
        self.ha1proxy = HaProxy.objects.get(pk=self.ha1.pk)
        self.ha1proxy.tags.set(self.tags)
        self.ha2 = Ha.objects.create()
        self.ha2proxy = HaProxy.objects.get(pk=self.ha2.pk)

    def test_initial(self):
        self.ha1.refresh_from_db()
        self.ha1proxy.refresh_from_db()
        self.assertEqual(self.ha1.all_tags, '0,1,2,3,4,5,6,7,8,9')
        self.assertEqual(self.ha1proxy.all_tags, self.ha1.all_tags)

    def test_move_on_proxies(self):
        self.ha1proxy.tags.clear()
        tagproxies = HaTagProxy.objects.all()
        self.ha2proxy.tags.set(tagproxies)
        # ha1 should contain nothing
        self.ha1.refresh_from_db()
        self.ha1proxy.refresh_from_db()
        self.assertEqual(self.ha1.all_tags, '')
        self.assertEqual(self.ha1proxy.all_tags, self.ha1.all_tags)
        # ha2 should contain all tags now
        self.ha2.refresh_from_db()
        self.ha2proxy.refresh_from_db()
        self.assertEqual(self.ha2.all_tags, '0,1,2,3,4,5,6,7,8,9')
        self.assertEqual(self.ha2proxy.all_tags, self.ha2.all_tags)


from computedfields.models import not_computed
class TestProxyModelsNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.tags = [HaTag.objects.create(name=str(i)) for i in range(10)]
            self.ha1 = Ha.objects.create()
            self.ha1proxy = HaProxy.objects.get(pk=self.ha1.pk)
            self.ha1proxy.tags.set(self.tags)
            self.ha2 = Ha.objects.create()
            self.ha2proxy = HaProxy.objects.get(pk=self.ha2.pk)
        self.ha1.refresh_from_db()
        self.ha1proxy.refresh_from_db()
        self.ha2.refresh_from_db()
        self.ha2proxy.refresh_from_db()

    def test_initial(self):
        self.ha1.refresh_from_db()
        self.ha1proxy.refresh_from_db()
        self.assertEqual(self.ha1.all_tags, '0,1,2,3,4,5,6,7,8,9')
        self.assertEqual(self.ha1proxy.all_tags, self.ha1.all_tags)

    def test_move_on_proxies(self):
        with not_computed(recover=True):
            self.ha1proxy.tags.clear()
            tagproxies = HaTagProxy.objects.all()
            self.ha2proxy.tags.set(tagproxies)
        # ha1 should contain nothing
        self.ha1.refresh_from_db()
        self.ha1proxy.refresh_from_db()
        self.assertEqual(self.ha1.all_tags, '')
        self.assertEqual(self.ha1proxy.all_tags, self.ha1.all_tags)
        # ha2 should contain all tags now
        self.ha2.refresh_from_db()
        self.ha2proxy.refresh_from_db()
        self.assertEqual(self.ha2.all_tags, '0,1,2,3,4,5,6,7,8,9')
        self.assertEqual(self.ha2proxy.all_tags, self.ha2.all_tags)

from django.test import TestCase
from ..models import UAppartment, UPerson
from computedfields.models import update_dependent
from django.db.transaction import atomic
from time import time


PERSONS = 100

class UnionRelatedPerf(TestCase):
    def setUp(self):
        with atomic():
            self.a = UAppartment.objects.create(street='Abyss Road', number=5)
            self.p = UPerson.objects.create(appartment=self.a)
            for _ in range(PERSONS):
                UPerson.objects.create(parent=self.p, at_parent=True)
    
    def test_rename_appartment_perf(self):
        start = time()
        with atomic():
            self.a.street = 'Hellway'
            self.a.number = 666
            self.a.save()
        plain = time() - start
        self.assertEqual(UPerson.objects.filter(address='App #666, Hellway').count(), PERSONS+1)
        
        # patch select_related
        UPerson._meta.get_field('address')._computed['select_related'] = ['appartment', 'parent__appartment']
        UPerson._meta.get_field('address')._computed['prefetch_related'] = []
        start = time()
        with atomic():
            self.a.street = 'Heaven Lane'
            self.a.number = 777
            self.a.save()
        sr = time() - start
        self.assertEqual(UPerson.objects.filter(address='App #777, Heaven Lane').count(), PERSONS+1)

        # patch prefetch_related
        UPerson._meta.get_field('address')._computed['select_related'] = []
        UPerson._meta.get_field('address')._computed['prefetch_related'] = ['appartment', 'parent__appartment']
        start = time()
        with atomic():
            self.a.street = 'Celestial Border'
            self.a.number = 888
            self.a.save()
        pr = time() - start
        self.assertEqual(UPerson.objects.filter(address='App #888, Celestial Border').count(), PERSONS+1)

        self.assertLess(sr, plain)
        self.assertLess(pr, plain)

        UPerson._meta.get_field('address')._computed['select_related'] = []
        UPerson._meta.get_field('address')._computed['prefetch_related'] = []





from computedfields.models import not_computed
class UnionRelatedPerfNC(TestCase):
    def setUp(self):
        with atomic() and not_computed(recover=True):
            self.a = UAppartment.objects.create(street='Abyss Road', number=5)
            self.p = UPerson.objects.create(appartment=self.a)
            for _ in range(PERSONS):
                UPerson.objects.create(parent=self.p, at_parent=True)
    
    def test_rename_appartment_perf(self):
        start = time()
        with atomic() and not_computed(recover=True):
            self.a.street = 'Hellway'
            self.a.number = 666
            self.a.save()
        plain = time() - start
        self.assertEqual(UPerson.objects.filter(address='App #666, Hellway').count(), PERSONS+1)
        
        # patch select_related
        UPerson._meta.get_field('address')._computed['select_related'] = ['appartment', 'parent__appartment']
        UPerson._meta.get_field('address')._computed['prefetch_related'] = []
        start = time()
        with atomic() and not_computed(recover=True):
            self.a.street = 'Heaven Lane'
            self.a.number = 777
            self.a.save()
        sr = time() - start
        self.assertEqual(UPerson.objects.filter(address='App #777, Heaven Lane').count(), PERSONS+1)

        # patch prefetch_related
        UPerson._meta.get_field('address')._computed['select_related'] = []
        UPerson._meta.get_field('address')._computed['prefetch_related'] = ['appartment', 'parent__appartment']
        start = time()
        with atomic() and not_computed(recover=True):
            self.a.street = 'Celestial Border'
            self.a.number = 888
            self.a.save()
        pr = time() - start
        self.assertEqual(UPerson.objects.filter(address='App #888, Celestial Border').count(), PERSONS+1)

        self.assertLess(sr, plain)
        self.assertLess(pr, plain)

        UPerson._meta.get_field('address')._computed['select_related'] = []
        UPerson._meta.get_field('address')._computed['prefetch_related'] = []

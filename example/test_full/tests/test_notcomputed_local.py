from django.test import TestCase
from exampleapp.models import SelfRef
from computedfields.models import not_computed, update_dependent
from time import time
from django.db.transaction import atomic
from fast_update.query import fast_update


def fms(v):
    """
    Format seconds value to milliseconds.
    """
    v = int(v * 1000)
    return '% 5d' % v + ' ms'


# manually resolved c5 computed value
def c5(name, xy):
    return 'c5' + 'c2' + name.upper() + 'c4' + 'c3' + name.upper() + 'c6' + str(xy)


class NotComputedLocal(TestCase):
    def create_looped(self):
        start = time()
        for i in range(100):
            SelfRef.objects.create(name=f'x{i}', xy=i)
        return time() - start
    
    def create_notcomputed(self):
        start = time()
        objects = []
        with not_computed():
            for i in range(100):
                objects.append(SelfRef.objects.create(name=f'x{i}', xy=i))
        update_dependent(SelfRef.objects.filter(pk__in=[o.pk for o in objects]))
        return time() - start
    
    def create_notcomputed_recover(self):
        start = time()
        with not_computed(recover=True):
            for i in range(100):
                SelfRef.objects.create(name=f'x{i}', xy=i)
        return time() - start
    
    def create_bulk(self, n=100):
        start = time()
        objects = []
        for i in range(n):
            objects.append(SelfRef(name=f'x{i}', xy=i))
        SelfRef.objects.bulk_create(objects)
        update_dependent(SelfRef.objects.filter(pk__in=[o.pk for o in objects]))
        return time() - start

    def test_compare_create(self):
        with atomic():
            looped = self.create_looped()
            notcomputed = self.create_notcomputed()
            notcomputed_recover = self.create_notcomputed_recover()
            bulk = self.create_bulk()
        
        print(
            f'\nCREATE\n'
            f'looped           : {fms(looped)}\n'
            f'not_computed     : {fms(notcomputed)}\n'
            f'not_computed_rec : {fms(notcomputed_recover)}\n'
            f'bulk             : {fms(bulk)}'
        )

        # all values should be in sync
        for sf in SelfRef.objects.all().order_by('pk'):
            self.assertEqual(sf.c5, c5(sf.name, sf.xy))

    def update_looped(self, sfs):
        start = time()
        for sf in sfs:
            sf.name += 'z'
            sf.save(update_fields=['name'])
        return time() - start
    
    def update_notcomputed(self, sfs):
        start = time()
        with not_computed():
            for sf in sfs:
                sf.name += 'z'
                sf.save(update_fields=['name'])
        update_dependent(SelfRef.objects.filter(pk__in=[o.pk for o in sfs]))
        return time() - start
    
    def update_notcomputed_recover(self, sfs):
        start = time()
        with not_computed(recover=True):
            for sf in sfs:
                sf.name += 'z'
                sf.save(update_fields=['name'])
        return time() - start
    
    def update_bulk(self, sfs):
        start = time()
        for sf in sfs:
            sf.name += 'z'
        fast_update(SelfRef.objects.all(), sfs, ['name'], None)
        update_dependent(SelfRef.objects.filter(pk__in=[o.pk for o in sfs]))
        return time() - start

    def test_compare_update(self):
        with atomic():
            self.create_bulk(400)
        with atomic():
            looped = self.update_looped(SelfRef.objects.all()[:100])
            notcomputed = self.update_notcomputed(SelfRef.objects.all()[100:200])
            notcomputed_recover = self.update_notcomputed_recover(SelfRef.objects.all()[200:300])
            bulk = self.update_bulk(SelfRef.objects.all()[300:400])
        
        print(
            f'\nUPDATE\n'
            f'looped           : {fms(looped)}\n'
            f'not_computed     : {fms(notcomputed)}\n'
            f'not_computed_rec : {fms(notcomputed_recover)}\n'
            f'bulk             : {fms(bulk)}'
        )

        # all values should be in sync
        for sf in SelfRef.objects.all().order_by('pk'):
            self.assertEqual(sf.c5, c5(sf.name, sf.xy))
        
        start = time()
        with not_computed(recover=True):
            for sf in SelfRef.objects.all().order_by('pk'):
                sf.delete()
        print(time()-start)

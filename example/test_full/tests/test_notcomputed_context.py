from django.test import TestCase
from ..models import Product, Shelf
from computedfields.models import no_computed, update_dependent
from time import time
from django.db.transaction import atomic


def fms(v):
    """
    Format seconds value to milliseconds.
    """
    v = int(v * 1000)
    return '% 5d' % v + ' ms'


class NoComputedContext(TestCase):
    def create_normal(self):
        start = time()
        for i in range(10):
            shelf = Shelf.objects.create(name=f's{i}')
            for j in range(10):
                Product.objects.create(name=f'p{j}', shelf=shelf)
        return time() - start
    
    def create_nocomputed(self):
        start = time()
        shelf_pks = []
        with no_computed():
            for i in range(10):
                shelf = Shelf.objects.create(name=f's{i}')
                shelf_pks.append(shelf.pk)
                for j in range(10):
                    Product.objects.create(name=f'p{j}', shelf=shelf)
        # manually resync
        update_dependent(Shelf.objects.filter(pk__in=shelf_pks))
        return time() - start
    
    def create_bulk(self):
        start = time()
        shelfs = []
        products = []
        for i in range(10):
            shelfs.append(Shelf(name=f's{i}', product_names='sentinel'))
        Shelf.objects.bulk_create(shelfs)
        for shelf in Shelf.objects.filter(product_names='sentinel').order_by('pk'):
            for j in range(10):
                products.append(Product(name=f'p{j}', shelf=shelf))
        Product.objects.bulk_create(products)
        update_dependent(Shelf.objects.filter(pk__in=set(p.shelf_id for p in products)))
        return time()-start

    def test_compare_create(self):
        with atomic():
            normal = self.create_normal()
            nocomputed = self.create_nocomputed()
            bulk = self.create_bulk()

        # resync yields same result
        for i in range(10):
            s_normal, s_nocomputed, s_bulk = list(Shelf.objects.filter(name=f's{i}').order_by('pk'))
            self.assertEqual(s_normal.product_names, s_nocomputed.product_names)
            self.assertEqual(s_normal.product_names, s_bulk.product_names)
        
        print(
            f'\nCREATE\n'
            f'normal     : {fms(normal)}\n'
            f'nocomputed : {fms(nocomputed)}\n'
            f'bulk       : {fms(bulk)}'
        )

        # no_computed is magnitudes faster than normal (at least 3x)
        self.assertGreater(normal, nocomputed * 3)
        # but cannot beat bulk
        self.assertGreater(nocomputed, bulk)

    def update_normal(self, products):
        start = time()
        for i, p in enumerate(products):
            p.name = f'p{i+1}'
            p.save(update_fields=['name'])
        return time() - start
    
    def update_nocomputed(self, products):
        start = time()
        with no_computed():
            for i, p in enumerate(products):
                p.name = f'p{i+1}'
                p.save(update_fields=['name'])
        update_dependent(Shelf.objects.filter(pk__in=set(p.shelf_id for p in products)))
        return time() - start
    
    def update_bulk(self, products):
        start = time()
        for i, p in enumerate(products):
            p.name = f'p{i+1}'
        Product.objects.fast_update(products, ['name'])  # alot faster than bulk_update
        update_dependent(Shelf.objects.filter(pk__in=set(p.shelf_id for p in products)))
        return time() - start

    def test_compare_update(self):
        with atomic():
            self.create_normal()
            self.create_nocomputed()
            self.create_bulk()

        normals = []
        nocomputeds = []
        bulks = []
        for i in range(10):
            products = list(Product.objects.filter(name=f'p{i}').order_by('pk'))
            normals.extend(products[0:10])
            nocomputeds.extend(products[10:20])
            bulks.extend(products[20:30])
        
        self.assertEqual(len(normals), 100)
        self.assertEqual(len(nocomputeds), 100)
        self.assertEqual(len(bulks), 100)
        
        with atomic():
            normal = self.update_normal(normals)
            nocomputed = self.update_nocomputed(nocomputeds)
            bulk = self.update_bulk(bulks)

        # resync yields same result
        for i in range(10):
            s_normal, s_nocomputed, s_bulk = list(Shelf.objects.filter(name=f's{i}').order_by('pk'))
            self.assertEqual(s_normal.product_names, s_nocomputed.product_names)
            self.assertEqual(s_normal.product_names, s_bulk.product_names)

        print(
            f'\nUPDATE\n'
            f'normal     : {fms(normal)}\n'
            f'nocomputed : {fms(nocomputed)}\n'
            f'bulk       : {fms(bulk)}'
        )

        # no_computed is magnitudes faster than normal (at least 3x)
        self.assertGreater(normal, nocomputed * 3)
        # but cannot beat bulk
        self.assertGreater(nocomputed, bulk)

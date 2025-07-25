from django.test import TestCase
from ..models import Book, Shelf
from computedfields.models import not_computed, update_dependent
from time import time
from django.db.transaction import atomic


def fms(v):
    """
    Format seconds value to milliseconds.
    """
    v = int(v * 1000)
    return '% 5d' % v + ' ms'


def avg(values):
    return sum(values) / len(values)


class NotComputedPerf(TestCase):
    def create_looped(self):
        start = time()
        for i in range(10):
            shelf = Shelf.objects.create(name=f's{i}')
            for j in range(10):
                Book.objects.create(name=f'p{j}', shelf=shelf)
        return time() - start
    
    def create_notcomputed(self):
        start = time()
        shelf_pks = []
        with not_computed():
            for i in range(10):
                shelf = Shelf.objects.create(name=f's{i}')
                shelf_pks.append(shelf.pk)
                for j in range(10):
                    Book.objects.create(name=f'p{j}', shelf=shelf)
        # handcrafted resync:
        # There is only one dependent CF - Shelf.book_names via Book.shelf fk relation.
        # Therefore we stored the shelf pks and can do a slightly optimized resync here.
        # Without good knowledge about the dependency tree an easier but more costly way
        # would be to just store all created object pks above and call update_dependent
        # on book and shelf pks separately.
        update_dependent(Shelf.objects.filter(pk__in=shelf_pks))
        return time() - start
    
    def create_notcomputed_recover(self):
        start = time()
        with not_computed(recover=True):
            for i in range(10):
                shelf = Shelf.objects.create(name=f's{i}')
                for j in range(10):
                    Book.objects.create(name=f'p{j}', shelf=shelf)
        return time() - start
    
    def create_bulk(self):
        start = time()
        shelves = []
        books = []
        # NOTE: the sentinel trick is needed for mysql, as it does not populate pk in bulk_create
        for i in range(10):
            shelves.append(Shelf(name=f's{i}', book_names='sentinel'))
        Shelf.objects.bulk_create(shelves)
        shelves = []
        for shelf in Shelf.objects.filter(book_names='sentinel').order_by('pk'):
            shelves.append(shelf.pk)
            for j in range(10):
                books.append(Book(name=f'p{j}', shelf=shelf))
        Book.objects.bulk_create(books)
        # resync
        update_dependent(Shelf.objects.filter(pk__in=shelves))
        return time() - start

    def test_compare_create(self):
        with atomic():
            self.create_looped()
            self.create_notcomputed()
            self.create_notcomputed_recover()
            self.create_bulk()

        # resync yields same result
        for i in range(10):
            s_looped, s_notcomputed, s_recovered, s_bulk = Shelf.objects.filter(name=f's{i}').order_by('pk')
            self.assertEqual(s_looped.book_names, s_notcomputed.book_names)
            self.assertEqual(s_looped.book_names, s_recovered.book_names)
            self.assertEqual(s_looped.book_names, s_bulk.book_names)

    
    def test_perf_create(self):
        RUNS = 5
        with atomic():
            looped = avg([self.create_looped() for _ in range(RUNS)])
        with atomic():
            notcomputed = avg([self.create_notcomputed() for _ in range(RUNS)])
        with atomic():
            recovered = avg([self.create_notcomputed_recover() for _ in range(RUNS)])
        with atomic():
            bulk = avg([self.create_bulk() for _ in range(10)])
        
        print(
            f'\nperf_related: CREATE (AVG of {RUNS} runs)\n'
            f'looped                     : {fms(looped)}\n'
            f'not_computed               : {fms(notcomputed)}\n'
            f'not_computed(recover=True) : {fms(recovered)}\n'
            f'bulk                       : {fms(bulk)}'
        )

    def update_looped(self, books):
        start = time()
        for i, b in enumerate(books):
            b.name += str(i)
            b.save(update_fields=['name'])
        return time() - start
    
    def update_notcomputed(self, books):
        start = time()
        with not_computed():
            for i, b in enumerate(books):
                b.name += str(i)
                b.save(update_fields=['name'])
        # resync
        update_dependent(Shelf.objects.filter(pk__in=set(b.shelf_id for b in books)))
        return time() - start

    def update_notcomputed_recover(self, books):
        start = time()
        with not_computed(recover=True):
            for i, b in enumerate(books):
                b.name += str(i)
                b.save(update_fields=['name'])
        return time() - start
    
    def update_bulk(self, books):
        start = time()
        for i, b in enumerate(books):
            b.name += str(i)
        Book.objects.fast_update(books, ['name'])  # alot faster than bulk_update
        # resync
        update_dependent(Shelf.objects.filter(pk__in=set(b.shelf_id for b in books)))
        return time() - start

    def test_compare_update(self):
        with atomic():
            self.create_bulk()
            self.create_bulk()
            self.create_bulk()
            self.create_bulk()

        loopeds = []
        notcomputeds = []
        recovereds = []
        bulks = []
        for i in range(10):
            books = Book.objects.filter(name=f'p{i}').order_by('pk')
            loopeds.extend(books[0:10])
            notcomputeds.extend(books[10:20])
            recovereds.extend(books[20:30])
            bulks.extend(books[30:40])
        
        self.assertEqual(len(loopeds), 100)
        self.assertEqual(len(notcomputeds), 100)
        self.assertEqual(len(recovereds), 100)
        self.assertEqual(len(bulks), 100)
        
        with atomic():
            self.update_looped(loopeds)
            self.update_notcomputed(notcomputeds)
            self.update_notcomputed_recover(recovereds)
            self.update_bulk(bulks)

        # resync yields same result
        for i in range(10):
            s_looped, s_notcomputed, s_recovered, s_bulk = list(Shelf.objects.filter(name=f's{i}').order_by('pk'))
            self.assertEqual(s_looped.book_names, s_notcomputed.book_names)
            self.assertEqual(s_looped.book_names, s_recovered.book_names)
            self.assertEqual(s_looped.book_names, s_bulk.book_names)

    def test_perf_update(self):
        RUNS = 5
        with atomic():
            self.create_bulk()
            self.create_bulk()
            self.create_bulk()
            self.create_bulk()

        loopeds = []
        notcomputeds = []
        recovereds = []
        bulks = []
        for i in range(10):
            books = Book.objects.filter(name=f'p{i}').order_by('pk')
            loopeds.extend(books[0:10])
            notcomputeds.extend(books[10:20])
            recovereds.extend(books[20:30])
            bulks.extend(books[30:40])
        
        self.assertEqual(len(loopeds), 100)
        self.assertEqual(len(notcomputeds), 100)
        self.assertEqual(len(recovereds), 100)
        self.assertEqual(len(bulks), 100)
        
        with atomic():
            looped = self.update_looped(loopeds)
            notcomputed = self.update_notcomputed(notcomputeds)
            recovered = self.update_notcomputed_recover(recovereds)
            bulk = self.update_bulk(bulks)

        with atomic():
            looped = avg([self.update_looped(loopeds) for _ in range(RUNS)])
        with atomic():
            notcomputed = avg([self.update_notcomputed(notcomputeds) for _ in range(RUNS)])
        with atomic():
            recovered = avg([self.update_notcomputed_recover(recovereds) for _ in range(RUNS)])
        with atomic():
            bulk = avg([self.update_bulk(bulks) for _ in range(RUNS)])
        
        print(
            f'\nperf_related: UPDATE (AVG of {RUNS} runs)\n'
            f'looped                     : {fms(looped)}\n'
            f'not_computed               : {fms(notcomputed)}\n'
            f'not_computed(recover=True) : {fms(recovered)}\n'
            f'bulk                       : {fms(bulk)}'
        )

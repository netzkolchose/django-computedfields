from django.test import TestCase
from ..models import Book, Shelf
from exampleapp.models import SelfRef
from computedfields.models import not_computed, update_dependent, active_resolver
from time import time
from django.db.transaction import atomic
from computedfields.thread_locals import get_not_computed_context, set_not_computed_context
from time import sleep
from threading import Thread


def fms(v):
    """
    Format seconds value to milliseconds.
    """
    v = int(v * 1000)
    return '% 5d' % v + ' ms'


class NoComputedContext(TestCase):
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
            looped = self.create_looped()
            notcomputed = self.create_notcomputed()
            bulk = self.create_bulk()

        # resync yields same result
        for i in range(10):
            s_looped, s_notcomputed, s_bulk = Shelf.objects.filter(name=f's{i}').order_by('pk')
            self.assertEqual(s_looped.book_names, s_notcomputed.book_names)
            self.assertEqual(s_looped.book_names, s_bulk.book_names)
        
        print(
            f'\nCREATE\n'
            f'looped       : {fms(looped)}\n'
            f'not_computed : {fms(notcomputed)}\n'
            f'bulk         : {fms(bulk)}'
        )

        # not_computed is magnitudes faster than looped (at least 3x)
        self.assertGreater(looped, notcomputed * 3)
        # but cannot beat bulk
        self.assertGreater(notcomputed, bulk)

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
            self.create_looped()
            self.create_notcomputed()
            self.create_bulk()

        loopeds = []
        notcomputeds = []
        bulks = []
        for i in range(10):
            books = Book.objects.filter(name=f'p{i}').order_by('pk')
            loopeds.extend(books[0:10])
            notcomputeds.extend(books[10:20])
            bulks.extend(books[20:30])
        
        self.assertEqual(len(loopeds), 100)
        self.assertEqual(len(notcomputeds), 100)
        self.assertEqual(len(bulks), 100)
        
        with atomic():
            looped = self.update_looped(loopeds)
            notcomputed = self.update_notcomputed(notcomputeds)
            bulk = self.update_bulk(bulks)

        # resync yields same result
        for i in range(10):
            s_looped, s_notcomputed, s_bulk = list(Shelf.objects.filter(name=f's{i}').order_by('pk'))
            self.assertEqual(s_looped.book_names, s_notcomputed.book_names)
            self.assertEqual(s_looped.book_names, s_bulk.book_names)

        print(
            f'\nUPDATE\n'
            f'looped       : {fms(looped)}\n'
            f'not_computed : {fms(notcomputed)}\n'
            f'bulk         : {fms(bulk)}'
        )

        # no_computed is magnitudes faster than looped (at least 3x)
        self.assertGreater(looped, notcomputed * 3)
        # but cannot beat bulk
        self.assertGreater(notcomputed, bulk)

    def test_nesting(self):
        self.assertEqual(get_not_computed_context(), None)
        with not_computed() as ctx:
            stored_ctx = get_not_computed_context()
            self.assertNotEqual(stored_ctx, None)
            self.assertEqual(ctx, stored_ctx)
            with not_computed() as ctx2:
                # stored and returned context may not change
                self.assertEqual(get_not_computed_context(), stored_ctx)
                self.assertEqual(ctx2, stored_ctx)
            self.assertEqual(get_not_computed_context(), ctx)
        self.assertEqual(get_not_computed_context(), None)

    def test_thread_locality(self):
        thread_ctx = None

        def f():
            nonlocal thread_ctx
            ctx = not_computed()
            set_not_computed_context(ctx)
            thread_ctx = get_not_computed_context()
            self.assertEqual(thread_ctx, ctx)

        t = Thread(target=f)
        t.start()
        sleep(.1)
        orig_ctx = get_not_computed_context()
        t.join()
        self.assertEqual(orig_ctx, None)

    def test_disabled_resolver_methods(self):
        # disabled resolver methods:
        # - _querysets_for_update
        # - preupdate_dependent
        # - update_dependent

        shelf1 = Shelf.objects.create(name='s1')
        shelf2 = Shelf.objects.create(name='s2')
        book = Book.objects.create(name='b', shelf=shelf1)
        shelf1.refresh_from_db()
        shelf2.refresh_from_db()
        self.assertEqual(shelf1.book_names, 'b')
        self.assertEqual(shelf2.book_names, '')

        with not_computed():
            # changes that would need intermodel updates
            book.name = 'book'
            book.shelf = shelf2
            book.save()
            qs = active_resolver._querysets_for_update(Book, book)
            self.assertEqual(qs, {})
            old = active_resolver.preupdate_dependent(book)
            self.assertEqual(old, {})
            update_dependent(book)
            self.assertEqual(shelf1.book_names, 'b')
            self.assertEqual(shelf2.book_names, '')

        update_dependent(book)
        shelf1.refresh_from_db()
        shelf2.refresh_from_db()
        self.assertEqual(shelf1.book_names, 'b')    # wrong now (due to missing contributing fk change)
        self.assertEqual(shelf2.book_names, 'book')
        update_dependent(Shelf.objects.all())
        shelf1.refresh_from_db()
        shelf2.refresh_from_db()
        self.assertEqual(shelf1.book_names, '')    # now fixed

    def test_disabled_local_methods(self):
        # disabled model local methods:
        # - update_computedfields
        # - compute

        sf = SelfRef.objects.create(name='test')
        self.assertEqual(sf.c1, 'TEST')

        with not_computed():
            sf.name = 'kaputt'
            computed = active_resolver.compute(sf, 'c1')
            self.assertEqual(computed, 'TEST')
            active_resolver.update_computedfields(sf)
            self.assertEqual(sf.c1, 'TEST')
            sf.save()
            sf.refresh_from_db()
            self.assertEqual(sf.c1, 'TEST')

        sf.save()
        sf.refresh_from_db()
        self.assertEqual(sf.c1, 'KAPUTT')

from django.test import TestCase
from ..models import Book, Shelf
from exampleapp.models import SelfRef
from computedfields.models import not_computed, update_dependent, active_resolver
from computedfields.thread_locals import get_not_computed_context, set_not_computed_context
from time import sleep
from threading import Thread


class NotComputedContext(TestCase):
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

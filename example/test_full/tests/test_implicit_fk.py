from django.test import TestCase
from ..models import Book, Shelf, Page
from computedfields.models import active_resolver


class ImplicitFk(TestCase):
    def setUp(self):
        self.shelf_a = Shelf.objects.create(name='shelf a')
        self.shelf_b = Shelf.objects.create(name='shelf b')
        self.book = Book.objects.create(name='A Book', shelf=self.shelf_a)
        Page.objects.create(num=10, book=self.book)
        Page.objects.create(num=11, book=self.book)

    def test_map(self):
        self.assertDictContainsSubset(
            {'shelf': {Shelf: ({'book_names', 'page_sum'}, {'books'})}},
            active_resolver._map[Book]
        )
        self.assertDictContainsSubset(
            {'book': {Shelf: ({'page_sum'}, {'books__pages'})}},
            active_resolver._map[Page]
        )

    def test_move(self):
        self.book.shelf = self.shelf_b
        self.book.save(update_fields=['shelf']) # important: we update only the fk relation
        self.shelf_a.refresh_from_db()
        self.shelf_b.refresh_from_db()
        self.assertEqual(self.shelf_a.book_names, '')
        self.assertEqual(self.shelf_b.book_names, 'A Book')
        self.assertEqual(self.shelf_a.page_sum, 0)
        self.assertEqual(self.shelf_b.page_sum, 21)

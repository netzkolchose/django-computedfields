from django.test import TestCase
from .. import models


class UpdateFields(TestCase):
    def setUp(self):
        self.a = models.PartialUpdateA.objects.create(name='a')
        self.b = models.PartialUpdateB.objects.create(name='b', f_ba=self.a)

    def test_partial_update(self):
        self.assertEqual(self.b.comp, 'ab')
        self.a.name = 'A'
        self.a.save(update_fields=['name'])
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'Ab')


from computedfields.models import not_computed
class UpdateFieldsNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.a = models.PartialUpdateA.objects.create(name='a')
            self.b = models.PartialUpdateB.objects.create(name='b', f_ba=self.a)
        self.a.refresh_from_db()
        self.b.refresh_from_db()

    def test_partial_update(self):
        self.assertEqual(self.b.comp, 'ab')
        with not_computed(recover=True):
            self.a.name = 'A'
            self.a.save(update_fields=['name'])
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'Ab')

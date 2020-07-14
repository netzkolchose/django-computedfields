from django.test import TestCase
from ..models import OBackward, OSource, ORelated, OForward


class TestOne2OneExplicit(TestCase):
    def setUp(self):
        self.b = OBackward.objects.create(name='B')
        self.s = OSource.objects.create(name='S', o=self.b)

        self.r = ORelated.objects.create(name='R')
        self.f = OForward.objects.create(name='F', o=self.r)

    def test_init_backward(self):
        self.b.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.b.forward_name, 'S')

    def test_init_forward(self):
        self.r.refresh_from_db()
        self.f.refresh_from_db()
        self.assertEqual(self.f.backward_name, 'R')

    def test_rename_backward(self):
        self.s.name = 'SS'
        self.s.save(update_fields=['name'])
        self.b.refresh_from_db()
        self.assertEqual(self.b.forward_name, 'SS')

    def test_rename_forward(self):
        self.r.name = 'RR'
        self.r.save(update_fields=['name'])
        self.f.refresh_from_db()
        self.assertEqual(self.f.backward_name, 'RR')

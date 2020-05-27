from django.test import TestCase
from ..models import ComputeLocal


class TestResultFromCompute(TestCase):
    def setUp(self):
        self.cl = ComputeLocal.objects.create(name='name', xy=123)
    
    def test_init(self):
        # no refresh from db needed, since all cfs depend on local fields only
        self.assertEqual(self.cl.c1, 'NAME')
        self.assertEqual(self.cl.c2, 'c2NAME')
        self.assertEqual(self.cl.c3, 'c3NAME')
        self.assertEqual(self.cl.c4, 'c4c3NAME')
        self.assertEqual(self.cl.c5, 'c5c2NAMEc4c3NAMEc6123')
        self.assertEqual(self.cl.c6, 'c6123')
        self.assertEqual(self.cl.c7, 'c7c8')
        self.assertEqual(self.cl.c8, 'c8')
        # db has same state
        self.cl.refresh_from_db()
        self.assertEqual(self.cl.c1, 'NAME')
        self.assertEqual(self.cl.c2, 'c2NAME')
        self.assertEqual(self.cl.c3, 'c3NAME')
        self.assertEqual(self.cl.c4, 'c4c3NAME')
        self.assertEqual(self.cl.c5, 'c5c2NAMEc4c3NAMEc6123')
        self.assertEqual(self.cl.c6, 'c6123')
        self.assertEqual(self.cl.c7, 'c7c8')
        self.assertEqual(self.cl.c8, 'c8')

    def test_init_empty(self):
        # all should be empty
        cl = ComputeLocal(name='name', xy=123)
        # all should be empty initially
        self.assertEqual(cl.c1, '')
        self.assertEqual(cl.c2, '')
        self.assertEqual(cl.c3, '')
        self.assertEqual(cl.c4, '')
        self.assertEqual(cl.c5, '')
        self.assertEqual(cl.c6, '')
        self.assertEqual(cl.c7, '')
        self.assertEqual(cl.c8, '')
        # computed should calculate correct value across other deps
        self.assertEqual(cl.compute('c1'), 'NAME')                    # self.name.upper()
        self.assertEqual(cl.compute('c2'), 'c2NAME')                  # 'c2' + self.c1
        self.assertEqual(cl.compute('c3'), 'c3NAME')                  # 'c3' + self.c1
        self.assertEqual(cl.compute('c4'), 'c4c3NAME')                # 'c4' + self.c3
        self.assertEqual(cl.compute('c5'), 'c5c2NAMEc4c3NAMEc6123')   # 'c5' + self.c2 + self.c4 + self.c6
        self.assertEqual(cl.compute('c6'), 'c6123')                   # 'c6' + str(self.xy)
        self.assertEqual(cl.compute('c7'), 'c7c8')                    # 'c7' + self.c8
        self.assertEqual(cl.compute('c8'), 'c8')                      # 'c8'
        # all should still be empty (no side effects on instance)
        self.assertEqual(cl.c1, '')
        self.assertEqual(cl.c2, '')
        self.assertEqual(cl.c3, '')
        self.assertEqual(cl.c4, '')
        self.assertEqual(cl.c5, '')
        self.assertEqual(cl.c6, '')
        self.assertEqual(cl.c7, '')
        self.assertEqual(cl.c8, '')

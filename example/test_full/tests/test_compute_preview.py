from django.test import TestCase
from ..models import ComputeLocal
from computedfields.models import update_dependent, compute


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
        self.assertEqual(compute(cl, 'c1'), 'NAME')                    # self.name.upper()
        self.assertEqual(compute(cl, 'c2'), 'c2NAME')                  # 'c2' + self.c1
        self.assertEqual(compute(cl, 'c3'), 'c3NAME')                  # 'c3' + self.c1
        self.assertEqual(compute(cl, 'c4'), 'c4c3NAME')                # 'c4' + self.c3
        self.assertEqual(compute(cl, 'c5'), 'c5c2NAMEc4c3NAMEc6123')   # 'c5' + self.c2 + self.c4 + self.c6
        self.assertEqual(compute(cl, 'c6'), 'c6123')                   # 'c6' + str(self.xy)
        self.assertEqual(compute(cl, 'c7'), 'c7c8')                    # 'c7' + self.c8
        self.assertEqual(compute(cl, 'c8'), 'c8')                      # 'c8'
        # all should still be empty (no side effects on instance)
        self.assertEqual(cl.c1, '')
        self.assertEqual(cl.c2, '')
        self.assertEqual(cl.c3, '')
        self.assertEqual(cl.c4, '')
        self.assertEqual(cl.c5, '')
        self.assertEqual(cl.c6, '')
        self.assertEqual(cl.c7, '')
        self.assertEqual(cl.c8, '')

    def test_compute_normal_field(self):
        # should simply return the value for normal fields or raise
        self.assertEqual(compute(self.cl, 'xy'), 123)
        with self.assertRaises(AttributeError):
            compute(self.cl, 'unknown')

    def test_manually_cf_update(self):
        # we insert with bulk_create, thus cfs are out of sync
        # a manual cf listing in update_fields should update all dependents
        ComputeLocal.objects.bulk_create([
          ComputeLocal(name='test', xy=666)
        ])
        cl = ComputeLocal.objects.filter(name='test')[0]
        # cfs are out of sync
        self.assertEqual(cl.c1, '')
        self.assertEqual(cl.c2, '')
        self.assertEqual(cl.c3, '')
        self.assertEqual(cl.c4, '')
        self.assertEqual(cl.c5, '')
        self.assertEqual(cl.c6, '')
        self.assertEqual(cl.c7, '')
        self.assertEqual(cl.c8, '')

        # sync manually
        cl.save(update_fields=['c1','c2','c3','c4','c5','c6','c7','c8'])
        cl.refresh_from_db()
        self.assertEqual(cl.c1, 'TEST')
        self.assertEqual(cl.c2, 'c2TEST')
        self.assertEqual(cl.c3, 'c3TEST')
        self.assertEqual(cl.c4, 'c4c3TEST')
        self.assertEqual(cl.c5, 'c5c2TESTc4c3TESTc6666')
        self.assertEqual(cl.c6, 'c6666')
        self.assertEqual(cl.c7, 'c7c8')
        self.assertEqual(cl.c8, 'c8')
        # added for test coverage - resaving only cfs without any change should not trigger `save`
        cl.save(update_fields=['c1','c2','c3','c4','c5','c6','c7','c8'])

    def test_manually_cf_update_bulk(self):
        # do cfs updates manually after bulk create of many records
        names = ['testa', 'testb', 'testc']
        ComputeLocal.objects.bulk_create([
          ComputeLocal(name=name, xy=666, c8='SENTINEL') for name in names
        ])
        # get pks to test against after update
        pks = [el.pk for el in ComputeLocal.objects.filter(c8='SENTINEL')]
        update_dependent(ComputeLocal.objects.filter(c8='SENTINEL'), update_fields=['c1','c2','c3','c4','c5','c6','c7','c8'])

        for i, el in enumerate(ComputeLocal.objects.filter(pk__in=pks)):
            name = names[i].upper()
            self.assertEqual(el.c1, name)
            self.assertEqual(el.c2, 'c2{}'.format(name))
            self.assertEqual(el.c3, 'c3{}'.format(name))
            self.assertEqual(el.c4, 'c4c3{}'.format(name))
            self.assertEqual(el.c5, 'c5c2{}c4c3{}c6666'.format(name, name))
            self.assertEqual(el.c6, 'c6666')
            self.assertEqual(el.c7, 'c7c8')
            self.assertEqual(el.c8, 'c8')


from computedfields.models import not_computed
class TestResultFromComputeNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.cl = ComputeLocal.objects.create(name='name', xy=123)
        self.cl.refresh_from_db()
    
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
        with not_computed(recover=True):
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
            # in not_computed computed should not calculate anything
            self.assertEqual(compute(cl, 'c1'), '')
            self.assertEqual(compute(cl, 'c2'), '')
            self.assertEqual(compute(cl, 'c3'), '')
            self.assertEqual(compute(cl, 'c4'), '')
            self.assertEqual(compute(cl, 'c5'), '')
            self.assertEqual(compute(cl, 'c6'), '')
            self.assertEqual(compute(cl, 'c7'), '')
            self.assertEqual(compute(cl, 'c8'), '')
            # all should still be empty (no side effects on instance)
            self.assertEqual(cl.c1, '')
            self.assertEqual(cl.c2, '')
            self.assertEqual(cl.c3, '')
            self.assertEqual(cl.c4, '')
            self.assertEqual(cl.c5, '')
            self.assertEqual(cl.c6, '')
            self.assertEqual(cl.c7, '')
            self.assertEqual(cl.c8, '')

    def test_compute_normal_field(self):
        # should simply return the value for normal fields or raise
        self.assertEqual(compute(self.cl, 'xy'), 123)
        with self.assertRaises(AttributeError):
            compute(self.cl, 'unknown')

    def test_manually_cf_update(self):
        # we insert with bulk_create, thus cfs are out of sync
        # a manual cf listing in update_fields should update all dependents
        ComputeLocal.objects.bulk_create([
          ComputeLocal(name='test', xy=666)
        ])
        cl = ComputeLocal.objects.filter(name='test')[0]
        # cfs are out of sync
        self.assertEqual(cl.c1, '')
        self.assertEqual(cl.c2, '')
        self.assertEqual(cl.c3, '')
        self.assertEqual(cl.c4, '')
        self.assertEqual(cl.c5, '')
        self.assertEqual(cl.c6, '')
        self.assertEqual(cl.c7, '')
        self.assertEqual(cl.c8, '')

        # sync manually
        with not_computed(recover=True):
            cl.save(update_fields=['c1','c2','c3','c4','c5','c6','c7','c8'])
        cl.refresh_from_db()
        self.assertEqual(cl.c1, 'TEST')
        self.assertEqual(cl.c2, 'c2TEST')
        self.assertEqual(cl.c3, 'c3TEST')
        self.assertEqual(cl.c4, 'c4c3TEST')
        self.assertEqual(cl.c5, 'c5c2TESTc4c3TESTc6666')
        self.assertEqual(cl.c6, 'c6666')
        self.assertEqual(cl.c7, 'c7c8')
        self.assertEqual(cl.c8, 'c8')
        # added for test coverage - resaving only cfs without any change should not trigger `save`
        cl.save(update_fields=['c1','c2','c3','c4','c5','c6','c7','c8'])

    def test_manually_cf_update_bulk(self):
        with not_computed(recover=True):
            # do cfs updates manually after bulk create of many records
            names = ['testa', 'testb', 'testc']
            ComputeLocal.objects.bulk_create([
            ComputeLocal(name=name, xy=666, c8='SENTINEL') for name in names
            ])
            # get pks to test against after update
            pks = [el.pk for el in ComputeLocal.objects.filter(c8='SENTINEL')]
            update_dependent(ComputeLocal.objects.filter(c8='SENTINEL'), update_fields=['c1','c2','c3','c4','c5','c6','c7','c8'])

        for i, el in enumerate(ComputeLocal.objects.filter(pk__in=pks)):
            name = names[i].upper()
            self.assertEqual(el.c1, name)
            self.assertEqual(el.c2, 'c2{}'.format(name))
            self.assertEqual(el.c3, 'c3{}'.format(name))
            self.assertEqual(el.c4, 'c4c3{}'.format(name))
            self.assertEqual(el.c5, 'c5c2{}c4c3{}c6666'.format(name, name))
            self.assertEqual(el.c6, 'c6666')
            self.assertEqual(el.c7, 'c7c8')
            self.assertEqual(el.c8, 'c8')

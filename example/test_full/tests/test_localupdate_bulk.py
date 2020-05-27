from django.test import TestCase
from ..models import ComputeLocal, LocalBulkUpdate
from computedfields.models import update_dependent, update_dependent_multi

class UpdateDependentWithLocals(TestCase):
    def setUp(self):
        self.cl = ComputeLocal.objects.create(name='name', xy=123)
        self.bu = LocalBulkUpdate.objects.create(fk=self.cl)
    
    def test_init(self):
        self.assertEqual(self.bu.same_as_fk_c5, 'c5c2NAMEc4c3NAMEc6123')

    def test_update(self):
        ComputeLocal.objects.all().update(name='other')
        update_dependent(ComputeLocal.objects.all(), update_fields=['name'])
        self.cl.refresh_from_db()
        self.bu.refresh_from_db()
        self.assertEqual(self.cl.c1, 'OTHER')
        self.assertEqual(self.cl.c2, 'c2OTHER')
        self.assertEqual(self.cl.c3, 'c3OTHER')
        self.assertEqual(self.cl.c4, 'c4c3OTHER')
        self.assertEqual(self.cl.c5, 'c5c2OTHERc4c3OTHERc6123')
        self.assertEqual(self.cl.c6, 'c6123')
        self.assertEqual(self.cl.c7, 'c7c8')
        self.assertEqual(self.cl.c8, 'c8')
        self.assertEqual(self.bu.same_as_fk_c5, 'c5c2OTHERc4c3OTHERc6123')

    def test_update_multi(self):
        ComputeLocal.objects.all().update(name='other')
        update_dependent_multi([ComputeLocal.objects.all()])
        self.cl.refresh_from_db()
        self.bu.refresh_from_db()
        self.assertEqual(self.cl.c1, 'OTHER')
        self.assertEqual(self.cl.c2, 'c2OTHER')
        self.assertEqual(self.cl.c3, 'c3OTHER')
        self.assertEqual(self.cl.c4, 'c4c3OTHER')
        self.assertEqual(self.cl.c5, 'c5c2OTHERc4c3OTHERc6123')
        self.assertEqual(self.cl.c6, 'c6123')
        self.assertEqual(self.cl.c7, 'c7c8')
        self.assertEqual(self.cl.c8, 'c8')
        self.assertEqual(self.bu.same_as_fk_c5, 'c5c2OTHERc4c3OTHERc6123')

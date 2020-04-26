from django.test import TestCase, override_settings
from .models import QueryCounter
from .models import BParent, BChild, BSubChild
from .models import BParentReverse, BChildReverse, BSubChildReverse
from computedfields.models import ComputedFieldsModelType as CFMT, update_dependent, preupdate_dependent


class CountQueriesFk(TestCase):
    def setUp(self):
        self.p1 = BParent.objects.create(name='p1')
        self.p2 = BParent.objects.create(name='p2')
        self.c1 = BChild.objects.create(name='c1', parent=self.p1)
        self.c2 = BChild.objects.create(name='c2', parent=self.p2)
        for i in range(100):
            BSubChild.objects.create(name='s1_{}'.format(i), parent=self.c1)

    @override_settings(DEBUG=True)
    @QueryCounter(False, 'test_change_p1_name: {count} queries')
    def test_change_p1_name(self):
        self.p1.name = 'P1'
        self.p1.save()

    @override_settings(DEBUG=True)
    @QueryCounter(False, 'test_change_c1_parent: {count} queries')
    def test_change_c1_parent(self):
        self.c1.parent = self.p2
        self.c1.save()

class CountQueriesFkBack(TestCase):
    def setUp(self):
        self.p1 = BParentReverse.objects.create(name='p1')
        self.p2 = BParentReverse.objects.create(name='p2')
        for i in range(10):
            BChildReverse.objects.create(name='c1_{}'.format(i), parent=self.p1)
        self.c1 = BChildReverse.objects.all()[0]
        for i in range(10):
            BSubChildReverse.objects.create(name='s1_{}'.format(i), parent=self.c1)

    @override_settings(DEBUG=True)
    @QueryCounter(False, 'test_change_s_name: {count} queries')
    def test_change_s_name(self):
        #s = BSubChildReverse.objects.all()[0]
        #s.name = 'SSS'
        #s.save()
        #for el in BSubChildReverse.objects.all():
        #    el.name = 'SSS'
        #    el.save()
        # better way:  FIXME: needs advanced opt hints in docs
        old = preupdate_dependent(BSubChildReverse.objects.all())
        BSubChildReverse.objects.all().update(name='SSS')
        update_dependent(BSubChildReverse.objects.all(), old=old)

    @override_settings(DEBUG=True)
    @QueryCounter(False, 'test_change_c1_parent: {count} queries')
    def test_change_c1_parent(self):
        self.c1.parent = self.p2
        self.c1.save()

from django.test import TestCase
from ..models import ParentNotO, ChildNotO, SubChildNotO, ParentO, ChildO, SubChildO
from django.test.utils import CaptureQueriesContext
from django.db import connection


class SelectRelatedOptimization(TestCase):
    def setUp(self):
        self.p1_not_o = ParentNotO.objects.create(name='p1')
        self.p1_o = ParentO.objects.create(name='p1')
        self.p2_not_o = ParentNotO.objects.create(name='p2')
        self.p2_o = ParentO.objects.create(name='p2')

        self.c1_not_o = ChildNotO.objects.create(name='c1', parent=self.p1_not_o)
        self.c1_o = ChildO.objects.create(name='c1', parent=self.p1_o)
        self.c2_not_o = ChildNotO.objects.create(name='c2', parent=self.p2_not_o)
        self.c2_o = ChildO.objects.create(name='c2', parent=self.p2_o)

        for i in range(100):
            SubChildNotO.objects.create(name='s1_{}'.format(i), parent=self.c1_not_o)
        for i in range(100):
            SubChildO.objects.create(name='s1_{}'.format(i), parent=self.c1_o)
    
    def test_init(self):
        for i, el in enumerate(SubChildNotO.objects.all()):
            self.assertEqual(el.parents, 's1_{}$c1$p1'.format(i))
        for i, el in enumerate(SubChildO.objects.all()):
            self.assertEqual(el.parents, 's1_{}$c1$p1'.format(i))

    def test_change_p1_name(self):
        with CaptureQueriesContext(connection) as queries:
            self.p1_not_o.name = 'P1'
            self.p1_not_o.save(update_fields=['name'])
        unoptimized = len(queries.captured_queries)

        with CaptureQueriesContext(connection) as queries:
            self.p1_o.name = 'P1'
            self.p1_o.save(update_fields=['name'])
        optimized = len(queries.captured_queries)

        for i, el in enumerate(SubChildNotO.objects.all()):
            self.assertEqual(el.parents, 's1_{}$c1$P1'.format(i))
        for i, el in enumerate(SubChildO.objects.all()):
            self.assertEqual(el.parents, 's1_{}$c1$P1'.format(i))
        self.assertGreater(unoptimized - optimized, 100)

    def test_change_c1_parent(self):
        with CaptureQueriesContext(connection) as queries:
            self.c1_not_o.parent = self.p2_not_o
            self.c1_not_o.save()
        unoptimized = len(queries.captured_queries)

        with CaptureQueriesContext(connection) as queries:
            self.c1_o.parent = self.p2_o
            self.c1_o.save()
        optimized = len(queries.captured_queries)

        for i, el in enumerate(SubChildNotO.objects.all()):
            self.assertEqual(el.parents, 's1_{}$c1$p2'.format(i))
        for i, el in enumerate(SubChildO.objects.all()):
            self.assertEqual(el.parents, 's1_{}$c1$p2'.format(i))
        self.assertGreater(unoptimized - optimized, 100)

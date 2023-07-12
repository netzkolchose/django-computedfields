import operator

from django.test import TestCase

from computedfields.resolver import Resolver
from ..models import ParentNotO, ChildNotO, SubChildNotO, ParentO, ChildO, SubChildO
from ..models import (ParentReverseNotO, ChildReverseNotO, SubChildReverseNotO,
                      ParentReverseO, ChildReverseO, SubChildReverseO)
from django.test.utils import CaptureQueriesContext
from django.db import connection
from computedfields.models import preupdate_dependent, update_dependent


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

        # should save 2 x 100 queries (100 subs with 2 lookups in method)
        self.assertEqual(unoptimized - optimized, 200)

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

        # should save 2 x 100 queries (100 subs with 2 lookups in method)
        self.assertEqual(unoptimized - optimized, 200)


class PrefetchRelatedOptimization(TestCase):
    def setUp(self):
        self.p1_not_o = ParentReverseNotO.objects.create(name='p1')
        self.p1_o = ParentReverseO.objects.create(name='p1')
        self.p2_not_o = ParentReverseNotO.objects.create(name='p2')
        self.p2_o = ParentReverseO.objects.create(name='p2')

        for i in range(10):
            ChildReverseNotO.objects.create(name='c1_{}'.format(i), parent=self.p1_not_o)
        for i in range(10):
            ChildReverseO.objects.create(name='c1_{}'.format(i), parent=self.p1_o)
        
        self.c1_not_o = ChildReverseNotO.objects.all()[0]
        for i in range(10):
            SubChildReverseNotO.objects.create(name='s1_{}'.format(i), parent=self.c1_not_o)
        self.c1_o = ChildReverseO.objects.all()[0]
        for i in range(10):
            SubChildReverseO.objects.create(name='s1_{}'.format(i), parent=self.c1_o)
    
    def test_init(self):
        self.p1_not_o.refresh_from_db()
        self.p1_o.refresh_from_db()
        self.assertEqual(self.p1_not_o.children_comp,
            'c1_0#s1_0,s1_1,s1_2,s1_3,s1_4,s1_5,s1_6,s1_7,s1_8,s1_9$c1_1$c1_2$c1_3$c1_4$c1_5$c1_6$c1_7$c1_8$c1_9')
        self.assertEqual(self.p1_o.children_comp,
            'c1_0#s1_0,s1_1,s1_2,s1_3,s1_4,s1_5,s1_6,s1_7,s1_8,s1_9$c1_1$c1_2$c1_3$c1_4$c1_5$c1_6$c1_7$c1_8$c1_9')

    def test_change_sub_name_bulk(self):
        with CaptureQueriesContext(connection) as queries:
            old = preupdate_dependent(SubChildReverseNotO.objects.all())
            SubChildReverseNotO.objects.all().update(name='S')
            update_dependent(SubChildReverseNotO.objects.all(), old=old)
        unoptimized = len(queries.captured_queries)

        with CaptureQueriesContext(connection) as queries:
            old = preupdate_dependent(SubChildReverseO.objects.all())
            SubChildReverseO.objects.all().update(name='S')
            update_dependent(SubChildReverseO.objects.all(), old=old)
        optimized = len(queries.captured_queries)

        # should turn all sub names into single S
        self.p1_not_o.refresh_from_db()
        self.p1_o.refresh_from_db()
        self.assertEqual(self.p1_not_o.children_comp,
            'c1_0#S,S,S,S,S,S,S,S,S,S$c1_1$c1_2$c1_3$c1_4$c1_5$c1_6$c1_7$c1_8$c1_9')
        self.assertEqual(self.p1_o.children_comp,
            'c1_0#S,S,S,S,S,S,S,S,S,S$c1_1$c1_2$c1_3$c1_4$c1_5$c1_6$c1_7$c1_8$c1_9')

        # should save 10 individual subqueries, but adds one --> 9
        self.assertEqual(unoptimized - optimized, 9)

    def test_change_c1_parent(self):
        with CaptureQueriesContext(connection) as queries:
            self.c1_not_o.parent = self.p2_not_o
            self.c1_not_o.save()
        unoptimized = len(queries.captured_queries)

        with CaptureQueriesContext(connection) as queries:
            self.c1_o.parent = self.p2_o
            self.c1_o.save()
        optimized = len(queries.captured_queries)

        self.p1_not_o.refresh_from_db()
        self.p1_o.refresh_from_db()
        self.p2_not_o.refresh_from_db()
        self.p2_o.refresh_from_db()

        # should move c1 + subs from p1 to p2
        self.assertEqual(self.p1_not_o.children_comp,
            'c1_1$c1_2$c1_3$c1_4$c1_5$c1_6$c1_7$c1_8$c1_9')
        self.assertEqual(self.p1_o.children_comp,
            'c1_1$c1_2$c1_3$c1_4$c1_5$c1_6$c1_7$c1_8$c1_9')
        self.assertEqual(self.p2_not_o.children_comp,
            'c1_0#s1_0,s1_1,s1_2,s1_3,s1_4,s1_5,s1_6,s1_7,s1_8,s1_9')
        self.assertEqual(self.p2_o.children_comp,
            'c1_0#s1_0,s1_1,s1_2,s1_3,s1_4,s1_5,s1_6,s1_7,s1_8,s1_9')

        # should save 10 individual queries, but adds 2 for to prefetch related subs --> 8
        self.assertEqual(unoptimized - optimized, 8)


class PipeQueriesOptimization(TestCase):

    def test_join_queries_using_or(self):
        with self.subTest("No queries to join."):
            pipe_method = Resolver()._choose_optimal_query_pipe_method({'field1'})
            self.assertEqual(operator.or_, pipe_method)
        with self.subTest("Queries with were statement based on same model. Filter on self."):
            pipe_method = Resolver()._choose_optimal_query_pipe_method({'field1', 'field2'})
            self.assertEqual(operator.or_, pipe_method)
        with self.subTest("Queries with were statement based on same model. Filter on external model."):
            pipe_method = Resolver()._choose_optimal_query_pipe_method({'A__field1', 'A__field2'})
            self.assertEqual(operator.or_, pipe_method)

    def test_join_queries_using_union(self):
        with self.subTest("Queries with were statement based on different models."):
            pipe_method = Resolver()._choose_optimal_query_pipe_method({'A__field1', 'B__field2'})
            self.assertNotEqual(operator.or_, pipe_method)

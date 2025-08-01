from django.test import TestCase
from ..models import EmailUser
from computedfields.raw_update import merged_update
from django.test.utils import CaptureQueriesContext
from django.db import connection


class TestRawUpdate(TestCase):
    def test_mt_support(self):
        eu1 = EmailUser.objects.create(forname='Anton', surname='AAA', email='aaa@example.com')
        eu2 = EmailUser.objects.create(forname='Anton', surname='AAA', email='aaa@example.com')
        eu3 = EmailUser.objects.create(forname='Anton', surname='AAA', email='aaa@example.com')
        objs = [eu1, eu2, eu3]

        # one merged update on emailuser
        for o in objs:
            o.email = 'ziggy@example.com'
        with CaptureQueriesContext(connection) as queries:
            merged_update(EmailUser.objects.all(), objs, ['email'])
        self.assertEqual(len(queries.captured_queries), 1)
        self.assertTrue(queries.captured_queries[0]['sql'].startswith('UPDATE "test_full_emailuser"'))
        self.assertEqual(
            list(EmailUser.objects.all().values_list('email', flat=True)),
            ['ziggy@example.com'] * 3
        )
        
        # one merged update on user
        for o in objs:
            o.forname = 'Ziggy'
        with CaptureQueriesContext(connection) as queries:
            merged_update(EmailUser.objects.all(), objs, ['forname'])
        self.assertEqual(len(queries.captured_queries), 1)
        self.assertTrue(queries.captured_queries[0]['sql'].startswith('UPDATE "test_full_user"'))
        self.assertEqual(
            list(EmailUser.objects.all().values_list('forname', flat=True)),
            ['Ziggy'] * 3
        )

        # 2 updates (one merged, one single) on user
        for o in objs:
            o.surname = 'Zabalot'
        objs[0].surname = 'ZZZ'
        with CaptureQueriesContext(connection) as queries:
            merged_update(EmailUser.objects.all(), objs, ['surname'])
        self.assertEqual(len(queries.captured_queries), 2)
        self.assertTrue(queries.captured_queries[0]['sql'].startswith('UPDATE "test_full_user"'))
        self.assertTrue(queries.captured_queries[1]['sql'].startswith('UPDATE "test_full_user"'))
        self.assertEqual(
            list(EmailUser.objects.all().values_list('surname', flat=True).order_by('pk')),
            ['ZZZ', 'Zabalot', 'Zabalot']
        )

        # 2 updates, one on emailuser, one on user
        for o in objs:
            o.email = 'xxx@example.com'
            o.forname = 'AAA'
        with CaptureQueriesContext(connection) as queries:
            merged_update(EmailUser.objects.all(), objs, ['email', 'forname'])
        self.assertEqual(len(queries.captured_queries), 2)
        self.assertTrue(queries.captured_queries[0]['sql'].startswith('UPDATE "test_full_emailuser"'))
        self.assertTrue(queries.captured_queries[1]['sql'].startswith('UPDATE "test_full_user"'))
        self.assertEqual(
            list(EmailUser.objects.all().values_list('email', flat=True)),
            ['xxx@example.com'] * 3
        )
        self.assertEqual(
            list(EmailUser.objects.all().values_list('forname', flat=True)),
            ['AAA'] * 3
        )

        # works with one object
        with CaptureQueriesContext(connection) as queries:
            merged_update(EmailUser.objects.all(), [eu1], ['email'])
        self.assertEqual(len(queries.captured_queries), 1)
        self.assertTrue(queries.captured_queries[0]['sql'].startswith('UPDATE "test_full_emailuser"'))

        # does not merge 2 objects
        with CaptureQueriesContext(connection) as queries:
            merged_update(EmailUser.objects.all(), [eu1, eu2], ['email', 'forname', 'surname'])
        self.assertEqual(len(queries.captured_queries), 4)
        self.assertTrue(queries.captured_queries[0]['sql'].startswith('UPDATE "test_full_emailuser"'))
        self.assertTrue(queries.captured_queries[1]['sql'].startswith('UPDATE "test_full_emailuser"'))
        self.assertTrue(queries.captured_queries[2]['sql'].startswith('UPDATE "test_full_user"'))
        self.assertTrue(queries.captured_queries[3]['sql'].startswith('UPDATE "test_full_user"'))

from django.test import TestCase
from ..models import FieldUpdate
from computedfields.models import update_dependent, active_resolver
from datetime import datetime, timedelta
import pytz
from decimal import Decimal
from uuid import uuid4


FIELDS = [
    'binary',
    'boolean',
    'char',
    'date',
    'datetime',
    'decimal',
    'duration',
    'email',
    'float',
    'integer',
    'ip',
    'json',
    'slug',
    'text',
    'time',
    'url',
    'uuid',
]

class MismatchException(Exception):
    pass

def compare_values(obj):
    for f in FIELDS:
        orig = getattr(obj, f + '_field')
        comp = getattr(obj, f + '_comp')
        if orig != comp:
            raise MismatchException(f'mismatch found: {obj.pk} - {f}, orig: {repr(orig)}, comp: {repr(comp)}')


class TestFieldUpdate(TestCase):
    
    def test_init(self):
        print('fast_update:', active_resolver.use_fastupdate)
        FieldUpdate.objects.create(
            binary_field = b'\x01\x02\x03\x04',
            boolean_field = True,
            char_field = 'ello',
            date_field = datetime.date(datetime.now(pytz.UTC)),
            datetime_field = datetime.now(pytz.UTC),
            decimal_field = Decimal('12.11'),
            duration_field = timedelta(days=3, hours=4, minutes=5),
            email_field = 'hello@example.com',
            float_field = 1.2345,
            integer_field = 666,
            ip_field = '127.0.0.1',
            json_field = {'a': 1, 5: 'b'},
            slug_field = 'here comes the mouse!',
            text_field = 'This is some longish text\n with multiple lines.',
            time_field = datetime.time(datetime.now(pytz.UTC)),
            url_field = 'https://example.com',
            uuid_field = uuid4()
        )
        obj = FieldUpdate.objects.all()[0]
        compare_values(obj)
    
    def test_fastupdate(self):
        FieldUpdate.objects.all().delete()
        inst = FieldUpdate(
            binary_field = b'\x01\x02\x03\x04',
            boolean_field = True,
            char_field = 'ello',
            date_field = datetime.date(datetime.now(pytz.UTC)),
            datetime_field = datetime.now(pytz.UTC),
            decimal_field = Decimal('12.11'),
            duration_field = timedelta(days=3, hours=4, minutes=5),
            email_field = 'hello@example.com',
            float_field = 1.2345,
            integer_field = 666,
            ip_field = '127.0.0.1',
            json_field = {'a': 1, 5: 'b'},
            slug_field = 'here comes the mouse!',
            text_field = 'This is some longish text\n with multiple lines.',
            time_field = datetime.time(datetime.now(pytz.UTC)),
            url_field = 'https://example.com',
            uuid_field = uuid4()
        )
        FieldUpdate.objects.bulk_create([inst])
        obj = FieldUpdate.objects.all()[0]
        # should raise since we did not update cfs yet
        self.assertRaises(MismatchException, lambda : compare_values(obj))
        # update cfs, should not raise anymore
        update_dependent(FieldUpdate.objects.all())
        obj = FieldUpdate.objects.all()[0]
        compare_values(obj)

    def test_nullvalues(self):
        FieldUpdate.objects.all().delete()
        # all fields but one are None
        inst = FieldUpdate(char_field = 'ello')
        FieldUpdate.objects.bulk_create([inst])
        obj = FieldUpdate.objects.all()[0]
        # should raise because of mismatch in char_field vs. char_comp
        self.assertRaises(MismatchException, lambda : compare_values(obj))
        # update cfs, should not raise anymore
        update_dependent(FieldUpdate.objects.all())
        obj = FieldUpdate.objects.all()[0]
        compare_values(obj)

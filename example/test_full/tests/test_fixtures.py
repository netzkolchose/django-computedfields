from django.test import TestCase, TransactionTestCase
from ..models import FixtureParent, FixtureChild
from django.core.management import call_command
from contextlib import contextmanager
from json import dumps, loads


def dumpdata_to_jsonstring(modelname):
    import sys
    from io import StringIO
    buf = StringIO()
    sysout = sys.stdout
    sys.stdout = buf
    call_command('dumpdata', modelname)
    sys.stdout = sysout
    return buf.getvalue()


# This test case must run before the second one.
class CreateDesyncFixtureData(TestCase):
    def test_create_data(self):
        # parent objs
        pA = FixtureParent.objects.create(name='A')
        FixtureParent.objects.create(name='B')
        FixtureParent.objects.create(name='C')
        raw = dumpdata_to_jsonstring('test_full.FixtureParent')
        with open('fixtureparent.json', 'w') as f:
            f.write(raw)

        # children objs
        for i in range(10):
            FixtureChild.objects.create(name=str(i), parent=pA)
        raw = dumpdata_to_jsonstring('test_full.FixtureChild')
        # delete path to get desync computed value
        data = loads(raw)
        for el in data:
            el['fields']['path'] = ''
        with open('fixturechild.json', 'w') as f:
            f.write(dumps(data))


class TestUpdatedata(TestCase):
    fixtures = ["fixtureparent.json", "fixturechild.json"]

    def test_computedfields_desync(self):
        # all children_count are zero
        self.assertEqual(list(FixtureParent.objects.all().values_list('children_count', flat=True).order_by('pk')), [0, 0, 0])
        # all path fields are empty
        self.assertEqual(any(FixtureChild.objects.all().values_list('path', flat=True)), False)

    def test_computedfields_resync(self):
        call_command('updatedata')  # expensive since resyncing all cfs in test models (~120ms)
        self.assertEqual(list(FixtureParent.objects.all().values_list('children_count', flat=True).order_by('pk')), [10, 0, 0])
        self.assertEqual(
            list(FixtureChild.objects.all().values_list('path', flat=True)),
            ['/A#10/' + str(i) for i in range(10)]
        )

    def test_computedfields_resync_advanced(self):
        # with good knowledge of what has changed and the dependency tree we can narrow down the resync
        # in the test data:
        # - FixtureParent records loaded (desync children_count)
        # - FixtureChild records loaded (desync path)
        # - FixtureParent.children_count depends on FixtureChild.parent only
        # --> we only need to trigger resync on children records, the resolver refreshs parents automatically
        from computedfields.resolver import active_resolver
        active_resolver.update_dependent(FixtureChild.objects.all())  # ~10 times faster than updatedata
        self.assertEqual(list(FixtureParent.objects.all().values_list('children_count', flat=True).order_by('pk')), [10, 0, 0])
        self.assertEqual(
            list(FixtureChild.objects.all().values_list('path', flat=True)),
            ['/A#10/' + str(i) for i in range(10)]
        )

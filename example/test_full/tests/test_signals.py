from django.test import TestCase
from ..models import SignalParent, SignalChild
from computedfields.signals import resolver_update_done
from computedfields.models import update_dependent
from contextlib import contextmanager

@contextmanager
def grab_signals(storage):
    def simple_handler(sender, **kwargs):
        changeset = kwargs.get('changeset')
        update_fields = kwargs.get('update_fields')
        data = kwargs.get('data')
        storage.append({
            'changeset': changeset,
            'update_fields': update_fields,
            'data': data
        })
    resolver_update_done.connect(simple_handler)
    yield
    resolver_update_done.disconnect(simple_handler)


class TestSignals(TestCase):
    def test_with_handler(self):
        data = []
        with grab_signals(data):

            # creating parents should be silent
            p1 = SignalParent.objects.create(name='p1')
            p2 = SignalParent.objects.create(name='p2')
            self.assertEqual(data, [])

            # newly creating children should be silent as well
            c1 = SignalChild.objects.create(parent=p1)
            c2 = SignalChild.objects.create(parent=p2)
            c3 = SignalChild.objects.create(parent=p2)
            self.assertEqual(data, [])

            # changing parent name should trigger signal with correct data
            p1.name = 'P1'
            p1.save()
            self.assertEqual(data, [{
                'changeset': p1,
                'update_fields': None,
                'data': {
                  SignalChild: {frozenset(['parentname']): {c1.pk}}
                }
            }])
            data.clear()

            # update_fields should contain correct value
            p2.name = 'P2'
            p2.save(update_fields=['name'])
            self.assertEqual(data, [{
                'changeset': p2,
                'update_fields': frozenset(['name']),
                'data': {
                  SignalChild: {frozenset(['parentname']): {c2.pk, c3.pk}}
                }
            }])
            data.clear()

            # values correctly updated
            c1.refresh_from_db()
            c2.refresh_from_db()
            c3.refresh_from_db()
            self.assertEqual(c1.parentname, 'P1')
            self.assertEqual(c2.parentname, 'P2')
            self.assertEqual(c3.parentname, 'P2')

            # changes from bulk action
            SignalParent.objects.filter(pk__in=[p2.pk]).update(name='P2_CHANGED')
            qs = SignalParent.objects.filter(pk__in=[p2.pk])
            update_dependent(qs, update_fields=['name'])
            self.assertEqual(data, [{
                'changeset': qs,
                'update_fields': frozenset(['name']),
                'data': {
                  SignalChild: {frozenset(['parentname']): {c2.pk, c3.pk}}
                }
            }])
            data.clear()

            # values correctly updated
            c1.refresh_from_db()
            c2.refresh_from_db()
            c3.refresh_from_db()
            self.assertEqual(c1.parentname, 'P1')
            self.assertEqual(c2.parentname, 'P2_CHANGED')
            self.assertEqual(c3.parentname, 'P2_CHANGED')


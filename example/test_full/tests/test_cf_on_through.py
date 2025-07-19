from django.test import TestCase
from ..models import AT, BT, ATBT
from computedfields.handlers import PATCHED_M2M


class CfOnThrough(TestCase):
    def test_add(self):
        PATCHED_M2M.clear()
        at = AT.objects.create(name='aa')
        bt = BT.objects.create(name='bb')
        bt.ats.add(at)
        atbt = ATBT.objects.get(at=at, bt=bt)
        self.assertEqual(atbt.names, 'aabb')
        # change at & bt names
        at.name = 'AA'
        at.save(update_fields=['name'])
        bt.name = 'BB'
        bt.save(update_fields=['name'])
        atbt.refresh_from_db()
        self.assertEqual(atbt.names, 'AABB')

    def test_add_reverse(self):
        PATCHED_M2M.clear()
        at = AT.objects.create(name='aa')
        bt = BT.objects.create(name='bb')
        at.bts.add(bt)
        atbt = ATBT.objects.get(at=at, bt=bt)
        self.assertEqual(atbt.names, 'aabb')
        # another non reverse
        bt2 = BT.objects.create(name='b2')
        bt2.ats.add(at)
        atbt2 = ATBT.objects.get(at=at, bt=bt2)
        self.assertEqual(atbt2.names, 'aab2')

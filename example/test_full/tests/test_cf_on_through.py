from django.test import TestCase
from ..models import AT, BT, ATBT
from computedfields.models import active_resolver, update_dependent


class CfOnThrough(TestCase):
    def setUp(self):
        # explicitly remove the through from the cache
        # to test normal and reverse action
        active_resolver._m2m.pop(ATBT, None)
        self.at = AT.objects.create(name='aa')
        self.bt = BT.objects.create(name='bb')
        self.bt2 = BT.objects.create(name='b2')

    def test_add(self):
        self.bt.ats.add(self.at)
        atbt = ATBT.objects.get(at=self.at, bt=self.bt)
        self.assertEqual(atbt.names, 'aabb')
        # change at & bt names
        self.at.name = 'AA'
        self.at.save(update_fields=['name'])
        self.bt.name = 'BB'
        self.bt.save(update_fields=['name'])
        atbt.refresh_from_db()
        self.assertEqual(atbt.names, 'AABB')

    def test_add_reverse(self):
        self.at.bts.add(self.bt)
        atbt = ATBT.objects.get(at=self.at, bt=self.bt)
        self.assertEqual(atbt.names, 'aabb')
        # another non reverse
        self.bt2.ats.add(self.at)
        atbt2 = ATBT.objects.get(at=self.at, bt=self.bt2)
        self.assertEqual(atbt2.names, 'aab2')

    def test_update_dependent(self):
        self.bt.ats.add(self.at)
        atbt = ATBT.objects.get(at=self.at, bt=self.bt)
        self.assertEqual(atbt.names, 'aabb')
        # change bt & at with bulk action & update_dependent
        BT.objects.all().update(name='BB')
        update_dependent(BT.objects.all())
        atbt.refresh_from_db()
        self.assertEqual(atbt.names, 'aaBB')
        AT.objects.all().update(name='AA')
        update_dependent(AT.objects.all())
        atbt.refresh_from_db()
        self.assertEqual(atbt.names, 'AABB')


from computedfields.models import not_computed
class CfOnThroughNC(TestCase):
    def setUp(self):
        # explicitly remove the through from the cache
        # to test normal and reverse action
        active_resolver._m2m.pop(ATBT, None)
        with not_computed(recover=True):
            self.at = AT.objects.create(name='aa')
            self.bt = BT.objects.create(name='bb')
            self.bt2 = BT.objects.create(name='b2')

    def test_add(self):
        with not_computed(recover=True):
            self.bt.ats.add(self.at)
        atbt = ATBT.objects.get(at=self.at, bt=self.bt)
        self.assertEqual(atbt.names, 'aabb')
        # change at & bt names
        with not_computed(recover=True):
            self.at.name = 'AA'
            self.at.save(update_fields=['name'])
            self.bt.name = 'BB'
            self.bt.save(update_fields=['name'])
        atbt.refresh_from_db()
        self.assertEqual(atbt.names, 'AABB')

    def test_add_reverse(self):
        with not_computed(recover=True):
            self.at.bts.add(self.bt)
        atbt = ATBT.objects.get(at=self.at, bt=self.bt)
        self.assertEqual(atbt.names, 'aabb')
        # another non reverse
        with not_computed(recover=True):
            self.bt2.ats.add(self.at)
        atbt2 = ATBT.objects.get(at=self.at, bt=self.bt2)
        self.assertEqual(atbt2.names, 'aab2')

    def test_update_dependent(self):
        with not_computed(recover=True):
            self.bt.ats.add(self.at)
        atbt = ATBT.objects.get(at=self.at, bt=self.bt)
        self.assertEqual(atbt.names, 'aabb')
        # change bt & at with bulk action & update_dependent
        with not_computed(recover=True):
            BT.objects.all().update(name='BB')
            update_dependent(BT.objects.all())
        atbt.refresh_from_db()
        self.assertEqual(atbt.names, 'aaBB')
        with not_computed(recover=True):
            AT.objects.all().update(name='AA')
            update_dependent(AT.objects.all())
        atbt.refresh_from_db()
        self.assertEqual(atbt.names, 'AABB')

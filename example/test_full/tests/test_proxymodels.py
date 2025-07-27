from django.test import TestCase
from ..models import (ProxyAllLocal, ProxyParent, ProxyChild, ProxySubchild, ProxyXParent, ProxyXChild,
    ProxyMGroup, ProxyMItem, ProxyMUser, ProxyMAgent)
from computedfields.models import get_contributing_fks, update_dependent, preupdate_dependent, active_resolver


class TestProxyModels(TestCase):
    def setUp(self):
        self.p = ProxyParent.objects.create()
        self.c = ProxyChild.objects.create(parent=self.p)
        self.s = ProxySubchild.objects.create(subparent=self.c)

    def test_init(self):
        self.p.refresh_from_db()
        self.assertEqual(self.p.children_count, 1)
        self.assertEqual(self.p.subchildren_count, 1)
        self.c.refresh_from_db()
        self.assertEqual(self.c.subchildren_count, 1)

    def test_copyclone_s(self):
        s2 = self.s
        s2.pk = None
        s2.save()

        self.p.refresh_from_db()
        self.assertEqual(self.p.children_count, 1)
        self.assertEqual(self.p.subchildren_count, 2)
        self.c.refresh_from_db()
        self.assertEqual(self.c.subchildren_count, 2)

    def test_move_children(self):
        other_parent = ProxyParent.objects.create()
        self.c.parent = other_parent
        self.c.save()
        self.p.refresh_from_db()
        self.assertEqual(self.p.children_count, 0)
        other_parent.refresh_from_db()
        self.assertEqual(other_parent.children_count, 1)

    def test_contributing_fk(self):
        # ProxyChild should be in contributing_fks with field 'parent'
        self.assertEqual(ProxyChild in get_contributing_fks(), True)
        self.assertEqual(get_contributing_fks()[ProxyChild], {'parent'})

    def test_computedmodels(self):
        # ProxyChild should be in computed models
        self.assertEqual(ProxyChild in active_resolver.computed_models, True)


class TestProxyModels2(TestCase):
    # the following tests are copied over from test02_fkback.py and adjusted to proxies
    def test_move_children(self):
        p1 = ProxyParent.objects.create()
        p2 = ProxyParent.objects.create()
        c1 = ProxyChild.objects.create(parent=p1)
        c2 = ProxyChild.objects.create(parent=p2)

        # One child per parent
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 1)
        self.assertEqual(p2.children_count, 1)

        # Move the child to another parent
        c2.parent = p1
        c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 2)  # Fine
        self.assertEqual(p2.children_count, 0)  # Assertion error : 1 != 0

    def test_move_bulk(self):
        p1 = ProxyParent.objects.create()
        p2 = ProxyParent.objects.create()
        for i in range(10):
            ProxyChild.objects.create(parent=p1)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 10)
        self.assertEqual(p2.children_count, 0)

        old_relations = preupdate_dependent(ProxyChild.objects.all())
        ProxyChild.objects.all().update(parent=p2)
        update_dependent(ProxyChild.objects.all(), old=old_relations)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 0)
        self.assertEqual(p2.children_count, 10)

    def test_move_subchildren(self):
        p1 = ProxyParent.objects.create()
        p2 = ProxyParent.objects.create()
        c1 = ProxyChild.objects.create(parent=p1)
        c2 = ProxyChild.objects.create(parent=p2)
        s11 = ProxySubchild.objects.create(subparent=c1)
        s12 = ProxySubchild.objects.create(subparent=c1)
        s21 = ProxySubchild.objects.create(subparent=c2)
        s22 = ProxySubchild.objects.create(subparent=c2)

        # One child per parent
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        # Move the child to another parent
        c2.parent = p1
        c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 4)
        self.assertEqual(p2.subchildren_count, 0)

        # move child back
        c2.parent = p2
        c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        # move one subchild
        s22.subparent = c1
        s22.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 3)
        self.assertEqual(p2.subchildren_count, 1)
        self.assertEqual(p1.subchildren_count_proxy, 3)
        self.assertEqual(p2.subchildren_count_proxy, 1)

    def test_move_bulk_subchildren(self):
        p1 = ProxyParent.objects.create()
        p2 = ProxyParent.objects.create()
        c1 = ProxyChild.objects.create(parent=p1)
        c2 = ProxyChild.objects.create(parent=p2)
        s11 = ProxySubchild.objects.create(subparent=c1)
        s12 = ProxySubchild.objects.create(subparent=c1)
        s21 = ProxySubchild.objects.create(subparent=c2)
        s22 = ProxySubchild.objects.create(subparent=c2)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        old_relations = preupdate_dependent(ProxySubchild.objects.all())
        ProxySubchild.objects.all().update(subparent=c2)
        update_dependent(ProxySubchild.objects.all(), old=old_relations)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 0)
        self.assertEqual(p2.subchildren_count, 4)
        self.assertEqual(p1.subchildren_count_proxy, 0)
        self.assertEqual(p2.subchildren_count_proxy, 4)

    def test_x_models(self):
        self.xp1 = ProxyXParent.objects.create()
        self.xp2 = ProxyXParent.objects.create()

        self.xc1 = ProxyXChild.objects.create(parent=self.xp1, value=1)
        self.xc10 = ProxyXChild.objects.create(parent=self.xp1, value=10)
        self.xc100 = ProxyXChild.objects.create(parent=self.xp2, value=100)
        self.xc1000 = ProxyXChild.objects.create(parent=self.xp2, value=1000)

        self.xp1.refresh_from_db()
        self.xp2.refresh_from_db()

        self.assertEqual(self.xp1.children_value, 11)
        self.assertEqual(self.xp2.children_value, 1100)

        self.xc100.parent = self.xp1
        self.xc100.save()
        self.xc1000.parent = self.xp1
        self.xc1000.save()

        self.xp1.refresh_from_db()
        self.xp2.refresh_from_db()

        self.assertEqual(self.xp1.children_value, 1111)
        self.assertEqual(self.xp2.children_value, 0)


class TestProxyModelsM2M(TestCase):
    def setUp(self):
        self.group = ProxyMGroup.objects.create()
        self.user =  ProxyMUser.objects.create()
        self.agent = ProxyMAgent.objects.create(user=self.user)
        self.item = ProxyMItem.objects.create()

    def test_init(self):
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

    def test_add_group_to_user(self):
        self.user.groups.add(self.group)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)   # should not have touched Agent.counter

    def test_add_item_to_user(self):
        self.user.items.add(self.item)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # should have touched Agent.counter once

    # here...
    def test_add_user_to_item(self):
        self.item.users.add(self.user)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # should have touched Agent.counter once

    def test_addremove_group_from_user(self):
        g1 = ProxyMGroup.objects.create()
        g2 = ProxyMGroup.objects.create()
        self.user.groups.add(g1, g2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

        self.user.groups.remove(g1, g2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

    def test_clear_groups_from_user(self):
        g1 = ProxyMGroup.objects.create()
        g2 = ProxyMGroup.objects.create()
        self.user.groups.add(g1, g2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

        self.user.groups.clear()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

    def test_addremove_item_from_user(self):
        i1 = ProxyMItem.objects.create()
        i2 = ProxyMItem.objects.create()
        self.user.items.add(i1, i2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # one touch

        self.user.items.remove(i1, i2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 3)   # another touch

    def test_clear_items_from_user(self):
        i1 = ProxyMItem.objects.create()
        i2 = ProxyMItem.objects.create()
        self.user.items.add(i1, i2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # one touch

        self.user.items.clear()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 3)   # another touch

    def test_addremove_user_from_item(self):
        u1 = ProxyMUser.objects.create()
        a1 = ProxyMAgent.objects.create(user=u1)
        u2 = ProxyMUser.objects.create()
        a2 = ProxyMAgent.objects.create(user=u2)
        self.item.users.add(u1, u2)
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.counter, 2)   # one touch
        self.assertEqual(a1.counter, 2)   # one touch

        self.item.users.remove(u1, u2)
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.counter, 3)   # another touch
        self.assertEqual(a1.counter, 3)   # another touch

    def test_clear_users_from_item(self):
        u1 = ProxyMUser.objects.create()
        a1 = ProxyMAgent.objects.create(user=u1)
        u2 = ProxyMUser.objects.create()
        a2 = ProxyMAgent.objects.create(user=u2)
        self.item.users.add(u1, u2)
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.counter, 2)   # one touch
        self.assertEqual(a1.counter, 2)   # one touch

        self.item.users.clear()
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.counter, 3)   # another touch
        self.assertEqual(a1.counter, 3)   # another touch


class TestProxyModelsLocal(TestCase):
    def setUp(self):
        self.obj = ProxyAllLocal.objects.create(f1='Hello')
    
    def test_init(self):
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'HELLO')
        self.assertEqual(self.obj.f3, 'HELLOF3')
        self.assertEqual(self.obj.f4, 'HELLOF4')
        self.assertEqual(self.obj.f5, 'HELLOF4F5')

    def test_change_f1(self):
        # full save
        self.obj.f1 = 'a'
        self.obj.save()
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'A')
        self.assertEqual(self.obj.f3, 'AF3')
        self.assertEqual(self.obj.f4, 'AF4')
        self.assertEqual(self.obj.f5, 'AF4F5')
        # with update_fields
        self.obj.f1 = 'b'
        self.obj.save(update_fields=['f1'])
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'B')
        self.assertEqual(self.obj.f3, 'BF3')
        self.assertEqual(self.obj.f4, 'BF4')
        self.assertEqual(self.obj.f5, 'BF4F5')

    def test_change_inject(self):
        # full save
        self.obj.inject = 'xxx'
        self.obj.save()
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'HELLO')
        self.assertEqual(self.obj.f3, 'HELLOF3')
        self.assertEqual(self.obj.f4, 'HELLOxxx')
        self.assertEqual(self.obj.f5, 'HELLOxxxF5')
        # with update_fields
        self.obj.inject = 'zzz'
        self.obj.save(update_fields=['inject'])
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'HELLO')
        self.assertEqual(self.obj.f3, 'HELLOF3')
        self.assertEqual(self.obj.f4, 'HELLOzzz')
        self.assertEqual(self.obj.f5, 'HELLOzzzF5')


from computedfields.models import not_computed
class TestProxyModelsNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.p = ProxyParent.objects.create()
            self.c = ProxyChild.objects.create(parent=self.p)
            self.s = ProxySubchild.objects.create(subparent=self.c)

    def test_init(self):
        self.p.refresh_from_db()
        self.assertEqual(self.p.children_count, 1)
        self.assertEqual(self.p.subchildren_count, 1)
        self.c.refresh_from_db()
        self.assertEqual(self.c.subchildren_count, 1)

    def test_copyclone_s(self):
        with not_computed(recover=True):
            s2 = self.s
            s2.pk = None
        s2.save()

        self.p.refresh_from_db()
        self.assertEqual(self.p.children_count, 1)
        self.assertEqual(self.p.subchildren_count, 2)
        self.c.refresh_from_db()
        self.assertEqual(self.c.subchildren_count, 2)

    def test_move_children(self):
        with not_computed(recover=True):
            other_parent = ProxyParent.objects.create()
            self.c.parent = other_parent
            self.c.save()
        self.p.refresh_from_db()
        self.assertEqual(self.p.children_count, 0)
        other_parent.refresh_from_db()
        self.assertEqual(other_parent.children_count, 1)

    def test_contributing_fk(self):
        # ProxyChild should be in contributing_fks with field 'parent'
        self.assertEqual(ProxyChild in get_contributing_fks(), True)
        self.assertEqual(get_contributing_fks()[ProxyChild], {'parent'})

    def test_computedmodels(self):
        # ProxyChild should be in computed models
        self.assertEqual(ProxyChild in active_resolver.computed_models, True)


class TestProxyModels2NC(TestCase):
    # the following tests are copied over from test02_fkback.py and adjusted to proxies
    def test_move_children(self):
        with not_computed(recover=True):
            p1 = ProxyParent.objects.create()
            p2 = ProxyParent.objects.create()
            c1 = ProxyChild.objects.create(parent=p1)
            c2 = ProxyChild.objects.create(parent=p2)

        # One child per parent
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 1)
        self.assertEqual(p2.children_count, 1)

        # Move the child to another parent
        with not_computed(recover=True):
            c2.parent = p1
            c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 2)  # Fine
        self.assertEqual(p2.children_count, 0)  # Assertion error : 1 != 0

    def test_move_bulk(self):
        with not_computed(recover=True):
            p1 = ProxyParent.objects.create()
            p2 = ProxyParent.objects.create()
            for i in range(10):
                ProxyChild.objects.create(parent=p1)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 10)
        self.assertEqual(p2.children_count, 0)

        with not_computed(recover=True):
            old_relations = preupdate_dependent(ProxyChild.objects.all())
            ProxyChild.objects.all().update(parent=p2)
            update_dependent(ProxyChild.objects.all(), old=old_relations)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 0)
        self.assertEqual(p2.children_count, 10)

    def test_move_subchildren(self):
        with not_computed(recover=True):
            p1 = ProxyParent.objects.create()
            p2 = ProxyParent.objects.create()
            c1 = ProxyChild.objects.create(parent=p1)
            c2 = ProxyChild.objects.create(parent=p2)
            s11 = ProxySubchild.objects.create(subparent=c1)
            s12 = ProxySubchild.objects.create(subparent=c1)
            s21 = ProxySubchild.objects.create(subparent=c2)
            s22 = ProxySubchild.objects.create(subparent=c2)

        # One child per parent
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        with not_computed(recover=True):
            # Move the child to another parent
            c2.parent = p1
            c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 4)
        self.assertEqual(p2.subchildren_count, 0)

        with not_computed(recover=True):
            # move child back
            c2.parent = p2
            c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        with not_computed(recover=True):
            # move one subchild
            s22.subparent = c1
            s22.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 3)
        self.assertEqual(p2.subchildren_count, 1)
        self.assertEqual(p1.subchildren_count_proxy, 3)
        self.assertEqual(p2.subchildren_count_proxy, 1)

    def test_move_bulk_subchildren(self):
        with not_computed(recover=True):
            p1 = ProxyParent.objects.create()
            p2 = ProxyParent.objects.create()
            c1 = ProxyChild.objects.create(parent=p1)
            c2 = ProxyChild.objects.create(parent=p2)
            s11 = ProxySubchild.objects.create(subparent=c1)
            s12 = ProxySubchild.objects.create(subparent=c1)
            s21 = ProxySubchild.objects.create(subparent=c2)
            s22 = ProxySubchild.objects.create(subparent=c2)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        with not_computed(recover=True):
            old_relations = preupdate_dependent(ProxySubchild.objects.all())
            ProxySubchild.objects.all().update(subparent=c2)
            update_dependent(ProxySubchild.objects.all(), old=old_relations)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 0)
        self.assertEqual(p2.subchildren_count, 4)
        self.assertEqual(p1.subchildren_count_proxy, 0)
        self.assertEqual(p2.subchildren_count_proxy, 4)

    def test_x_models(self):
        with not_computed(recover=True):
            self.xp1 = ProxyXParent.objects.create()
            self.xp2 = ProxyXParent.objects.create()

            self.xc1 = ProxyXChild.objects.create(parent=self.xp1, value=1)
            self.xc10 = ProxyXChild.objects.create(parent=self.xp1, value=10)
            self.xc100 = ProxyXChild.objects.create(parent=self.xp2, value=100)
            self.xc1000 = ProxyXChild.objects.create(parent=self.xp2, value=1000)

        self.xp1.refresh_from_db()
        self.xp2.refresh_from_db()

        self.assertEqual(self.xp1.children_value, 11)
        self.assertEqual(self.xp2.children_value, 1100)

        with not_computed(recover=True):
            self.xc100.parent = self.xp1
            self.xc100.save()
            self.xc1000.parent = self.xp1
            self.xc1000.save()

        self.xp1.refresh_from_db()
        self.xp2.refresh_from_db()

        self.assertEqual(self.xp1.children_value, 1111)
        self.assertEqual(self.xp2.children_value, 0)


class TestProxyModelsM2MNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.group = ProxyMGroup.objects.create()
            self.user =  ProxyMUser.objects.create()
            self.agent = ProxyMAgent.objects.create(user=self.user)
            self.item = ProxyMItem.objects.create()
        self.group.refresh_from_db()
        self.user.refresh_from_db()
        self.agent.refresh_from_db()
        self.item.refresh_from_db()

    def test_init(self):
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

    def test_add_group_to_user(self):
        with not_computed(recover=True):
            self.user.groups.add(self.group)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)   # should not have touched Agent.counter

    def test_add_item_to_user(self):
        with not_computed(recover=True):
            self.user.items.add(self.item)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # should have touched Agent.counter once

    # here...
    def test_add_user_to_item(self):
        with not_computed(recover=True):
            self.item.users.add(self.user)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # should have touched Agent.counter once

    def test_addremove_group_from_user(self):
        with not_computed(recover=True):
            g1 = ProxyMGroup.objects.create()
            g2 = ProxyMGroup.objects.create()
            self.user.groups.add(g1, g2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

        with not_computed(recover=True):
            self.user.groups.remove(g1, g2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

    def test_clear_groups_from_user(self):
        with not_computed(recover=True):
            g1 = ProxyMGroup.objects.create()
            g2 = ProxyMGroup.objects.create()
            self.user.groups.add(g1, g2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

        with not_computed(recover=True):
            self.user.groups.clear()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

    def test_addremove_item_from_user(self):
        with not_computed(recover=True):
            i1 = ProxyMItem.objects.create()
            i2 = ProxyMItem.objects.create()
            self.user.items.add(i1, i2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # one touch

        with not_computed(recover=True):
            self.user.items.remove(i1, i2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 3)   # another touch

    def test_clear_items_from_user(self):
        with not_computed(recover=True):
            i1 = ProxyMItem.objects.create()
            i2 = ProxyMItem.objects.create()
            self.user.items.add(i1, i2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # one touch

        with not_computed(recover=True):
            self.user.items.clear()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 3)   # another touch

    def test_addremove_user_from_item(self):
        with not_computed(recover=True):
            u1 = ProxyMUser.objects.create()
            a1 = ProxyMAgent.objects.create(user=u1)
            u2 = ProxyMUser.objects.create()
            a2 = ProxyMAgent.objects.create(user=u2)
            self.item.users.add(u1, u2)
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.counter, 1)   # one less than above (only called once from recover)
        self.assertEqual(a2.counter, 1)   # one touch

        with not_computed(recover=True):
            self.item.users.remove(u1, u2)
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.counter, 2)   # another touch
        self.assertEqual(a2.counter, 2)   # another touch

    def test_clear_users_from_item(self):
        with not_computed(recover=True):
            u1 = ProxyMUser.objects.create()
            a1 = ProxyMAgent.objects.create(user=u1)
            u2 = ProxyMUser.objects.create()
            a2 = ProxyMAgent.objects.create(user=u2)
            self.item.users.add(u1, u2)
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.counter, 1)   # one touch
        self.assertEqual(a2.counter, 1)   # one touch

        with not_computed(recover=True):
            self.item.users.clear()
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.counter, 2)   # another touch
        self.assertEqual(a2.counter, 2)   # another touch


class TestProxyModelsLocalNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.obj = ProxyAllLocal.objects.create(f1='Hello')
    
    def test_init(self):
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'HELLO')
        self.assertEqual(self.obj.f3, 'HELLOF3')
        self.assertEqual(self.obj.f4, 'HELLOF4')
        self.assertEqual(self.obj.f5, 'HELLOF4F5')

    def test_change_f1(self):
        # full save
        with not_computed(recover=True):
            self.obj.f1 = 'a'
            self.obj.save()
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'A')
        self.assertEqual(self.obj.f3, 'AF3')
        self.assertEqual(self.obj.f4, 'AF4')
        self.assertEqual(self.obj.f5, 'AF4F5')
        # with update_fields
        with not_computed(recover=True):
            self.obj.f1 = 'b'
            self.obj.save(update_fields=['f1'])
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'B')
        self.assertEqual(self.obj.f3, 'BF3')
        self.assertEqual(self.obj.f4, 'BF4')
        self.assertEqual(self.obj.f5, 'BF4F5')

    def test_change_inject(self):
        # full save
        with not_computed(recover=True):
            self.obj.inject = 'xxx'
            self.obj.save()
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'HELLO')
        self.assertEqual(self.obj.f3, 'HELLOF3')
        self.assertEqual(self.obj.f4, 'HELLOxxx')
        self.assertEqual(self.obj.f5, 'HELLOxxxF5')
        # with update_fields
        with not_computed(recover=True):
            self.obj.inject = 'zzz'
            self.obj.save(update_fields=['inject'])
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.f2, 'HELLO')
        self.assertEqual(self.obj.f3, 'HELLOF3')
        self.assertEqual(self.obj.f4, 'HELLOzzz')
        self.assertEqual(self.obj.f5, 'HELLOzzzF5')

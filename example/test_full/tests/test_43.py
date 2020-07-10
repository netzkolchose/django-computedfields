from django.test import TestCase
from ..models import MAgent, MUser, MItem, MGroup


class TestBetterM2M(TestCase):
    def setUp(self):
        self.group = MGroup.objects.create()
        self.user = MUser.objects.create()
        self.agent = MAgent.objects.create(user=self.user)
        self.item = MItem.objects.create()

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

    def test_add_user_to_item(self):
        self.item.users.add(self.user)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # should have touched Agent.counter once

    def test_addremove_group_from_user(self):
        g1 = MGroup.objects.create()
        g2 = MGroup.objects.create()
        self.user.groups.add(g1, g2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

        self.user.groups.remove(g1, g2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

    def test_clear_groups_from_user(self):
        g1 = MGroup.objects.create()
        g2 = MGroup.objects.create()
        self.user.groups.add(g1, g2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

        self.user.groups.clear()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 1)

    def test_addremove_item_from_user(self):
        i1 = MItem.objects.create()
        i2 = MItem.objects.create()
        self.user.items.add(i1, i2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # one touch

        self.user.items.remove(i1, i2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 3)   # another touch

    def test_clear_items_from_user(self):
        i1 = MItem.objects.create()
        i2 = MItem.objects.create()
        self.user.items.add(i1, i2)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 2)   # one touch

        self.user.items.clear()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.counter, 3)   # another touch

    def test_addremove_user_from_item(self):
        u1 = MUser.objects.create()
        a1 = MAgent.objects.create(user=u1)
        u2 = MUser.objects.create()
        a2 = MAgent.objects.create(user=u2)
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
        u1 = MUser.objects.create()
        a1 = MAgent.objects.create(user=u1)
        u2 = MUser.objects.create()
        a2 = MAgent.objects.create(user=u2)
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

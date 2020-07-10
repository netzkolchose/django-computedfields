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
        # should not have touched Agent.counter
        self.assertEqual(self.agent.counter, 1)

    def test_add_item_to_user(self):
        self.user.items.add(self.item)

        self.agent.refresh_from_db()
        # should have touched Agent.counter once
        self.assertEqual(self.agent.counter, 2)

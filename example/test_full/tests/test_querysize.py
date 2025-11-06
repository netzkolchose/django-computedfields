from django.test import TestCase, override_settings
from ..models import Querysize, EmailUser
from computedfields.models import active_resolver
from computedfields.settings import settings as settings


class TestQuerysize(TestCase):
    def test_default(self):
        self.assertEqual(
            active_resolver.get_querysize(Querysize, frozenset(['default'])),
            settings.COMPUTEDFIELDS_QUERYSIZE
        )
        self.assertEqual(
            active_resolver.get_querysize(EmailUser),
            settings.COMPUTEDFIELDS_QUERYSIZE
        )

    @override_settings(COMPUTEDFIELDS_QUERYSIZE=10000)
    def test_default_altered(self):
        self.assertEqual(settings.COMPUTEDFIELDS_QUERYSIZE, 10000)
        self.assertEqual(
            active_resolver.get_querysize(Querysize, frozenset(['default']), 10000),
            settings.COMPUTEDFIELDS_QUERYSIZE
        )

    def test_lowest_in_updates(self):
        # the lowest local cf value always wins
        self.assertEqual(active_resolver.get_querysize(Querysize), 1)
        self.assertEqual(active_resolver.get_querysize(Querysize, None, 10000), 1)
        # q10 limits
        self.assertEqual(active_resolver.get_querysize(Querysize, frozenset(['default', 'q10'])), 10)
        self.assertEqual(active_resolver.get_querysize(Querysize, frozenset(['default', 'q10']), 10000), 10)
        self.assertEqual(active_resolver.get_querysize(Querysize, frozenset(['default', 'q10', 'q100', 'q1000'])), 10)
        # q100 limits
        self.assertEqual(active_resolver.get_querysize(Querysize, frozenset(['default', 'q100'])), 100)
        self.assertEqual(active_resolver.get_querysize(Querysize, frozenset(['default', 'q100', 'q1000']), 10000), 100)
        # q1000 limits
        self.assertEqual(active_resolver.get_querysize(Querysize, frozenset(['default', 'q1000']), 10000), 1000)

    def test_chain(self):
        # c_10_100 can do 100, but is limited by prev q10
        mro = active_resolver.get_local_mro(Querysize, frozenset(['q10']))
        self.assertEqual(active_resolver.get_querysize(Querysize, frozenset(mro), 10000), 1)

    def test_low_override_wins(self):
        # q1000 wins
        self.assertEqual(active_resolver.get_querysize(Querysize, frozenset(['default', 'q1000']), 10000), 1000)
        # override wins
        self.assertEqual(active_resolver.get_querysize(Querysize, frozenset(['default', 'q1000']), 10), 10)

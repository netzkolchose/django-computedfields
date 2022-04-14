from .base import GenericModelTestBase
from computedfields.models import active_resolver
from computedfields.graph import CycleEdgeException
from django.core.management import call_command
from django.core.management.base import CommandError
from io import StringIO
import pickle
from django.conf import settings
import os


def strip_proxy_models(map_data):
    cleaned = {}
    for k, v in map_data.items():
        if k._meta.proxy:
            continue
        cleaned[k] = v
    return cleaned


class CommandTests(GenericModelTestBase):
    """
    Tests the management commands.
    """
    def setUp(self):
        self.setDeps({
            # deps only to itself
            'B': {'depends': [('self', ['name'])],
                  'func': lambda self: self.name},
            # one fk step deps to comp field
            'C': {'depends': [('self', ['name']), ('f_cb', ['comp'])],
                  'func': lambda self: self.name + self.f_cb.comp},
            'D': {'depends': [('self', ['name']), ('f_dc', ['comp'])],
                  'func': lambda self: self.name + self.f_dc.comp},
            # multi fk steps deps to non comp field
            'E': {'depends': [('self', ['name']), ('f_ed.f_dc.f_cb.f_ba', ['name'])],
                  'func': lambda self: self.name + self.f_ed.f_dc.f_cb.f_ba.name},
            # multi fk steps deps to comp field
            'F': {'depends': [('self', ['name']), ('f_fe.f_ed.f_dc.f_cb', ['name'])],
                  'func': lambda self: self.name + self.f_fe.f_ed.f_dc.f_cb.name}
        })

    def tearDown(self):
        self.resetDeps()

    def test_rendergraph(self):
        # TODO: test for output
        self.assertEqual(self.graph.is_cyclefree, True)
        call_command('rendergraph', 'output', verbosity=0)
        os.remove('output.pdf')

    def test_rendergraph_with_cycle(self):
        import sys

        # normally raises due to get_nodepaths() in _resolve_dependencies()
        self.assertRaises(
            CycleEdgeException,
            lambda: self.setDeps({
                    'A': {'depends': [('f_ag', ['comp'])]},
                    'G': {'depends': [('f_ga', ['comp'])]},
            })
        )

        # does not raise anymore with COMPUTEDFIELDS_ALLOW_RECURSION
        setattr(settings, 'COMPUTEDFIELDS_ALLOW_RECURSION', True)
        self.setDeps({
            'A': {'depends': [('f_ag', ['comp'])]},
            'G': {'depends': [('f_ga', ['comp'])]},
        })
        self.assertEqual(active_resolver._graph.is_cyclefree, False)
        stdout = sys.stdout
        sys.stdout = StringIO()
        call_command('rendergraph', 'output', verbosity=0)
        # should have printed cycle info on stdout
        self.assertIn('Warning -  1 cycles in dependencies found:', sys.stdout.getvalue())
        sys.stdout = stdout
        setattr(settings, 'COMPUTEDFIELDS_ALLOW_RECURSION', False)

    def test_updatedata(self):
        # TODO: advanced test case
        self.models.A(name='a').save()
        call_command('updatedata', verbosity=0)

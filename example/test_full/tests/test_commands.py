# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from .base import GenericModelTestBase
from computedfields.models import ComputedFieldsModelType
from computedfields.graph import CycleNodeException
from django.core.management import call_command
from django.utils.six.moves import cStringIO


class CommandTests(GenericModelTestBase):
    """
    Tests the management commands.
    """
    def setUp(self):
        self.setDeps({
            # deps only to itself
            'B': {'func': lambda self: self.name},
            # one fk step deps to comp field
            'C': {'depends': ['f_cb#comp'],
                  'func': lambda self: self.name + self.f_cb.comp},
            'D': {'depends': ['f_dc#comp'],
                  'func': lambda self: self.name + self.f_dc.comp},
            # multi fk steps deps to non comp field
            'E': {'depends': ['f_ed.f_dc.f_cb.f_ba#name'],
                  'func': lambda self: self.name + self.f_ed.f_dc.f_cb.f_ba.name},
            # multi fk steps deps to comp field
            'F': {'depends': ['f_fe.f_ed.f_dc.f_cb#name'],
                  'func': lambda self: self.name + self.f_fe.f_ed.f_dc.f_cb.name}
        })

    def tearDown(self):
        self.resetDeps()

    def test_rendergraph(self):
        # TODO: test for output
        self.assertEqual(self.graph.is_cyclefree, True)
        call_command('rendergraph', 'output', verbosity=0)

    def test_rendergraph_with_cycle(self):
        import sys

        # raises due to get_nodepaths() in _resolve_dependencies()
        self.assertRaises(
            CycleNodeException,
            lambda: self.setDeps({
                    'A': {'depends': ['f_ag#comp']},
                    'G': {'depends': ['f_ga#comp']},
                })
        )
        self.assertEqual(ComputedFieldsModelType._graph.is_cyclefree, False)
        stdout = sys.stdout
        sys.stdout = cStringIO()
        call_command('rendergraph', 'output', verbosity=0)
        # should have printed cycle info on stdout
        self.assertIn('Warning -  1 cycles in dependencies found:', sys.stdout.getvalue())
        sys.stdout = stdout

    def test_updatedata(self):
        # TODO: advanced test case
        self.models.A(name='a').save()
        call_command('updatedata', verbosity=0)

    def test_createmap(self):
        call_command('createmap', verbosity=0)

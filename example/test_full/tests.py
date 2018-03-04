# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.test import TestCase
import models as models_module
from .models import MODELS
from computedfields.models import ComputedFieldsModelType
from computedfields.graph import CycleNodeException
from django.core.management import call_command

# access comp field stuff
# models.A._computed_fields['comp']._computed
# --> {u'attr': 'comp', u'func': <function <lambda> at 0x7fa0186e7140>, u'kwargs': {'depends': []}}

# update ComputedFieldsModelType._computed_models
# {<class 'test_full.models.A'>, {}}
# --> {<class 'test_full.models.A'>, {'comp': [dep list]}}

# rerun resolver
# ComputedFieldsModelType._resolve_dependencies()

# load fixtures in test:
# from django.core.management import call_command
# call_command('loaddata', 'fixtures/myfixture', verbosity=0)


class GenericModelTestBase(TestCase):
    models = models_module

    def setDeps(self, mapping):
        models = ComputedFieldsModelType._computed_models
        for modelname, data in mapping.items():
            if data.get('depends'):
                models[MODELS[modelname]] = {'comp': data.get('depends')}
            if data.get('func'):
                MODELS[modelname]._computed_fields['comp']._computed['func'] = data.get('func')
        ComputedFieldsModelType._resolve_dependencies()
        self.graph = ComputedFieldsModelType._graph
        #self.graph.view()

    def resetDeps(self):
        models = ComputedFieldsModelType._computed_models
        for model in models:
            models[model] = {}
            for fielddata in model._computed_fields.values():
                fielddata._computed['func'] = lambda x: ''
        self.graph = None


class CommandTests(GenericModelTestBase):
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
        self.assertEqual(self.graph.is_cyclefree, True)
        call_command('rendergraph', 'output', verbosity=0)

    def test_rendergraph_with_cycle(self):
        import sys
        try:
            import StringIO
        except ImportError:
            from io import StringIO

        # raises due to remove_redundant_paths() in _resolve_dependencies()
        self.assertRaises(
            CycleNodeException,
            lambda: self.setDeps({
                    'A': {'depends': ['f_ag#comp']},
                    'G': {'depends': ['f_ga#comp']},
                })
        )
        self.assertEqual(ComputedFieldsModelType._graph.is_cyclefree, False)
        stdout = sys.stdout
        sys.stdout = StringIO.StringIO()
        call_command('rendergraph', 'output', verbosity=0)
        # should have printed cycle info on stdout
        self.assertEqual(
            'Warning -  1 cycles in dependencies found:' in sys.stdout.getvalue(), True)
        sys.stdout = stdout

    def test_updatedata(self):
        self.models.A(name='a').save()
        call_command('updatedata', verbosity=0)


class ForeignKeyDependencies(GenericModelTestBase):
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
                  'func': lambda self: self.name + self.f_fe.f_ed.f_dc.f_cb.name},
            # multiple mixed deps
            'G': {'depends': ['f_gf#comp', 'f_gf.f_fe.f_ed#name'],
                  'func': lambda self: self.name + self.f_gf.comp + self.f_gf.f_fe.f_ed.name}
        })
        # test data - fk chained objects
        self.a = self.models.A(name='a')
        self.a.save()
        self.b = self.models.B(name='b', f_ba=self.a)
        self.b.save()
        self.c = self.models.C(name='c', f_cb=self.b)
        self.c.save()
        self.d = self.models.D(name='d', f_dc=self.c)
        self.d.save()
        self.e = self.models.E(name='e', f_ed=self.d)
        self.e.save()
        self.f = self.models.F(name='f', f_fe=self.e)
        self.f.save()
        self.g = self.models.G(name='g', f_gf=self.f)
        self.g.save()

    def tearDown(self):
        self.resetDeps()

    def test_insert_test(self):
        self.assertEqual(self.b.comp, 'b')
        self.assertEqual(self.c.comp, 'cb')
        self.assertEqual(self.d.comp, 'dcb')

    def test_bubbling_updates(self):
        self.b.name = 'B'
        self.b.save()
        # need to reload data from db
        self.c.refresh_from_db()
        self.d.refresh_from_db()
        self.assertEqual(self.b.comp, 'B')
        self.assertEqual(self.c.comp, 'cB')
        self.assertEqual(self.d.comp, 'dcB')

    def test_bubbling_update_without_refresh_on_save(self):
        # bubbling update without refresh should work on save
        self.b.name = 'B'
        self.b.save()
        self.c.name = 'C'
        self.c.save()
        self.d.name = 'D'
        self.d.save()
        self.assertEqual(self.b.comp, 'B')
        self.assertEqual(self.c.comp, 'CB')
        self.assertEqual(self.d.comp, 'DCB')

    def test_fk_over_multiple_models_insert(self):
        self.assertEqual(self.e.comp, 'ea')
        self.assertEqual(self.f.comp, 'fb')

    def test_fk_over_multiple_models_update(self):
        self.assertEqual(self.e.comp, 'ea')
        new_a = self.models.A(name='A')
        new_a.save()
        self.b.f_ba = new_a
        self.b.name = 'B'
        self.b.save()
        self.e.refresh_from_db()
        self.f.refresh_from_db()
        self.assertEqual(self.e.comp, 'eA')
        self.assertEqual(self.f.comp, 'fB')

    def test_multiple_fk_deps_insert(self):
        self.assertEqual(self.g.comp, 'gfbd')

    def test_multiple_fk_deps_update(self):
        # removed: set([Edge test_full.e.#-test_full.g.comp, Edge test_full.d.#-test_full.g.comp])
        # G.comp depends: ['f_gf#comp', 'f_gf.f_fe.f_ed#name']
        #self.graph.view()
        self.assertEqual(self.g.comp, 'gfbd')
        self.f.name = 'F'
        self.f.save()
        self.g.refresh_from_db()
        self.assertEqual(self.g.comp, 'gFbd')
        self.d.name = 'D'
        self.d.save()
        self.g.refresh_from_db()
        self.assertEqual(self.g.comp, 'gFbD')


def helper(self):  # 'depends': ['f_ab.bc_f.f_cd.db_f#comp']
    res = ''
    b = self.f_ab
    if b:
        all_c = b.bc_f.all()
        if all_c:
            all_d = [el.f_cd for el in all_c]
            if filter(bool, all_d):
                for el in all_d:
                    for sub in el.db_f.all():
                        res += sub.name
    return res


class Simple(GenericModelTestBase):
    def setUp(self):
        #self.setDeps({
        #    'A': {'func': lambda self: self.name},
        #    'C': {'depends': ['f_cb.f_ba#comp'],
        #          'func': lambda self: self.name + self.f_cb.f_ba.comp}
        #})
        #self.setDeps({
        #    'A': {'depends': ['ab_f.bc_f#comp'], 'func': lambda self: self.name},
        #    'C': {'func': lambda self: self.name}
        #})
        #self.setDeps({
        #    'A': {'depends': ['ab_f.bc_f.f_cd#name'], 'func': lambda self: self.name},
        #    'C': {'func': lambda self: self.name}
        #})  # --> [['attrs', 'f_ba', 'f_cb'], ['search', u'f_cd']]
            # --> models.C.filter(f_cd=d)#f_cb.f_ba#save
        #self.setDeps({
        #    'D': {'depends': ['f_dc.f_cb.ba_f#name'], 'func': lambda self: self.name},
        #    'C': {'func': lambda self: self.name}
        #})  # --> [['search', u'f_dc', u'f_cb'], ['attrs', 'f_ab']]
            # --> models.D.objects.filter(f_dc__f_cb=a.f_ab)#save
        self.setDeps({
            'A': {'depends': ['f_ab.bc_f.f_cd.db_f#comp'],
                  'func': helper},
            'C': {'func': lambda self: self.name}
        }) # --> [['search', u'f_ab'], ['attrs', 'f_cb'], ['search', u'f_cd'], ['attrs', 'f_bd']]
        # --> A.filter(f_ab__in=C.filter(f_cd=b.f_bd)#f_cb.pk)#save

        # test data - fk chained objects
        self.a = self.models.A(name='a')
        self.a.save()
        self.b = self.models.B(name='b', f_ba=self.a)
        self.b.save()
        self.a.f_ab = self.b
        self.a.save()
        self.c = self.models.C(name='c', f_cb=self.b)
        self.c.save()
        self.d = self.models.D(name='d', f_dc=self.c)
        self.d.save()
        self.c.f_cd = self.d
        self.c.save()
        self.b.f_bd = self.d
        self.b.save()

    def test_simple(self):
        self.a.refresh_from_db()
        self.assertEqual(self.a.comp, self.b.name)
        self.b.name = 'B'
        self.b.save()
        self.a.refresh_from_db()
        self.assertEqual(self.a.comp, self.b.name)

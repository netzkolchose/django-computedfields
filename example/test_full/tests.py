# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.test import TestCase
import models as models_module
from .models import MODELS
from computedfields.models import ComputedFieldsModelType

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
            for field, values in data.items():
                if values.get('depends'):
                    models[MODELS[modelname]] = {field: values.get('depends')}
                if values.get('func'):
                    MODELS[modelname]._computed_fields[field]._computed['func'] = values.get('func')
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


class ForeignKeyDependencies(GenericModelTestBase):
    def setUp(self):
        self.setDeps({
            # deps only to itself
            'B': {'comp': {
                    'func': lambda self: self.name
                }
            },
            # one fk step deps to comp field
            'C': {'comp': {
                    'depends': ['f_cb#comp'],
                    'func': lambda self: self.name + self.f_cb.comp
                }
            },
            'D': {'comp': {
                    'depends': ['f_dc#comp'],
                    'func': lambda self: self.name + self.f_dc.comp
                }
            },
            # multi fk steps deps to non comp field
            'E': {'comp': {
                    'depends': ['f_ed.f_dc.f_cb.f_ba#name'],
                    'func': lambda self: self.name + self.f_ed.f_dc.f_cb.f_ba.name
                }
            },
            # multi fk steps deps to comp field
            'F': {'comp': {
                    'depends': ['f_fe.f_ed.f_dc.f_cb#name'],
                    'func': lambda self: self.name + self.f_fe.f_ed.f_dc.f_cb.name
                }
            }
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

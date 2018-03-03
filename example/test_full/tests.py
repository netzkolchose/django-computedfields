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


class GenericModelTestCaseBase(TestCase):
    def parse(self, mapping):
        models = ComputedFieldsModelType._computed_models
        for modelname, data in mapping.iteritems():
            for field, values in data.iteritems():
                if values.get('depends'):
                    models[MODELS[modelname]] = {field: values.get('depends')}
                if values.get('func'):
                    MODELS[modelname]._computed_fields[field]._computed['func'] = values.get('func')
        ComputedFieldsModelType._resolve_dependencies()
        self.models = models_module

    def reset(self):
        models = ComputedFieldsModelType._computed_models
        for model in models:
            models[model] = {}
            for fielddata in model._computed_fields.values():
                fielddata._computed['func'] = lambda x: ''


class MultipleFKDependenciesTestCase(GenericModelTestCaseBase):
    def setUp(self):
        self.parse({
            'B': {'comp': {
                    'func': lambda self: self.name
                }
            },
            'C': {'comp': {
                    'depends': ['f_cb#comp'],
                    'func': lambda self: self.name + self.f_cb.comp
                }
            },
            'D': {'comp': {
                    'depends': ['f_dc#comp'],
                    'func': lambda self: self.name + self.f_dc.comp
                }
            }
        })

    def tearDown(self):
        self.reset()

    def test_simple_fk_relations(self):
        b = self.models.B(name='b')
        b.save()
        c = self.models.C(name='c', f_cb=b)
        c.save()
        d = self.models.D(name='d', f_dc=c)
        d.save()
        # insert test
        self.assertEqual(c.comp, 'cb')
        self.assertEqual(d.comp, 'dcb')
        b.name = 'B'
        b.save()
        c.refresh_from_db()
        d.refresh_from_db()
        # bubbling updates
        self.assertEqual(c.comp, 'cB')
        self.assertEqual(d.comp, 'dcB')
        c.name = 'C'
        c.save()
        # this should work without refresh
        d.name = 'D'
        d.save()
        self.assertEqual(d.comp, 'DCB')

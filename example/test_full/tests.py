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
        for modelname, data in mapping.items():
            for field, values in data.items():
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


class MultipleFKDependencies(GenericModelTestCaseBase):
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
        # test data
        self.b = self.models.B(name='b')
        self.b.save()
        self.c = self.models.C(name='c', f_cb=self.b)
        self.c.save()
        self.d = self.models.D(name='d', f_dc=self.c)
        self.d.save()

    def tearDown(self):
        self.reset()

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

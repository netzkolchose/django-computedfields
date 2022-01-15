"""
Some tests for the resolver.

Note - the resolver gets mainly tested indirectly by all other tests.
Tests here are for rare branches and exception traps, that should not
happen during normal operation mode.
"""
import os
from django.test import TestCase
from django.db.models.signals import class_prepared
from django.conf import settings
from computedfields.resolver import Resolver, active_resolver, ResolverException
from .. import models


def generate_computedmodel(resolver, modelname, func, wrong_base=False):
    from django.db import models
    from computedfields.models import ComputedFieldsModel
    field = resolver.computed(models.CharField(max_length=32), depends=[('self', ['name'])])(func)
    return field, type(
      modelname,
      (models.Model if wrong_base else ComputedFieldsModel,),
      {
          '__module__': 'test_full.models',
          'name': models.CharField(max_length=32),
          'comp': field
      }
    )


class TestResolverInstance(TestCase):
    def setUp(self):
        self.resolver = Resolver()

    # since django 3.2 field in ... check does not work anymore
    # This is a work around with equality testing on individual basis.
    def compare_fields(self, fields_left, fields_right):
        self.assertEqual(len(fields_left), len(fields_right))
        left_ids = set(f.creation_counter for f in fields_left)
        right_ids = set(f.creation_counter for f in fields_right)
        self.assertEqual(left_ids, right_ids)
        # walk all fields
        for left in fields_left:
            for right in fields_right:
                if left == right:
                    break
            else:
                raise Exception(f'{left} not in right fields')
        for right in fields_right:
            for left in fields_left:
                if left == right:
                    break
            else:
                raise Exception(f'{right} not in left fields')

    def test_initialstate(self):
        # all states should be false
        self.assertEqual(self.resolver._sealed, False)
        self.assertEqual(self.resolver._initialized, False)
        self.assertEqual(self.resolver._map_loaded, False)

        # should allow to add fields and models
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedA', lambda self: self.name.upper())
        class_prepared.disconnect(self.resolver.add_model)
        self.compare_fields(self.resolver.computedfields, {rt_field})
        self.assertEqual(self.resolver.models, {rt_model})
        
        # should raise on computed_models, models_with_computedfields, computedfields_with_models
        with self.assertRaises(ResolverException):
            self.resolver.computed_models
        with self.assertRaises(ResolverException):
            list(self.resolver.models_with_computedfields)
        with self.assertRaises(ResolverException):
            list(self.resolver.computedfields_with_models)

    def test_sealed(self):
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedB', lambda self: self.name.upper())

        self.resolver.seal()
        self.assertEqual(self.resolver._sealed, True)
        self.assertEqual(self.resolver._initialized, False)
        self.assertEqual(self.resolver._map_loaded, False)

        # should raise on new fields or models
        with self.assertRaises(ResolverException):
            self.resolver.add_field(rt_field)
        with self.assertRaises(ResolverException):
            self.resolver.add_model(rt_model)
        with self.assertRaises(ResolverException):
            generate_computedmodel(self.resolver, 'RuntimeGeneratedC', lambda self: self.name.upper())
        class_prepared.disconnect(self.resolver.add_model)

        # should allow access to models_with_computedfields, computedfields_with_models
        self.assertEqual(list(self.resolver.models_with_computedfields), [(rt_model, {rt_field})])
        self.assertEqual(list(self.resolver.computedfields_with_models), [(rt_field, {rt_model})])

        # should raise on computed_models
        with self.assertRaises(ResolverException):
            self.resolver.computed_models

    def test_initialized_models_only(self):
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedD', lambda self: self.name.upper())
        class_prepared.disconnect(self.resolver.add_model)

        self.resolver.initialize(models_only=True)
        self.assertEqual(self.resolver._sealed, True)
        self.assertEqual(self.resolver._initialized, True)
        self.assertEqual(self.resolver._map_loaded, False)

        # should allow access to computed_models
        self.assertEqual(self.resolver.computed_models, {rt_model: {'comp': rt_field}})

    def test_initialized_full(self):
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedE', lambda self: self.name.upper())
        class_prepared.disconnect(self.resolver.add_model)

        self.resolver.initialize()
        self.assertEqual(self.resolver._sealed, True)
        self.assertEqual(self.resolver._initialized, True)
        self.assertEqual(self.resolver._map_loaded, True)

        # should have all maps loaded
        self.assertEqual(self.resolver._map, {})
        self.assertEqual(self.resolver._fk_map, {})
        self.assertEqual(self.resolver._local_mro, {rt_model: {'base': ['comp'], 'fields': {'comp': 1, 'name': 1}}})

    def test_initialized_full_wrong_modelbase(self):
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedF', lambda self: self.name.upper(), True)
        class_prepared.disconnect(self.resolver.add_model)

        with self.assertRaises(ResolverException):
            self.resolver.initialize()

    def test_pickled_load(self):
        # write pickled map file
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedG', lambda self: self.name.upper())
        class_prepared.disconnect(self.resolver.add_model)
        self.resolver.initialize()

        # patch test_full.models (otherwise pickle doesnt work)
        models.RuntimeGeneratedG = rt_model

        settings.COMPUTEDFIELDS_MAP = 'mapfile.test_generated'
        self.resolver._write_pickled_data()

        # load back pickled file
        data = self.resolver._load_pickled_data()
        settings.COMPUTEDFIELDS_MAP = None
        os.remove('mapfile.test_generated')
        
        # compare pickle data
        self.assertEqual(data['hash'], self.resolver._calc_modelhash())
        self.assertEqual(data['lookup_map'], self.resolver._map)
        self.assertEqual(data['fk_map'], self.resolver._fk_map)
        self.assertEqual(data['local_mro'], self.resolver._local_mro)

    def test_runtime_coverage(self):
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedH', lambda self: self.name.upper())
        class_prepared.disconnect(self.resolver.add_model)
        self.resolver.initialize()

        # MRO expansion
        self.assertEqual(self.resolver.get_local_mro(rt_model), ['comp'])
        self.assertEqual(self.resolver.get_local_mro(models.Concrete), [])

        # update_computedfields with update_fields expansion
        self.assertEqual(self.resolver.update_computedfields(rt_model(), {'name'}), {'name', 'comp'})
        self.assertEqual(self.resolver.update_computedfields(models.Concrete(), {'name'}), {'name'})

        # is_computedfield test
        self.assertEqual(self.resolver.is_computedfield(rt_model, 'name'), False)
        self.assertEqual(self.resolver.is_computedfield(rt_model, 'comp'), True)
        self.assertEqual(self.resolver.is_computedfield(models.Concrete, 'name'), False)

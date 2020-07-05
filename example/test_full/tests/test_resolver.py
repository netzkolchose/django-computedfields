"""
Some tests for the resolver.

Note - the resolver gets mainly tested indirectly by all other tests.
Tests here are for rare branches and exception traps, that should not
happen during normal operation mode.
"""
from django.test import TestCase
from django.db.models.signals import class_prepared
from computedfields.resolver import Resolver, active_resolver, ResolverException


def generate_computedmodel(resolver, modelname, func):
    from django.db import models
    from computedfields.models import ComputedFieldsModel
    field = resolver.computed(models.CharField(max_length=32), depends=[['self', ['name']]])(func)
    return field, type(
      modelname,
      (ComputedFieldsModel,),
      {
          '__module__': 'test_full.models',
          'name': models.CharField(max_length=32),
          'comp': field
      }
    )

class TestResolverInstance(TestCase):
    def setUp(self):
        self.resolver = Resolver()

    def test_initialstate(self):
        # all states should be false
        self.assertEqual(self.resolver._sealed, False)
        self.assertEqual(self.resolver._initialized, False)
        self.assertEqual(self.resolver._map_loaded, False)

        # should allow to add fields and models
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedA', lambda self: self.upper())
        class_prepared.disconnect(self.resolver.add_model)
        self.assertEqual(self.resolver.computedfields, {rt_field})
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
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedB', lambda self: self.upper())

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
            generate_computedmodel(self.resolver, 'RuntimeGeneratedC', lambda self: self.upper())
        class_prepared.disconnect(self.resolver.add_model)

        # should allow access to models_with_computedfields, computedfields_with_models
        self.assertEqual(list(self.resolver.models_with_computedfields), [(rt_model, {rt_field})])
        self.assertEqual(list(self.resolver.computedfields_with_models), [(rt_field, {rt_model})])

        # should raise on computed_models
        with self.assertRaises(ResolverException):
            self.resolver.computed_models

    def test_initialized_models_only(self):
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedD', lambda self: self.upper())
        class_prepared.disconnect(self.resolver.add_model)

        self.resolver.initialize(models_only=True)
        self.assertEqual(self.resolver._sealed, True)
        self.assertEqual(self.resolver._initialized, True)
        self.assertEqual(self.resolver._map_loaded, False)

        # should allow access to computed_models
        self.assertEqual(self.resolver.computed_models, {rt_model: {'comp': rt_field}})

    def test_initialized_models_only(self):
        class_prepared.connect(self.resolver.add_model)
        rt_field, rt_model = generate_computedmodel(self.resolver, 'RuntimeGeneratedE', lambda self: self.upper())
        class_prepared.disconnect(self.resolver.add_model)

        self.resolver.initialize()
        self.assertEqual(self.resolver._sealed, True)
        self.assertEqual(self.resolver._initialized, True)
        self.assertEqual(self.resolver._map_loaded, True)

        # should have all maps loaded
        self.assertEqual(self.resolver._map, {})
        self.assertEqual(self.resolver._fk_map, {})
        self.assertEqual(self.resolver._local_mro, {rt_model: {'base': ['comp'], 'fields': {'comp': 1, 'name': 1}}})

from django.test import TestCase
from computedfields.models import (ComputedFieldsAdminModel, ContributingModelsModel,
                                   active_resolver, get_contributing_fks)
from django.apps import apps


class TestHelperModels(TestCase):
    def test_ComputedFieldsAdminModel(self):
        cf_models = set()
        for entry in ComputedFieldsAdminModel.objects.all():
            cf_models.add(apps.get_model(entry.app_label, entry.model))
        # NOTE: we have to filter proxy models here
        self.assertEqual(cf_models, set(m for m in active_resolver._computed_models.keys() if not m._meta.proxy))
    
    def test_ContributingModelsModel(self):
        dep_models = set()
        for entry in ContributingModelsModel.objects.all():
            dep_models.add(apps.get_model(entry.app_label, entry.model))
        # NOTE: we have to filter proxy models here
        self.assertEqual(dep_models, set(m for m in active_resolver._fk_map.keys() if not m._meta.proxy))
    
    def test_get_contributing_fks(self):
        self.assertEqual(get_contributing_fks(), active_resolver._fk_map)

from django.test import TestCase
from computedfields.models import (ComputedFieldsAdminModel, ContributingModelsModel,
                                   ComputedFieldsModelType as CFMT, get_contributing_fks)
from django.apps import apps


class TestHelperModels(TestCase):
    def test_ComputedFieldsAdminModel(self):
        cf_models = set()
        for entry in ComputedFieldsAdminModel.objects.all():
            cf_models.add(apps.get_model(entry.app_label, entry.model))
        self.assertEqual(cf_models, set(CFMT._computed_models.keys()))
    
    def test_ContributingModelsModel(self):
        dep_models = set()
        for entry in ContributingModelsModel.objects.all():
            dep_models.add(apps.get_model(entry.app_label, entry.model))
        self.assertEqual(dep_models, set(CFMT._fk_map.keys()))
    
    def test_get_contributing_fks(self):
        self.assertEqual(get_contributing_fks(), CFMT._fk_map)

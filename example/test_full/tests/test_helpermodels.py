from django.test import TestCase
from computedfields.models import (
    ComputedFieldsAdminModel, ContributingModelsModel, active_resolver, get_contributing_fks)
from django.apps import apps


class TestHelperModels(TestCase):
    def test_ComputedFieldsAdminModel(self):
        # NOTE: we have to filter proxy models here
        self.assertEqual(
            set(apps.get_model(e.app_label, e.model) for e in ComputedFieldsAdminModel.objects.all()),
            set(m for m in active_resolver._computed_models.keys() if not m._meta.proxy)
        )
    
    def test_ContributingModelsModel(self):
        # NOTE: for some reason this test fails with "./manage.py test"
        #       nagging about missing through models,
        #       but works with "./manage.py test test_full" and the browser?
        #       --> patched by adding through model explicitly
        # NOTE: we have to filter proxy models here
        self.assertEqual(
            set(apps.get_model(e.app_label, e.model) for e in ContributingModelsModel.objects.all())
            | set(active_resolver._m2m.keys()), # through model hack
            set(m for m in active_resolver._fk_map.keys() if not m._meta.proxy)
        )
    
    def test_get_contributing_fks(self):
        self.assertEqual(
            get_contributing_fks(),
            active_resolver._fk_map
        )

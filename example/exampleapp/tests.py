from django.test import TestCase
from .models import Foo, Bar, Baz
from computedfields.models import ComputedFieldsAdminModel, ComputedFieldsModelType
from computedfields.admin import ComputedModelsAdmin
from django.contrib.admin.sites import AdminSite


class TestModels(TestCase):
    def setUp(self):
        ComputedFieldsModelType._resolve_dependencies(_force=True)
        self.foo = Foo.objects.create(name='foo1')
        self.bar = Bar.objects.create(name='bar1', foo=self.foo)
        self.baz = Baz.objects.create(name='baz1', bar=self.bar)

    def test_create(self):
        self.foo.refresh_from_db()
        self.bar.refresh_from_db()
        self.baz.refresh_from_db()
        self.assertEqual(self.foo.bazzes, 'baz1')
        self.assertEqual(self.bar.foo_bar, 'foo1bar1')
        self.assertEqual(self.baz.foo_bar_baz, 'foo1bar1baz1')

    def test_create_baz(self):
        Baz.objects.create(name='baz2', bar=self.bar)
        self.foo.refresh_from_db()
        self.assertEqual(self.foo.bazzes, 'baz1, baz2')

    def test_delete_bar(self):
        self.baz.delete()
        self.foo.refresh_from_db()
        self.bar.refresh_from_db()
        self.assertEqual(self.foo.bazzes, '')
        self.assertEqual(self.bar.foo_bar, 'foo1bar1')


class TestModelClassesForAdmin(TestCase):
    def setUp(self):
        ComputedFieldsModelType._resolve_dependencies(_force=True)
        self.site = AdminSite()
        self.adminobj = ComputedModelsAdmin(ComputedFieldsAdminModel, self.site)
        self.models = set(ComputedFieldsModelType._computed_models.keys())

    def test_models_listed(self):
        models = [obj.model_class() for obj in ComputedFieldsAdminModel.objects.all()]
        self.assertIn(Foo, models)
        self.assertIn(Bar, models)
        self.assertIn(Baz, models)
        self.assertEqual(set(models), self.models)

    def test_run_adminclass_methods(self):
        for instance in ComputedFieldsAdminModel.objects.all():
            self.adminobj.dependencies(instance)
            self.adminobj.name(instance)
        self.adminobj.get_urls()
        self.adminobj.render_graph({})

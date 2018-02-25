# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.test import TestCase
from models import NormalModel, Foo, Bar, Baz


class FKRelationTestCase(TestCase):
    def setUp(self):
        nm = NormalModel.objects.create(name='nm1')
        foo = Foo.objects.create(name='foo1', nm=nm)
        bar = Bar.objects.create(name='bar1', foo=foo)
        baz = Baz.objects.create(name='baz1', bar=bar)

    def test_values_computed_on_create(self):
        foo = Foo.objects.get(name='foo1')
        bar = Bar.objects.get(name='bar1')
        baz = Baz.objects.get(name='baz1')
        for obj in (foo, bar, baz):
            assert(obj.nm_name == 'nm1')

    def test_value_change_should_update_dependend_fields(self):
        nm = NormalModel.objects.get(name='nm1')
        nm.name = 'new_nm1'
        nm.save()
        foo = Foo.objects.get(name='foo1')
        bar = Bar.objects.get(name='bar1')
        baz = Baz.objects.get(name='baz1')
        for obj in (foo, bar, baz):
            assert(obj.nm_name == 'new_nm1')

    def test_fk_change_update_dependend_fields(self):
        nm2 = NormalModel.objects.create(name='nm2')
        foo = Foo.objects.get(name='foo1')
        foo.nm = nm2
        foo.save()
        foo = Foo.objects.get(name='foo1')
        bar = Bar.objects.get(name='bar1')
        baz = Baz.objects.get(name='baz1')
        for obj in (foo, bar, baz):
            assert(obj.nm_name == 'nm2')

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.test import TestCase
from django.core.management import call_command
from .models import Foo, Bar, Baz


class TestModels(TestCase):
    def setUp(self):
        # run tests with created map
        call_command('createmap', verbosity=0)
        self.foo = Foo.objects.create(name='foo1')
        self.bar = Bar.objects.create(name='bar1', foo=self.foo)
        self.baz = Baz.objects.create(name='baz1', bar=self.bar)
        self.foo.refresh_from_db()
        self.bar.refresh_from_db()
        self.baz.refresh_from_db()

    def test_create(self):
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

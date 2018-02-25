# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.test import TestCase
from models import NormalModel, Foo, Bar, Baz


class FKBackrelationTestCase(TestCase):
    def setUp(self):
        nm = NormalModel.objects.create(name='nm1')
        foo = Foo.objects.create(name='foo1', nm=nm)
        bar = Bar.objects.create(name='bar1', foo=foo)
        baz = Baz.objects.create(name='baz1', bar=bar)

    
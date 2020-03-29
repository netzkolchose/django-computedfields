# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.test import TestCase
from test_full import models


class AbstractModel(TestCase):
    def setUp(self):
        self.concrete = models.Concrete.objects.create(a=300, b=14)

    def test_computed_field_on_abstract_model(self):
        self.assertEqual(self.concrete.c, 314)

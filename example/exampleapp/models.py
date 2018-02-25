# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from computedfields.models import ComputedFieldsModel, computed


class ReprName(models.Model):
    class Meta:
        abstract = True

    def __unicode__(self):
        return self.name


class NormalModel(ReprName):
    name = models.CharField(max_length=32)


class Foo(ComputedFieldsModel, ReprName):
    name = models.CharField(max_length=32)
    nm = models.ForeignKey(NormalModel)


class Bar(ComputedFieldsModel, ReprName):
    name = models.CharField(max_length=32)
    foo = models.ForeignKey(Foo)


class Baz(ComputedFieldsModel, ReprName):
    name = models.CharField(max_length=32)
    bar = models.ForeignKey(Bar)

    @computed(models.CharField(max_length=32), depends=['bar.foo.nm#name'])
    def nm_name(self):
        return self.bar.foo.nm.name

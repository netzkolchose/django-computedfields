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

    @computed(models.CharField(max_length=32), depends=['nm#name'])
    def nm_name(self):
        return self.nm.name


class Bar(ComputedFieldsModel, ReprName):
    name = models.CharField(max_length=32)
    foo = models.ForeignKey(Foo)

    @computed(models.CharField(max_length=32), depends=['foo.nm#name'])
    def nm_name(self):
        return self.foo.nm.name


class Baz(ComputedFieldsModel, ReprName):
    name = models.CharField(max_length=32)
    bar = models.ForeignKey(Bar)

    @computed(models.CharField(max_length=32), depends=['bar.foo.nm#name'])
    def nm_name(self):
        return self.bar.foo.nm.name

    @computed(models.CharField(max_length=32), depends=['bar.foo.nm#name', 'bar.foo#nm_name'])
    def two_ancestors(self):
        return u'%s - %s' % (self.bar.foo.nm.name, self.bar.foo.nm_name)

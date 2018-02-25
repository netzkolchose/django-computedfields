# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from computedfields.models import ComputedFieldsModel, computed


class ReprName(models.Model):
    class Meta:
        abstract = True

    def __unicode__(self):
        return self.name


class NormalModel(ComputedFieldsModel, ReprName):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=['foo_set.bar_set.baz_set#name'])
    def baz_names(self):
        names = []
        for e in self.foo_set.all():
            for elems in e.bar_set.all():
                for obj in elems.baz_set.all():
                    names.append(obj.name)
        return ', '.join(names)


class Foo(ComputedFieldsModel, ReprName):
    name = models.CharField(max_length=32)
    nm = models.ForeignKey(NormalModel)

    @computed(models.CharField(max_length=32), depends=['bar_set.baz_set#name'])
    def baz_names(self):
        names = []
        for elems in self.bar_set.all():
            for obj in elems.baz_set.all():
                names.append(obj.name)
        return ', '.join(names)


class Bar(ComputedFieldsModel, ReprName):
    name = models.CharField(max_length=32)
    foo = models.ForeignKey(Foo)

    @computed(models.CharField(max_length=32), depends=['baz_set#name'])
    def baz_names(self):
        return ', '.join(obj.name for obj in self.baz_set.all())


class Baz(ComputedFieldsModel, ReprName):
    name = models.CharField(max_length=32)
    bar = models.ForeignKey(Bar)

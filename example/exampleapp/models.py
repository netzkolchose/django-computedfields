# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from computedfields.models import ComputedFieldsModel, computed


class Test(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=['foo_set#name'])
    def pansen(self):
        return self.name + 'pansen' + ''.join([e.name for e in self.foo_set.all()])

    def __unicode__(self):
        return u'Test %s' % self.pk


class Foo(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    test = models.ForeignKey(Test)

    @computed(models.CharField(max_length=32), depends=['test#pansen', 'bar_set#name'])
    def drilldown(self):
        return self.name + self.test.pansen

    @computed(models.CharField(max_length=32), depends=['test#pansen', 'test#name', 'bar_set#name'])
    def test2(self):
        return self.name + self.test.pansen

    def __unicode__(self):
        return u'Foo %s' % self.pk


class Bar(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    foo = models.ForeignKey(Foo)
    bla = models.ForeignKey(Foo, related_name='husten')

    @computed(models.CharField(max_length=32), depends=['foo.test#name', 'bla.test#name'])
    def klaus(self):
        return self.name + self.foo.test.name

    @computed(models.CharField(max_length=32), depends=['bla.test#name'])
    def klaus2(self):
        return self.name + self.bla.test.name

    def __unicode__(self):
        return u'Bar %s' % self.pk


class Baz(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    foos = models.ManyToManyField(Foo)

    @computed(models.CharField(max_length=32), depends=['foos#drilldown'])
    def buzzer(self):
        if not self.pk:
            return ''
        return ', '.join(e.drilldown for e in self.foos.all())


# comp: 'a__b__c__field' --> model_comp: model_a, model_b, model_c field_c
#
# model_a --> model_comp(filter a) -> filter(a=inst)
# model_b --> model_comp(filter a in model_a(filter b)) -> filter(a__b=inst)
# model_c --> model_comp(filter a in model_a(filter b in model_b(filter c))) -> filter(a__b__c=inst)


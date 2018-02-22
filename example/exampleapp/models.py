# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from computedfields.models import ComputedFieldsModel, computed


class Test(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=['#foo_set'])
    def pansen(self):
        return self.name + 'pansen' + ''.join(map(unicode, self.foo_set.all()))

    def __unicode__(self):
        return u'Test %s' % self.pk


class Foo(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    test = models.ForeignKey(Test)

    @computed(models.CharField(max_length=32), depends=['test'])
    def drilldown(self):
        return self.name + self.test.name

    def __unicode__(self):
        return u'Foo %s' % self.pk


class Bar(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    foo = models.ForeignKey(Foo)

    @computed(models.CharField(max_length=32), depends=['foo__test'])
    def klaus(self):
        return self.name + self.foo.test.name

    def __unicode__(self):
        return u'Bar %s' % self.pk

# comp: 'a__b__c__field' --> model_comp: model_a, model_b, model_c field_c
#
# model_a --> model_comp(filter a) -> filter(a=inst)
# model_b --> model_comp(filter a in model_a(filter b)) -> filter(a__b=inst)
# model_c --> model_comp(filter a in model_a(filter b in model_b(filter c))) -> filter(a__b__c=inst)


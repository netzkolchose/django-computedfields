# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db.models.base import ModelBase
from django.db import models
from django.apps import apps


from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save)
def my_callback(sender, instance, **kwargs):
    print instance, kwargs
    if sender in dependent_models:
        for _, model, field, computed in dependent_models[sender]:
            print model, field, computed
            if not field.startswith('#'):
                for elem in model.objects.filter(**{field: instance}):
                    elem.save(update_fields=[computed])
            else:
                print 'hmmm:', sender, model, field



computed_models = {}

dependent_models = {}


def resolve_dependencies():
    for model, fields in computed_models.iteritems():
        dep_model = model
        for field, depends in fields.iteritems():
            for dependency in depends:
                agg = []
                for value in dependency.split('__'):
                    agg.append(value)
                    if value.startswith('#'):
                        related_model = getattr(model, value[1:]).rel.related_model
                    else:
                        related_model = model._meta.get_field(value).related_model
                    dependent_models.setdefault(related_model, []).append((len(agg), dep_model, '__'.join(agg), field))
                    model = related_model
    print 'computed models:'
    for e in computed_models:
        print e, computed_models[e]
    print 'dep models:'
    for dep in dependent_models:
        print dep, dependent_models[dep]


class ComputedFieldsModelType(ModelBase):
    def __new__(mcs, name, bases, attrs):
        computed_fields = {}
        dependent_fields = {}
        for k, v in attrs.iteritems():
            if getattr(v, '_computed', None):
                computed_fields.update({k: v})
                v.editable = False
                v._computed.update({'attr': k})
                depends = v._computed['kwargs'].get('depends')
                if depends:
                    dependent_fields[k] = depends
        cls = super(ComputedFieldsModelType, mcs).__new__(mcs, name, bases, attrs)
        cls._computed_fields = computed_fields
        if dependent_fields:
            computed_models[cls] = dependent_fields
        return cls


class ComputedFieldsModel(models.Model):
    __metaclass__ = ComputedFieldsModelType

    class Meta:
        abstract = True

    def compute(self, field):
        setattr(self, field._computed['attr'], field._computed['func'](self))

    def save(self, *args, **kwargs):
        for field in self._computed_fields.values():
            self.compute(field)
        super(ComputedFieldsModel, self).save(*args, **kwargs)


def computed(field, **kwargs):
    def wrap(f):
        field._computed = {'func': f, 'kwargs': kwargs}
        return field
    return wrap

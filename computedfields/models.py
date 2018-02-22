# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db.models.base import ModelBase
from django.db import models


from django.db.models.signals import post_save


def my_callback(sender, instance, **kwargs):
    if sender in dependent_models:
        for _, model, field, computed in dependent_models[sender]:
            print sender, instance, model, field, computed
            if not field.startswith('#'):
                print model.objects.filter(**{field: instance}).distinct()
                for elem in model.objects.filter(**{field: instance}).distinct():
                    elem.save(update_fields=[computed])
            else:
                #post_save.disconnect(my_callback, sender=None, dispatch_uid='COMP_FIELD')
                fieldname = getattr(model, field[1:]).rel.field.name
                print '#backrel', getattr(instance, fieldname)
                getattr(instance, fieldname).save(update_fields=[computed])
                #post_save.connect(my_callback, sender=None, weak=False, dispatch_uid='COMP_FIELD')


post_save.connect(my_callback, sender=None, weak=False, dispatch_uid='COMP_FIELD')


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

    def compute(self, fieldname):
        field = self._computed_fields[fieldname]
        return field._computed['func'](self)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields:
            update_fields = set(update_fields)
            all_computed = not (update_fields - set(self._computed_fields.keys()))
            if all_computed:
                has_changed = False
                for fieldname in update_fields:
                    result = self.compute(fieldname)
                    field = self._computed_fields[fieldname]
                    if result != getattr(self, field._computed['attr']):
                        has_changed = True
                        setattr(self, field._computed['attr'], result)
                if not has_changed:
                    return
                super(ComputedFieldsModel, self).save(*args, **kwargs)
                return
        for fieldname in self._computed_fields:
            result = self.compute(fieldname)
            field = self._computed_fields[fieldname]
            setattr(self, field._computed['attr'], result)
        super(ComputedFieldsModel, self).save(*args, **kwargs)


def computed(field, **kwargs):
    def wrap(f):
        field._computed = {'func': f, 'kwargs': kwargs}
        return field
    return wrap

# -*- coding: utf-8 -*-
from django.db import models
import sys
from computedfields.models import ComputedFieldsModel, computed


def model_factory(name, keys):
    """
    Create a test model at runtime. `name` is the model name in lower case, `keys`
    contains all other models to be build like this.

        class A(ComputedFieldsModel):
            name = models.CharField(max_length=5)
            f_ab = models.ForeignKey('B', related_name='ba_f', blank=True, null=True)
            m_ab = models.ManyToManyField('B', related_name='ba_m', blank=True, null=True)
            o_ab = models.OneToOneField('B', related_name='ba_o', blank=True, null=True)

            @computed(models.CharField(max_length=5), depends=[])
            def comp(self):
                return ''

    The `comp` function and the depends list will be replaced by the different test cases.
    """
    attrs = {}

    # add module and __unicode__ attr
    attrs.update({
        '__module__': 'test_full.models',
        '__unicode__': lambda self: self.name})

    # name field
    attrs.update({'name': models.CharField(max_length=5)})

    # related fields
    for key in keys:
        fwd_name = name + key
        bwd_name = key + name
        attrs['f_'+fwd_name] = models.ForeignKey(
            key, related_name=bwd_name+'_f', blank=True, null=True)
        attrs['m_'+fwd_name] = models.ManyToManyField(
            key, related_name=bwd_name+'_m', blank=True)
        attrs['o_'+fwd_name] = models.OneToOneField(
            key, related_name=bwd_name+'_o', blank=True, null=True)

    # comp field
    attrs['comp'] = computed(models.CharField(max_length=20), depends=[])(lambda self: '')

    # create model class
    model_cls = type(name.upper(), (ComputedFieldsModel,), attrs)
    setattr(sys.modules[__name__], name.upper(), model_cls)
    return model_cls


def generate_models(keys):
    """
    Generate multiple models at runtime.
    """
    return dict((key.upper(), model_factory(key, keys)) for key in keys)


# generate models: A, B ...
MODELS = generate_models('abcdefgh')


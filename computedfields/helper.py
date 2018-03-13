from itertools import tee
from django.utils.six.moves import zip
from django.db.models.fields.reverse_related import ManyToOneRel, OneToOneRel, ManyToManyRel
from django.db.models import ManyToManyField, ForeignKey


RELTYPES = {ManyToManyRel: 'm2m', OneToOneRel: 'o2o', ManyToOneRel: 'fk',
            ManyToManyField: 'm2m', ForeignKey: 'fk'}


def reltype(rel):
    return RELTYPES[type(rel)]


def pairwise(iterable):
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def is_computedfield(model, field):
    return hasattr(model, '_computed_fields') and field in model._computed_fields


def modelname(model):
    return '%s.%s' % (model._meta.app_label, model._meta.verbose_name)


def is_sublist(needle, haystack):
    if not needle:
        return True
    if not haystack:
        return False
    max_k = len(needle) - 1
    k = 0
    for elem in haystack:
        if elem != needle[k]:
            k = 0
            continue
        if k == max_k:
            return True
        k += 1
    return False

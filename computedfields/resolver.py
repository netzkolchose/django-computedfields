"""
Module containing the resolver for dependency strings. It basically does
the transition from a given depends string to a list of functions,
that, applied to a given instance, returns all dependent objects.

Example:
    Given a depends string on a computed field of a model ``MyModel``
    is ``'a.b#field'``. Here changes to an instance of the model behind
    ``b`` must update the computed field of instances of ``MyModel`` through
    a model that resides behind ``a``.

    Further given all relations above are foreign keys the resolver creates
    roughly this function:

    .. code:: python

        lambda instance: MyModel.objects.filter(a__b=instance)

    which, directly applied to an instance or a queryset of the
    model behind ``b``, returns all ``MyModel`` objects that depend on
    this instance or the objects in the queryset.

For more complex dependency strings several functions will be returned,
that must be applied in order. This is needed to resolve intermediate
subqueries and attribute lookups correctly.
"""
from operator import attrgetter
from django.db.models import QuerySet
from functools import partial


class QuerySetGenerator(object):
    """
    Class for inserting a queryset into the dependency stack.
    Handles consecutive querysets as subqueries (translated to sub selects by django).
    Returns a queryset.
    """
    def __init__(self):
        self.strings = []
        self.model = None

    def add_string(self, string):
        self.strings.append(string)

    def finalize(self):
        return partial(qs_value, self.model, '__'.join(self.strings))


def qs_value(model, qs_string, instance):
    """
    Pickleable resolve function returned as
    a partial from a ``QuerySetGenerator`` object.
    """
    if isinstance(instance, QuerySet):
        return model.objects.filter(**{qs_string+'__in': instance})
    return model.objects.filter(**{qs_string: instance})


class AttrGenerator(object):
    """
    Class for inserting an attribute lookup into the dependency stack.
    Uses ``operator.attrgetter`` if the input is a model instance.
    For querysets it returns a flatted value list queryset.
    """
    def __init__(self):
        self.strings = []

    def add_string(self, string):
        self.strings.append(string)

    def finalize(self):
        return partial(attr_value, '__'.join(reversed(self.strings)),
                       '.'.join(reversed(self.strings)))


def attr_value(qs_string, attr_string, instance):
    """
    Pickleable resolve function returned as
    a partial from an ``AttrGenerator`` object.
    """
    if isinstance(instance, QuerySet):
        return instance.values_list(qs_string, flat=True)
    try:
        return attrgetter(attr_string)(instance)
    except AttributeError:
        return None


class PathResolver(object):
    """
    Class to resolve dependency path segments into consecutive function calls.

    This works stream like where every function alters the input and outputs the
    result to the next function. First input is the initial instance
    (model instance or queryset), last output is the final dependent
    model instance or queryset:

    .. code:: python

        instance = func3(func2(func1(instance)))

    The inner resolve functions are function partials created by
    ``QuerySetGenerator`` and ``AttrGenerator``.
    """
    def __init__(self, model, data):
        self.model = model
        self.data = data

    def _resolve_path_segments(self, dep):
        """
        Builds a stack of ``QuerySetGenerator`` and ``AttrGenerator``
        objects based on the dependencies data.
        Returns the reversed stack of function partials
        to be applied later to a model instance or queryset.
        """
        search = QuerySetGenerator()
        attrs = AttrGenerator()
        stack = []
        for rel in dep['nd']:
            if ((rel['type'] in ['fk', 'm2m'] and not rel['backrel'])
                  or (rel['type'] == 'm2m' and rel['backrel'])):
                if attrs.strings:
                    stack.append(attrs)
                    attrs = AttrGenerator()
                if not search.strings:
                    search.model = rel['model']
                search.add_string(rel['path'])
            elif rel['type'] == 'fk' and rel['backrel']:
                if search.strings:
                    stack.append(search)
                    search = QuerySetGenerator()
                attrs.add_string(rel['path'])
            else:
                raise NotImplemented([rel['type'], rel['backrel']])
        if attrs.strings:
            stack.append(attrs)
        if search.strings:
            stack.append(search)
        return [el.finalize() for el in reversed(stack)]

    def resolve(self):
        """
        Returns a list containing
        ``[['computed fieldname', [resolve functions]], ...]``.
        """
        result = []
        for field, deps in self.data.items():
            for dep in deps:
                result.append([field, self._resolve_path_segments(dep)])
        return result

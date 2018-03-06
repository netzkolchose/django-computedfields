from operator import attrgetter
from django.db.models import QuerySet, Model
from itertools import ifilter


class QuerySetGenerator(object):
    """
    Class for inserting a queryset in the dependency path.
    Handles consecutive querysets as subqueries (translated to sub selects by django).
    Returns a queryset.
    """
    def __init__(self):
        self.strings = []
        self.model = None
        self._qs_string = None

    def add_string(self, string):
        self.strings.append(string)

    def _value(self, instance):
        if isinstance(instance, QuerySet):
            return self.model.objects.filter(**{self._qs_string+'__in': instance}).distinct()
        return self.model.objects.filter(**{self._qs_string: instance}).distinct()

    def finalize(self):
        self._qs_string = '__'.join(self.strings)
        return self._value


class AttrGenerator(object):
    """
    Class for inserting an attribute lookup in the dependency path.
    Uses `operator.attrgetter` if the input is a model instance.
    For querysets it returns a flatted value list queryset.
    """
    def __init__(self):
        self.strings = []
        self._attrgetter = None
        self._qs_string = None

    def add_string(self, string):
        self.strings.append(string)

    def _value(self, instance):
        if isinstance(instance, QuerySet):
            return instance.values_list(self._qs_string, flat=True).distinct()
        try:
            return self._attrgetter(instance)
        except AttributeError:
            return None

    def finalize(self):
        self._attrgetter = attrgetter('.'.join(reversed(self.strings)))
        self._qs_string = '__'.join(reversed(self.strings))
        return self._value


def _resolve(paths_resolved, model, field):
    """
    Closure for the save handler. The inner function calls the
    path segment functions and saves the final result.
    """
    def resolved(instance):
        for func in paths_resolved:
            instance = func(instance)
            if not instance:
                return
        if isinstance(instance, QuerySet):
            # for multiple fk back relations the final queryset
            # contains only pks due to the fact that values_list
            # returns "nacked" pks for foreign fields
            # simply try to determine if we have no model instances
            # and replace it with a pk__in filtered queryset
            try:
                el = instance[0]
            except IndexError:
                return
            if not isinstance(el, Model):
                # the value list should point to the pks of the target model
                instance = model.objects.filter(pk__in=instance)
            for el in ifilter(bool, instance):
                el.save(update_fields=[field])
            return
        instance.save(update_fields=[field])
    return resolved


class PathResolver(object):
    """
    Class to resolve dependency path segments into consecutive function calls.
    This works stream like where every function alters the input and outputs the
    result to the next function. First input is the instance given in the save handler,
    last action is to save the final output:
        `func3(func2(func1(instance))).save()`
    The functions are the `_value()` methods of `QuerySetGenerator` and `AttrGenerator`,
    which work either on model instances or querysets.
    To lower the runtime penalty in the save handler the `_value()` methods
    are as slim as possible.
    """
    def __init__(self, model, data):
        self.model = model
        self.data = data

    def _resolve_path_segments(self, dep):
        search = QuerySetGenerator()
        attrs = AttrGenerator()
        stack = []
        for rel in dep['nd']:
            if rel['type'] == 'fk' and not rel['backrel']:
                # found a fk relation
                if attrs.strings:
                    stack.append(attrs)
                    attrs = AttrGenerator()
                if not search.strings:
                    search.model = rel['model']
                search.add_string(rel['path'])
            elif rel['type'] == 'fk' and rel['backrel']:
                # found a fk backrelation
                if search.strings:
                    stack.append(search)
                    search = QuerySetGenerator()
                attrs.add_string(rel['path'])
        if attrs.strings:
            stack.append(attrs)
        if search.strings:
            stack.append(search)
        return [el.finalize() for el in reversed(stack)]

    def resolve(self):
        result = []
        for field, deps in self.data.items():
            for dep in deps:
                result.append(_resolve(self._resolve_path_segments(dep), self.model, field))
        return result

from operator import attrgetter
from django.db.models import QuerySet


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
            return self.model.objects.filter(**{self._qs_string+'__in': instance})
        return self.model.objects.filter(**{self._qs_string: instance})

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
            return instance.values_list(self._qs_string, flat=True)
        try:
            return self._attrgetter(instance)
        except AttributeError:
            return None

    def finalize(self):
        self._attrgetter = attrgetter('.'.join(reversed(self.strings)))
        self._qs_string = '__'.join(reversed(self.strings))
        return self._value


class PathResolver(object):
    """
    Class to resolve dependency path segments into consecutive function calls.
    This works stream like where every function alters the input and outputs the
    result to the next function. First input is the initial instance
    (model instance or queryset), last output is the final dependent
    model instance or queryset:
        ` instance = func3(func2(func1(instance)))`
    The functions are the `_value()` methods of `QuerySetGenerator` and `AttrGenerator`,
    which work either on model instances or querysets.
    To lower the runtime penalty the `_value` methods are as slim as possible.
    """
    def __init__(self, model, data):
        self.model = model
        self.data = data

    def _resolve_path_segments(self, dep):
        """
        Builds a stack of `QuerySetGenerator` and `AttrGenerator`
        objects based on the dependencies data.
        Returns the reversed stack of `_value` methods to be applied
        later to a model instance or queryset.
        """
        search = QuerySetGenerator()
        attrs = AttrGenerator()
        stack = []
        for rel in dep['nd']:
            if rel['type'] in ['fk', 'm2m'] and not rel['backrel']:
                # found a fk/m2m relation
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
        """
        Returns a list containing
        [['computed fieldname', [resolve functions]], ...].
        """
        result = []
        for field, deps in self.data.items():
            for dep in deps:
                result.append([field, self._resolve_path_segments(dep)])
        return result

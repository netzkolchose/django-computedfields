from operator import attrgetter
from django.db.models import QuerySet


class QuerySetGenerator(object):
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
    def __init__(self):
        self.strings = []
        self._attrgetter = None
        self._qs_string = None

    def add_string(self, string):
        self.strings.append(string)

    def _value(self, instance):
        if isinstance(instance, QuerySet):
            return instance.values_list(self._qs_string, flat=True)
        return self._attrgetter(instance)

    def finalize(self):
        self._attrgetter = attrgetter('.'.join(reversed(self.strings)))
        self._qs_string = '__'.join(reversed(self.strings))
        return self._value


class PathResolver(object):
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

    def _resolve(self, paths_resolved, field):
        def resolved(instance):
            for func in paths_resolved:
                instance = func(instance)
                if not instance:
                    return
            if isinstance(instance, QuerySet):
                for el in instance:
                    el.save(update_fields=[field])
            else:
                instance.save(update_fields=[field])
        return resolved

    def resolve(self):
        result = []
        for field, deps in self.data.items():
            for dep in deps:
                result.append(self._resolve(self._resolve_path_segments(dep), field))
        return result

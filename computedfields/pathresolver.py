from pprint import pprint
from operator import attrgetter
from django.db.models import QuerySet
from computedfields.helper import modelname


# problem:
# 1) a field can depend on multiple nested relations, e.g. fk.fk_back.m2m....
# 2) a field can depend on the same target relation multiple times with different fields
#    e.g. ['fk_a.#name', 'fk_b#xy'] where fk_a and fk_b point to the same model
#
# solution 1)
#   - nested fks      --> merge paths to query, e.g. ['fk_a', 'fk_b'] --> 'fk_a__fk_b'
#                         call save on final QuerySet
#                         M.filter(a__b==instance)#save
#   - nested fks back --> instance.a.b.save
#
#   - mixed:
#       - fks after fk backs
#           'a_set.b_set.c.d' --> M.filter(c__b==instance.a.b)#save
#       - fks back after fks
#           'a.b.c_set.d_set' --> QS.filter(a__b==instance)#c.d.save
#       - complicated
#           'a.b_set.c.d_set' --> QS.filter(c__in=QS.filter(a==instance.b)#pk)#d.save
#           'a_set.b.c_set.d' --> QS.filter(d__in=QS.filter(b=instance.a)#c.pk)#save


class QuerySetGenerator(object):
    def __init__(self):
        self.strings = []
        self.model = None
        self._qs_string = None

    def add_string(self, string):
        self.strings.append(string)

    def _value(self, instance):
        if isinstance(instance, QuerySet) or hasattr(instance, '__iter__'):
            qs = self.model.objects.filter(**{'__'.join((self._qs_string, 'in')): instance})
        else:
            qs = self.model.objects.filter(**{self._qs_string: instance})
        return qs

    def finalize(self):
        self._qs_string = '__'.join(self.strings)
        return self._value

    def __str__(self):
        return '<QuerySetGenerator "%s" %s>' % (modelname(self.model), '__'.join(self.strings))

    def __repr__(self):
        return str(self)


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

    def __str__(self):
        return '<AttrGenerator %s>' % '.'.join(reversed(self.strings))

    def __repr__(self):
        return str(self)


class PathResolver(object):
    def __init__(self, model, data):
        self.model = model
        self.data = data

    def dump_data(self):
        pprint(self.data, width=120)

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

        # final path segments resolved
        return [el.finalize() for el in reversed(stack)]

    def _resolve(self, paths_resolved, field):
        # final handler code
        def resolved(instance):
            # iterate through path segments
            for func in paths_resolved:
                instance = func(instance)
                if not instance:
                    break
            else:
                # save if we went through all
                if isinstance(instance, QuerySet) or hasattr(instance, '__iter__'):
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

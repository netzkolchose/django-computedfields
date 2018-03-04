from functools import partial
from copy import deepcopy
from pprint import pprint
from operator import attrgetter
from django.db.models import QuerySet


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
        self.is_subquery = False
        self.filter_subquery = False

    def add_string(self, string):
        self.strings.append(string)

    def _value(self, instance):
        # FIXME: better way to deal with subqueries
        if isinstance(instance, QuerySet) or hasattr(instance, '__iter__'):
            strings = self.strings
            strings += ['in']
            qs = self.model.objects.filter(**{'__'.join(strings): instance})
            return qs

        if self.strings:
            strings = self.strings
            if self.filter_subquery:
                strings += ['in']
            qs = self.model.objects.filter(**{'__'.join(strings): instance})
        else:
            if self.filter_subquery:
                qs = self.model.objects.filter(pk__in=instance)
            else:
                qs = self.model.objects.all()
        if self.is_subquery:
            qs = qs.values_list('pk', flat=True)
        return qs

    @property
    def value(self):
        return self._value

    def __str__(self):
        return '<QSG %s %s>' % (self.model._meta.model_name, '__'.join(self.strings))

    def __repr__(self):
        return str(self)


class AttrGenerator(object):
    def __init__(self):
        self.strings = []

    def add_string(self, string):
        self.strings.append(string)

    def _value(self, instance):
        attr = attrgetter('.'.join(reversed(self.strings)))
        # FIXME: better way to deal with subqueries - replace container with QS logic
        if isinstance(instance, QuerySet):
            result = []
            for el in instance:
                result.append(attr(el))
            return result
        return attr(instance)

    @property
    def value(self):
        return self._value

    def __str__(self):
        return '<AG %s>' % '.'.join(reversed(self.strings))

    def __repr__(self):
        return str(self)


# FIXME: move resolver out of handler callback
def path_resolver(model, field, dep, instance):
    search = QuerySetGenerator()
    attrs = AttrGenerator()
    stack = []
    for rel in dep['nd']:
        if rel['type'] == 'fk' and not rel['backrel']:  # found a fk relation
            if attrs.strings:
                stack.append(attrs)
                attrs = AttrGenerator()
            if not search.strings:
                search.model = rel['model']
            search.add_string(rel['path'])
        elif rel['type'] == 'fk' and rel['backrel']:    # found a fk backrelation
            if search.strings:
                stack.append(search)
                search = QuerySetGenerator()
            attrs.add_string(rel['path'])
    if attrs.strings:
        stack.append(attrs)
    if search.strings:
        stack.append(search)

    print stack

    # FIXME: make use of subquery annotations here

    # handler code starts here...
    for el in reversed(stack):
        print el
        instance = el.value(instance)
        print instance
        if not instance:
            break
    else:
        print 'should call save now...'
        if isinstance(instance, QuerySet) or hasattr(instance, '__iter__'):
            for el in instance:
                el.save(update_fields=[field])
        else:
            instance.save(update_fields=[field])

    print
    print


class FuncGenerator(object):
    def __init__(self, model, data):
        self.model = model
        self.data = deepcopy(data)
        self.final = []

    def dump_data(self):
        pprint(self.data, width=120)

    def resolve_all(self):
        for field, deps in self.data.items():
            for dep in deps:
                self.final.append(partial(path_resolver, self.model, field, dep))

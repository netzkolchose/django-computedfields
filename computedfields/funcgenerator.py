from django.db.models import Q
from functools import partial
from copy import deepcopy
from pprint import pprint

# FIXME: major design flaw in multi path - respect all in between relation types


def generate_Q(paths, instance):
    if paths:
        query_obj = Q(**{paths.pop(): instance})
        while paths:
            query_obj |= Q(**{paths.pop(): instance})
        return query_obj
    return Q()


def fk_relation(model, paths, fields, instance):
    print 'fk_relation', paths, model
    for elem in model.objects.filter(generate_Q(paths, instance)).distinct():
        elem.save(update_fields=fields)


def fk_backrelation(model, paths, fields, instance):
    print 'fk_backrelation', paths, model
    for path in paths:
        if len(path) == 2:
            model = getattr(model, path[0]).field.rel.related_model
            fieldname = getattr(model, path[1]).rel.field.name
            getattr(instance, fieldname).save(update_fields=fields)
            return
        if len(path) == 3:
            model = getattr(model, path[0]).field.rel.related_model
            model = getattr(model, path[1]).field.rel.related_model
            fieldname = getattr(model, path[2]).rel.field.name
            getattr(instance, fieldname).save(update_fields=fields)
            return
        fieldname = getattr(model, ''.join(path)).rel.field.name
        getattr(instance, fieldname).save(update_fields=fields)


def m2m_relation(model, paths, fields, instance):
    print 'm2m_relation', paths, model
    for elem in model.objects.filter(generate_Q(paths, instance)).distinct():
        elem.save(update_fields=fields)


class FuncGenerator(object):
    def __init__(self, model, data):
        self.model = model
        self.data = deepcopy(data)
        self.final = []

    def dump_data(self):
        pprint(self.data, width=120)

    def cleanup_data(self):
        for field in self.data.keys():
            self.data[field] = [dep for dep in self.data[field] if not dep.get('processed')]
            if not self.data[field]:
                del self.data[field]

    def resolve_all(self):
        self.resolve_fk_relation()
        self.resolve_fk_backrelation()
        self.resolve_m2m_relation()

    def resolve_fk_relation(self):
        paths = set()
        fields = set()
        for field, deps in self.data.iteritems():
            for dep in deps:
                if dep['rel'] == 'fk' and not dep['backrel']:
                    paths.add('__'.join(dep['path']))
                    fields.add(field)
                    dep['processed'] = True
        if paths:
            self.final.append(partial(fk_relation, self.model, paths, fields))
        self.cleanup_data()

    def resolve_fk_backrelation(self):
        paths = set()
        fields = set()
        for field, deps in self.data.iteritems():
            for dep in deps:
                if dep['rel'] == 'fk' and dep['backrel']:
                    paths.add(tuple(dep['path']))
                    fields.add(field)
                    dep['processed'] = True
        if paths:
            self.final.append(partial(fk_backrelation, self.model, paths, fields))
        self.cleanup_data()

    def resolve_m2m_relation(self):
        paths = set()
        fields = set()
        for field, deps in self.data.iteritems():
            for dep in deps:
                if dep['rel'] == 'm2m' and not dep['backrel']:
                    paths.add('__'.join(dep['path']))
                    fields.add(field)
                    dep['processed'] = True
        if paths:
            self.final.append(partial(m2m_relation, self.model, paths, fields))
        self.cleanup_data()

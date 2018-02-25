from collections import OrderedDict
from django.core.exceptions import FieldDoesNotExist
from itertools import tee, izip
from django.db.models.fields.reverse_related import ManyToOneRel, OneToOneRel, ManyToManyRel


RELTYPES = {ManyToManyRel: 'm2m', OneToOneRel: 'o2o', ManyToOneRel: 'fk'}


def reltype(rel):
    return RELTYPES[type(rel)]


def pairwise(iterable):
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)


def is_computed_field(model, field):
    if hasattr(model, '_computed_fields') and field in model._computed_fields:
        return True
    return False


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


class CycleException(Exception):
    pass


class Edge(object):
    instances = {}

    def __new__(cls, *args, **kwargs):
        key = (args[0], args[1])
        if key in cls.instances:
            return cls.instances[key]
        instance = super(Edge, cls).__new__(cls, *args, **kwargs)
        cls.instances[key] = instance
        return instance

    def __init__(self, left, right, data=None):
        self.left = left
        self.right = right
        self.data = data

    def __str__(self):
        return 'Edge %s-%s' % (self.left, self.right)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self.left == other.left and self.right == other.right

    def __ne__(self, other):
        return not self.__eq__(other)


class Node(object):
    instances = {}

    def __new__(cls, *args, **kwargs):
        if args[0] in cls.instances:
            return cls.instances[args[0]]
        instance = super(Node, cls).__new__(cls, *args, **kwargs)
        cls.instances[args[0]] = instance
        return instance

    def __init__(self, data):
        self.data = data

    def __str__(self):
        return '.'.join(self.data)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self.data == other.data

    def __ne__(self, other):
        return not self.__eq__(other)


class Graph(object):
    def __init__(self):
        self.nodes = set()
        self.edges = set()
        self._removed = set()

    def add_node(self, node):
        self.nodes.add(node)

    def remove_node(self, node):
        self.nodes.remove(node)

    def add_edge(self, edge):
        self.edges.add(edge)
        self.nodes.add(edge.left)
        self.nodes.add(edge.right)

    def remove_edge(self, edge):
        self.edges.remove(edge)

    def render(self, filename=None):
        from graphviz import Digraph
        dot = Digraph()
        for node in self.nodes:
            dot.node(str(node), str(node))
        for edge in self.edges:
            dot.edge(str(edge.left), str(edge.right))
        dot.render(filename=filename, cleanup=True)

    def _get_edge_paths(self, edge, left_edges, paths, seen=None):
        if not seen:
            seen = []
        if edge in seen:
            raise CycleException(seen[seen.index(edge):] + [edge])
        seen.append(edge)
        if edge.right in left_edges:
            for new_edge in left_edges[edge.right]:
                self._get_edge_paths(new_edge, left_edges, paths, seen[:])
        paths.append(seen)

    def get_edgepaths(self):
        left_edges = {}
        paths = []
        for edge in self.edges:
            left_edges.setdefault(edge.left, []).append(edge)
        for edge in self.edges:
            self._get_edge_paths(edge, left_edges, paths)
        return paths

    def get_nodepaths(self):
        paths = self.get_edgepaths()
        node_paths = []
        for path in paths:
            node_paths.append([edge.left for edge in path] + [path[-1].right])
        return node_paths

    def _can_replace_nodepath(self, needle, haystack):
        if not set(haystack).issuperset(needle):
            return False
        if is_sublist(needle, haystack):
            return False
        return True

    def _compare_startend_nodepaths(self, new_paths, base_paths):
        base_points = set((path[0], path[-1]) for path in base_paths)
        new_points = set((path[0], path[-1]) for path in new_paths)
        return base_points == new_points

    def remove_redundant_paths(self):
        paths = self.get_nodepaths()
        possible_replaces = []
        for p in paths:
            for q in paths:
                if self._can_replace_nodepath(q, p):
                    possible_replaces.append((q, p))
        removed = set()
        for candidate, replacement in possible_replaces:
            edges = [Edge(*nodes) for nodes in pairwise(candidate)]
            for edge in edges:
                if edge in removed:
                    continue
                self.remove_edge(edge)
                removed.add(edge)
                # make sure all startpoints will still update all endpoints
                if not self._compare_startend_nodepaths(self.get_nodepaths(), paths):
                    self.add_edge(edge)
                    removed.remove(edge)
        self._removed.update(removed)
        return removed


class ComputedModelsGraph(Graph):
    def __init__(self, computed_models):
        super(ComputedModelsGraph, self).__init__()
        self.computed_models = computed_models
        self.lookup_map = {}
        self.data, self.cleaned, self.model_mapping = self.resolve_dependencies(self.computed_models)
        self.insert_data(self.cleaned)

    def dump_computed_models(self):
        print 'computed models field dependencies'
        for model, data in self.computed_models.iteritems():
            print model
            for field, depends in data.iteritems():
                print '    ', field
                print '        ', depends

    def dump_data(self):
        print 'resolved field dependencies'
        for model, fielddata in self.data.iteritems():
            print model
            for field, modeldata in fielddata.iteritems():
                print '    ', field
                for depmodel, data in modeldata.iteritems():
                    print '        ', depmodel, data

    def dump_cleaned(self):
        print 'graph insert data (edges)'
        for left_node, right_nodes in self.cleaned.iteritems():
            print left_node
            for right_node in right_nodes:
                print '    ', right_node

    def dump_lookup_map(self):
        print 'lookup map for signal handler'
        for lmodel, data in self.lookup_map.iteritems():
            print lmodel
            for lfield, fielddata in data.iteritems():
                print '    ', lfield
                for rmodel, rdata in fielddata.iteritems():
                    print '        ', rmodel
                    for rfield, rfielddata in rdata.iteritems():
                        print '            ', rfield
                        if hasattr(rfielddata, '__iter__'):
                            for dep in rfielddata:
                                print '                ', dep
                        else:
                            print '                ', rfielddata

    def resolve_dependencies(self, computed_models):
        store = OrderedDict()
        for model, fields in computed_models.iteritems():
            modelentry = store.setdefault(model, {})
            for field, depends in fields.iteritems():
                fieldentry = modelentry.setdefault(field, {})
                count = 0
                for value in depends:
                    path, target_field = value.split('#')
                    cls = model
                    agg_path = []
                    for symbol in path.split('.'):
                        agg_path.append(symbol)
                        try:
                            if fieldentry.get(cls):
                                fieldentry[cls][count]['depends'] = symbol
                        except IndexError:
                            pass
                        is_backrelation = False
                        try:
                            rel = cls._meta.get_field(symbol).rel
                            cls = cls._meta.get_field(symbol).related_model
                        except FieldDoesNotExist:
                            is_backrelation = True
                            rel = getattr(cls, symbol).field.rel
                            cls = getattr(cls, symbol).field.rel.related_model
                        fieldentry.setdefault(cls, []).append({
                            'depends': '', 'backrel': is_backrelation,
                            'rel': reltype(rel), 'path': tuple(agg_path[:])})
                    fieldentry[cls][-1]['depends'] = target_field
                    count += 1

        # reorder data for better graph handling
        final = {}
        model_mapping = {}
        for model, fielddata in store.iteritems():
            for field, modeldata in fielddata.iteritems():
                for depmodel, data in modeldata.iteritems():
                    model_mapping[modelname(model)] = model
                    for comb in ((modelname(depmodel), dep['depends']
                      if is_computed_field(depmodel, dep['depends']) else '#') for dep in data):
                        final.setdefault(comb, set()).add((modelname(model), field))

        # fix tree: move all sub updates of field dependencies under '#'
        # leads possibly to double paths (removed later if redundant)
        for key, value in final.iteritems():
            model, field = key
            if field == '#':
                for skey, svalue in final.iteritems():
                    smodel, sfield = skey
                    if model == smodel and field != sfield:
                        value.update(svalue)
        return store, final, model_mapping

    def insert_data(self, data):
        for node, value in data.iteritems():
            self.add_node(Node(node))
            for node in value:
                self.add_node(Node(node))
        for left, value in data.iteritems():
            for right in value:
                edge = Edge(Node(left), Node(right))
                self.add_edge(edge)

    def generate_lookup_map(self):
        # TODO: premerge queryset logic for signal handler
        # reorder to {changed_model: {needs_update_model: {computed_field: dep_data}}}
        final = OrderedDict()
        for model, fielddata in self.data.iteritems():
            for field, modeldata in fielddata.iteritems():
                for depmodel, data in modeldata.iteritems():
                    final.setdefault(depmodel, {}).setdefault(model, {}).setdefault(field, data)

        table = {}
        for left_node, right_nodes in self.cleaned.iteritems():
            lmodel, lfield = left_node
            lmodel = self.model_mapping[lmodel]
            rstore = table.setdefault(lmodel, {}).setdefault(lfield, {})
            for right_node in right_nodes:
                rmodel, rfield = right_node
                rmodel = self.model_mapping[rmodel]
                rstore.setdefault(rmodel, {}).setdefault(rfield, []).extend(
                    final[lmodel][rmodel][rfield])

        self.lookup_map = table
        #self.dump_lookup_map()


        # merge queries if (AND):
        #   - same model
        #   - same rel type and same backrel
        #   - same path
        #   - different path, if possible (join paths with Q objects), not possible for fk backrel
        # create lambda funcs iterator to be run in handler?
        func_table = {}
        for lmodel, data in table.iteritems():
            for lfield, fielddata in data.iteritems():
                store = func_table.setdefault(lmodel, {}).setdefault(lfield, {})
                for rmodel, rfielddata in fielddata.iteritems():
                    gen = FuncGenerator(rmodel, rfielddata)
                    gen.resolve_all()
                    store[rmodel] = gen.final

        return func_table


############################
# handler functions creation
############################
from django.db.models import Q
from functools import partial
from copy import deepcopy
from pprint import pprint


def generate_Q(paths, instance):
    if paths:
        query_obj = Q(**{paths.pop(): instance})
        while paths:
            query_obj |= Q(**{paths.pop(): instance})
        return query_obj
    return Q()


def fk_relation(model, paths, fields, instance):
    for elem in model.objects.filter(generate_Q(paths, instance)).distinct():
        elem.save(update_fields=fields)


def fk_backrelation(model, paths, fields, instance):
    # FIXME: showstopper - how to deal with .foo.bar.baz_set? --> multiple chained rel types
    for path in paths:
        fieldname = getattr(model, ''.join(path)).rel.field.name
        getattr(instance, fieldname).save(update_fields=fields)


def m2m_relation(model, paths, fields, instance):
    for elem in model.objects.filter(generate_Q(paths, instance)).distinct():
        elem.save(update_fields=fields)


class FuncGenerator(object):
    def __init__(self, model, fielddata):
        self.model = model
        self.data = deepcopy(fielddata)
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

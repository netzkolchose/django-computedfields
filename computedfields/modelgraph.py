from graphviz import Digraph
from collections import OrderedDict
from django.core.exceptions import FieldDoesNotExist


def resolve_dep_string(computed_models):
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
                        cls = cls._meta.get_field(symbol).related_model
                    except FieldDoesNotExist:
                        is_backrelation = True
                        cls = getattr(cls, symbol).field.rel.related_model
                    fieldentry.setdefault(cls, []).append({
                        'depends': '', 'backrel': is_backrelation, 'path': tuple(agg_path[:])})
                fieldentry[cls][-1]['depends'] = target_field
                count += 1

    #for k, v in store.iteritems():
    #    print k
    #    for vk, vv in v.iteritems():
    #        print '    ', vk, vv

    # reorder to {changed_model: {needs_update_model: {computed_field: dep_data}}}
    final = OrderedDict()
    for model, fielddata in store.iteritems():
        for field, modeldata in fielddata.iteritems():
            for depmodel, data in modeldata.iteritems():
                final.setdefault(depmodel, {}).setdefault(model, {}).setdefault(field, data)

    #print 'final:'
    #for k, v in final.iteritems():
    #    print k
    #    for vk, vv in v.iteritems():
    #        print '    ', vk
    #        for vvk, vvv in vv.iteritems():
    #            print '        ', vvk, vvv

    return final


class Node(object):
    def __init__(self, model):
        self.model = model
        self.name = modelname(model)
        self.incoming = []
        self.outgoing = []

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()


class CycleException(Exception):
    pass


class Graph(object):
    def __init__(self, data):
        self.data = data
        self.nodes = self._create_node_mapping()
        self.edges = self._create_edges()
        self._apply_edges()

    def _apply_edges(self):
        for left, right, path in self.edges:
            self.nodes[left].outgoing.append((self.nodes[right], tuple(reversed(path))))
            self.nodes[right].incoming.append((self.nodes[left], path))

    def _create_node_mapping(self):
        nodes = {}
        for model, data in self.data.iteritems():
            if not nodes.get(model):
                nodes[model] = Node(model)
            for submodel in data:
                if not nodes.get(submodel):
                    nodes[submodel] = Node(submodel)
        return nodes

    def _create_edges(self):
        """
        edges: {(source_model, target_model, path): [(source_field, target_field)]}
        :return:
        """
        edges = {}
        for model, data in self.data.iteritems():
            for submodel, subdata in data.iteritems():
                paths = set()
                for field, deps in subdata.iteritems():
                    for dep in deps:
                        paths.add(dep['path'])
                for path in paths:
                    for field, deps in subdata.iteritems():
                        for dep in deps:
                            if dep['path'] == path:
                                edges.setdefault(
                                    (model, submodel, path), []).append((dep['depends'], field))
        return edges

    def render(self):
        dot = Digraph(comment='computed fields dependencies')
        # insert nodes
        for node in self.nodes.values():
            dot.node(node.name, node.name)
        # insert edges
        for edge, data in self.edges.iteritems():
            from_, to_, path = edge
            dot.edge(self.nodes[from_].name, self.nodes[to_].name, label='.'.join(path))
        dot.view()

    def is_sublist(self, needle, haystack):
        if not needle:
            return True
        if not haystack:
            return False
        max_k = len(needle) - 1
        k = 0
        for elem in haystack:
            if elem != needle[k]:   # reset k to find later occurence
                k = 0
                continue
            if k == max_k:          # needle exhausted
                return True
            k += 1
        return False

    def sublist_occurence(self, needle, haystack):
        max_k = len(needle) - 1
        k = 0
        for i, elem in enumerate(haystack):
            if elem != needle[k]:   # reset k to find later occurence
                k = 0
                continue
            if k == max_k:          # needle exhausted
                return i - k
            k += 1
        return -1

    def sublist_occurences(self, needle, haystack):
        if not needle or not haystack:
            return 0
        count = 0
        idx = self.sublist_occurence(needle, haystack)
        while idx != -1:
            count += 1
            haystack = haystack[idx+1:]
            idx = self.sublist_occurence(needle, haystack)
        return count

    def _walk(self, final_cycles, entry, seen, cycle=None):
        seen.append(entry)
        if not cycle:
            cycle = []
        if entry in seen:
            if seen.count(entry) > 2:   # prolly cycling
                if len(cycle) > 50:
                    if self.sublist_occurences(cycle, seen) > 2:
                        final_cycles.append(cycle)
                        raise CycleException
                cycle.append(entry)
        for next_entry, path in entry.outgoing:
            self._walk(final_cycles, next_entry, seen[:], cycle[:])
        return

    def find_cycle(self, cycles):
        if not cycles:
            return []
        k = 0
        sentinel = cycles[k]
        next_idx = cycles[k+1:].index(sentinel)
        occurences = self.sublist_occurences(cycles[:next_idx], cycles)
        while not occurences:
            k += 1
            sentinel = cycles[k]
            next_idx = cycles[k+1:].index(sentinel)
            occurences = self.sublist_occurences(cycles[:next_idx], cycles)
        return cycles[:next_idx+1]

    def walk(self):
        for entry in self.data:
            seen = []
            cycles = []
            try:
                self._walk(cycles, self.nodes[entry], seen)
            except CycleException:
                pass
            print  'entry#####', entry
            #print 'seen    ', seen
            #print 'cycles  ', cycles[0]
            print 'cycle  ', self.find_cycle(cycles[0])
















AL = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
al = iter(AL)


def modelname(model):
    return '%s.%s' % (model._meta.app_label, model._meta.verbose_name)


def create_mapping(dot, dependent_models, entry=None):
    mapping = {}
    for k, v in dependent_models.iteritems():
        if k not in mapping:
            c = next(al)
            mapping[k] = c
            if k == entry:
                dot.node(c, modelname(k), shape='box')
            else:
                dot.node(c, modelname(k))
        for weight, model, value, field in v:
            if model not in mapping:
                c = next(al)
                mapping[model] = c
                if model == entry:
                    dot.node(c, modelname(model), shape='box')
                else:
                    dot.node(c, modelname(model))
    return mapping


def walk(entry, dot, mapping, dependent_models, depth, c):
    if not depth:
        #raise Exception('recursion')
        return
    for weight, model, value, field in sorted(dependent_models.get(entry, [])):
        dot.edge(mapping[entry], mapping[model], label='%s (%s)' % (value, c))
        walk(model, dot, mapping, dependent_models, depth-1, c+1)
    return


def draw_field_dependencies(dependent_models, entry=None):
    dot = Digraph(comment='computed fields dependencies')
    mapping = create_mapping(dot, dependent_models, entry)
    c = 0
    if entry:
        walk(entry, dot, mapping, dependent_models, 2, 0)
        dot.view()
        return
    # base graph
    for k, v in dependent_models.iteritems():
        for weight, model, value, field in sorted(v):
            dot.edge(mapping[k], mapping[model], label='%s (%s)' % (value, c))
            c += 1
    dot.view()

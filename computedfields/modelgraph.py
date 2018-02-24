from graphviz import Digraph
from collections import OrderedDict
from django.core.exceptions import FieldDoesNotExist
from itertools import cycle, tee, izip


def pairwise(iterable):
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)


def is_computed_field(model, field):
    if hasattr(model, '_computed_fields') and field in model._computed_fields:
        return True
    return False


def render_graph(data):
    dot = Digraph(comment='computed fields dependencies')
    # get all nodes
    nodes = set()
    for node, value in data.iteritems():
        nodes.add(node)
        for node in value:
            nodes.add(node)
    # insert nodes
    for node in nodes:
        dot.node('.'.join(node), '.'.join(node))
    # insert edges
    for left, value in data.iteritems():
        for right in value:
            dot.edge('.'.join(left), '.'.join(right))
    dot.view()


def build_new_graph(data):
    graph = NewGraph()
    for node, value in data.iteritems():
        graph.add_node(NewNode(node))
        for node in value:
            graph.add_node(NewNode(node))

    for left, value in data.iteritems():
        for right in value:
            edge = Edge(NewNode(left), NewNode(right))
            graph.add_edge(edge)

    graph.remove_redundant_paths()
    graph.render()


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


class NewNode(object):
    instances = {}

    def __new__(cls, *args, **kwargs):
        if args[0] in cls.instances:
            return cls.instances[args[0]]
        instance = super(NewNode, cls).__new__(cls, *args, **kwargs)
        cls.instances[args[0]] = instance
        return instance

    def __init__(self, data):
        self.data = data
        self.incoming = set()
        self.outgoing = set()

    def __str__(self):
        return '.'.join(self.data)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self.data == other.data

    def __ne__(self, other):
        return not self.__eq__(other)


class NewGraph(object):
    def __init__(self):
        self.nodes = set()
        self.edges = set()

    def add_node(self, node):
        self.nodes.add(node)
        for edge in node.incoming:
            if edge.left in self.nodes:
                self.edges.add(edge)
        for edge in node.outgoing:
            if edge.right in self.nodes:
                self.edges.add(edge)

    def remove_node(self, node):
        self.nodes.remove(node)

    def add_edge(self, edge):
        self.edges.add(edge)
        self.nodes.add(edge.left)
        self.nodes.add(edge.right)
        edge.left.outgoing.add(edge)
        edge.right.incoming.add(edge)

    def remove_edge(self, edge):
        self.edges.remove(edge)
        edge.left.outgoing.remove(edge)
        edge.right.incoming.remove(edge)

    def render(self):
        dot = Digraph()
        for node in self.nodes:
            dot.node(str(node), str(node))
        for edge in self.edges:
            dot.edge(str(edge.left), str(edge.right))
        dot.view()

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

    def get_edge_paths(self):
        left_edges = {}
        paths = []
        for edge in self.edges:
            left_edges.setdefault(edge.left, []).append(edge)
        for edge in self.edges:
            self._get_edge_paths(edge, left_edges, paths)
        return paths

    def get_node_paths(self):
        paths = self.get_edge_paths()
        node_paths = []
        for path in paths:
            node_paths.append([edge.left for edge in path] + [path[-1].right])
        return node_paths

    def is_sublist(self, needle, haystack):
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

    def can_replace_path(self, needle, haystack):
        if not set(haystack).issuperset(needle):
            return False
        if self.is_sublist(needle, haystack):
            return False
        return True

    def compare_start_to_end_paths(self, new_paths, base_paths):
        base_points = set((path[0], path[-1]) for path in base_paths)
        new_points = set((path[0], path[-1]) for path in new_paths)
        return base_points == new_points

    def remove_redundant_paths(self):
        paths = self.get_node_paths()
        possible_replaces = []
        for p in paths:
            for q in paths:
                if self.can_replace_path(q, p):
                    possible_replaces.append((q, p))
        for candidate, replacement in possible_replaces:
            edges = [Edge(*nodes) for nodes in pairwise(candidate)]
            for edge in edges:
                self.remove_edge(edge)
                # make sure all startpoints will still update all endpoints
                if not self.compare_start_to_end_paths(self.get_node_paths(), paths):
                    self.add_edge(edge)



def check_dependencies(store):
    agg = {}
    for model, fielddata in store.iteritems():
            for field, modeldata in fielddata.iteritems():
                for depmodel, data in modeldata.iteritems():
                    for comb in ((modelname(depmodel), dep['depends']
                          if is_computed_field(depmodel, dep['depends']) else '#') for dep in data):
                        agg.setdefault(comb, set()).add((modelname(model), field))

    # fix tree: move all sub updates of field dependencies under '#'
    # leads possibly to double paths
    for key, value in agg.iteritems():
        model, field = key
        if field == '#':
            for skey, svalue in agg.iteritems():
                smodel, sfield = skey
                if model == smodel and field != sfield:
                    value.update(svalue)

    for k, v in agg.iteritems():
        print k
        for e in v:
            print '  ', e
    #render_graph(agg)
    build_new_graph(agg)


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

    for k, v in store.iteritems():
        print k
        for vk, vv in v.iteritems():
            print '    ', vk, vv
    print
    check_dependencies(store)

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

    def render_with_cycles(self, cycles):
        cycle_edges = []
        # prepare cycles edges
        for cycle in cycles:
            for i in range(len(cycle)-1):
                cycle_edges.append((cycle[i].model, cycle[i+1].model))
            cycle_edges.append((cycle[-1].model, cycle[0].model))

        dot = Digraph(comment='computed fields dependencies')
        # insert nodes
        for node in self.nodes.values():
            dot.node(node.name, node.name)
        # insert edges
        for edge, data in self.edges.iteritems():
            from_, to_, path = edge
            if (from_, to_) in cycle_edges:
                dot.edge(self.nodes[from_].name, self.nodes[to_].name,
                         label='.'.join(path), color="red")
            else:
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

    def equal_cycles(self, a, b):
        if len(a) != len(b):
            return False
        if not len(a):
            return True
        if set(a) != set(b):
            return False
        b_cycle = cycle(b)
        b_elem = next(b_cycle)
        while b_elem != a[0]:
            b_elem = next(b_cycle)
        for elem in a[1:]:
            if elem != next(b_cycle):
                return False
        return True

    def unique_cycles(self, cycles):
        if not cycles:
            return []
        result = [cycles[0]]
        while cycles[1:]:
            candidate = cycles.pop()
            unique = True
            for cycle in result:
                if self.equal_cycles(candidate, cycle):
                    unique = False
                    break
            if unique:
                result.append(candidate)
        return result

    def walk(self):
        all_cycles = []
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
            all_cycles.append(self.find_cycle(cycles[0]))
        print 'unique cycles:', self.unique_cycles(all_cycles)
        self.render_with_cycles(self.unique_cycles(all_cycles))

    def _better_walk(self, entry, depth=0):
        if depth == 5:
            return
        for next_entry, path in entry.outgoing:
            #print 'sub', depth, next_entry, '.'.join(path)
            #print next_entry.data
            self._better_walk(next_entry, depth+1)

    def better_walk(self):
        for entry in self.data:
            print 'entry:', entry
            self._better_walk(self.nodes[entry])

















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

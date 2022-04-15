from collections import Counter
from django.core.management.base import BaseCommand
from computedfields.models import active_resolver
from computedfields.graph import ComputedModelsGraph, CycleException


# maps amount of cycles on a specific edge to color (more than 3 is always blue)
COLORS = {1: 'red', 2: 'green', 3: 'blue'}

# color legend for cycling
LEGEND = '''<<table border="0" cellpadding="0" cellspacing="0" cellborder="0">
    <tr>
        <td align="left"><font color="black">black</font></td>
        <td>&nbsp;&nbsp;</td>
        <td align="left">0 cycles</td>
    </tr>
    <tr>
        <td align="left"><font color="red">red</font></td>
        <td>&nbsp;&nbsp;</td>
        <td align="left">1 cycle</td>
    </tr>
    <tr>
        <td align="left"><font color="green">green</font></td>
        <td>&nbsp;&nbsp;</td>
        <td align="left">2 cycles</td>
    </tr>
    <tr>
        <td align="left"><font color="blue">blue</font></td>
        <td>&nbsp;&nbsp;</td>
        <td align="left">2+ cycles</td>
    </tr>
</table>>'''


class Command(BaseCommand):
    help = 'Show dependency graph for computed fields.'

    def add_arguments(self, parser):
        parser.add_argument('filename', nargs='+', type=str)

    def handle(self, *args, **options):
        graph = ComputedModelsGraph(active_resolver.computed_models)
        try:
            graph.get_edgepaths()
            graph.render(filename=options['filename'][0])
        except CycleException:
            # graph is not cycle free, get all cycles
            # we draw the graph with
            cycles = graph.edge_cycles
            counter = Counter()
            for cycle in cycles:
                counter.update(cycle)
            mark_edges = dict((edge, {'color': COLORS.get(amount, 'blue')})
                              for edge, amount in counter.items())
            dot = graph.get_dot(mark_edges=mark_edges)
            with dot.subgraph(name='cluster_1') as c:
                c.attr(label='Colors - edge in cycles', color='white')
                c.node('1', label=LEGEND, shape='plaintext', color='black')
            dot.render(filename=options['filename'][0], cleanup=True)
            print(self.style.WARNING(f'Warning -  {len(cycles)} cycles in dependencies found:'))
            for cycle in cycles:
                print(graph.edgepath_to_nodepath(cycle))

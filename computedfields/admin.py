from json import dumps
from django.contrib import admin
from django.apps import apps
from django.conf import settings
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.urls import reverse, NoReverseMatch, path
from django.shortcuts import render
from django.core.exceptions import ObjectDoesNotExist
from .models import ComputedFieldsAdminModel, ContributingModelsModel
from .resolver import active_resolver
from .graph import ComputedModelsGraph
from .settings import settings
try:
    import pygments
    from pygments.lexers import JsonLexer
    from pygments.formatters import HtmlFormatter
except ImportError:
    pygments = False
try:
    from graphviz import Digraph
except ImportError:
    Digraph = False


class ComputedModelsAdmin(admin.ModelAdmin):
    """
    Shows all ``ComputedFieldsModel`` models with their field dependencies
    in the admin. Also renders the dependency graphs if the :mod:`graphviz`
    package is installed.
    """
    actions = None
    change_list_template = 'computedfields/change_list.html'
    list_display = ('name', 'computed_fields', 'dependencies', 'local_computed_fields_mro', 'modelgraph')
    list_display_links = None

    def has_add_permission(self, request):
        ""
        return False

    def has_delete_permission(self, request, obj=None):
        ""
        return False

    def dependencies(self, inst):
        """
        List dependencies for model.
        """
        model = apps.get_model(inst.app_label, inst.model)
        cf_models = active_resolver.computed_models
        deps = {}
        for fieldname, field in cf_models.get(model).items():
            deps[fieldname] = field._computed['depends']
        data = dumps(deps, indent=4, sort_keys=True)
        if pygments:
            data = mark_safe(
                pygments.highlight(data, JsonLexer(stripnl=False),
                                   HtmlFormatter(noclasses=True, nowrap=True)))
        return format_html('<pre>{}</pre>', data)

    def computed_fields(self, inst):
        """
        List computed fields for model.
        """
        model = apps.get_model(inst.app_label, inst.model)
        cfs = list(active_resolver.computed_models[model].keys())
        data = dumps(cfs, indent=4, sort_keys=True)
        if pygments:
            data = mark_safe(
                pygments.highlight(data, JsonLexer(stripnl=False),
                                   HtmlFormatter(noclasses=True, nowrap=True)))
        return format_html('<pre>{}</pre>', data)

    def local_computed_fields_mro(self, inst):
        """
        List MRO for local computed fields on model.
        """
        model = apps.get_model(inst.app_label, inst.model)
        entry = active_resolver._local_mro[model]
        base = entry['base']
        deps = {'mro': base, 'fields': {}}
        for field, value in entry['fields'].items():
            deps['fields'][field] = [name for pos, name in enumerate(base) if value & (1 << pos)]
        data = dumps(deps, indent=4, sort_keys=False)
        if pygments:
            data = mark_safe(pygments.highlight(data, JsonLexer(stripnl=False),
                                                HtmlFormatter(noclasses=True, nowrap=True)))
        return format_html('<pre>{}</pre>', data)

    def name(self, obj):
        """
        Resolve modelname, optionally with link.
        """
        name = escape(f'{obj.app_label}.{obj.model}')
        try:
            _url = escape(reverse(f'admin:{obj.app_label}_{obj.model}_changelist'))
        except NoReverseMatch:
            return name
        return format_html('<a href="{}">{}</a>', _url, name)

    def get_urls(self):
        urls = super(ComputedModelsAdmin, self).get_urls()
        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name
        databaseview_urls = [
            path(r'computedfields/rendergraph/',
                self.admin_site.admin_view(self.render_graph),
                name=f'{app_label}_{model_name}_computedfields_rendergraph'),
            path(r'computedfields/renderuniongraph/',
                self.admin_site.admin_view(self.render_uniongraph),
                name=f'{app_label}_{model_name}_computedfields_renderuniongraph'),
            path(r'computedfields/modelgraph/<int:modelid>/',
                self.admin_site.admin_view(self.render_modelgraph),
                name=f'{app_label}_{model_name}_computedfields_modelgraph'),
        ]
        return databaseview_urls + urls

    def modelgraph(self, inst):
        """
        Link to show modelgraph.
        """
        model = apps.get_model(inst.app_label, inst.model)
        if not active_resolver._local_mro.get(model, None):
            return 'None'
        _url = reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_computedfields_modelgraph',
                        args=[inst.id])
        return mark_safe(f'''<a href="{_url}" target="popup"
            onclick="javascript:open('', 'popup', 'height=400,width=600,resizable=yes')">
            ModelGraph</a>''')

    def render_graph(self, request, extra_context=None):
        """
        Render intermodel graph view.
        """
        error = 'graphviz must be installed to use this feature.'
        dot = ''
        if Digraph:
            error = ''
            graph = active_resolver._graph
            if not graph:
                # we are in map file mode - create new graph
                graph = ComputedModelsGraph(active_resolver.computed_models)
                graph.get_edgepaths()
            dot = mark_safe(str(graph.get_dot()).replace('\n', ' '))
        return render(request, 'computedfields/graph.html', {'error': error, 'dot': dot})

    def render_uniongraph(self, request, extra_context=None):
        """
        Render union graph view.
        """
        error = 'graphviz must be installed to use this feature.'
        dot = ''
        if Digraph:
            error = ''
            graph = active_resolver._graph
            if not graph:
                # we are in map file mode - create new graph
                graph = ComputedModelsGraph(active_resolver.computed_models)
                graph.get_edgepaths()
            uniongraph = graph.get_uniongraph()
            dot = mark_safe(str(uniongraph.get_dot()).replace('\n', ' '))
        return render(request, 'computedfields/graph.html', {'error': error, 'dot': dot})

    def render_modelgraph(self, request, modelid, extra_context=None):
        """
        Render modelgraph view.
        """
        try:
            inst = self.model._base_manager.get(pk=modelid)
            model = apps.get_model(inst.app_label, inst.model)
        except ObjectDoesNotExist:
            error = 'illegal value for model'
            return render(request, 'computedfields/graph.html', {'error': error, 'dot': ''})
        error = 'graphviz must be installed to use this feature.'
        dot = ''
        if Digraph:
            error = ''
            graph = active_resolver._graph
            if not graph:
                # we are in map file mode - create new graph
                graph = ComputedModelsGraph(active_resolver.computed_models)
                graph.get_edgepaths()
                graph.get_uniongraph()
            modelgraph = graph.modelgraphs.get(model, None)
            if modelgraph:
                dot = mark_safe(str(modelgraph.get_dot()).replace('\n', ' '))
            else:
                error = 'Model has no local field dependencies.'
        return render(request, 'computedfields/graph.html', {'error': error, 'dot': dot})


class ContributingModelsAdmin(admin.ModelAdmin):
    """
    Shows models with cf contributing local fk fields.
    """
    actions = None
    list_display = ('name', 'fk_fields')
    list_display_links = None

    def has_add_permission(self, request):
        ""
        return False

    def has_delete_permission(self, request, obj=None):
        ""
        return False

    def fk_fields(self, inst):
        """
        List contributing fk field names.
        """
        model = apps.get_model(inst.app_label, inst.model)
        vul = active_resolver._fk_map.get(model)
        if vul:
            vul = list(vul)
        vul = dumps(vul, indent=4, sort_keys=True)
        if pygments:
            vul = mark_safe(pygments.highlight(vul, JsonLexer(stripnl=False),
                                               HtmlFormatter(noclasses=True, nowrap=True)))
        return format_html('<pre>{}</pre>', vul)

    def name(self, obj):
        """
        Resolve modelname, optionally with link.
        """
        name = escape(f'{obj.app_label}.{obj.model}')
        try:
            _url = escape(reverse(f'admin:{obj.app_label}_{obj.model}_changelist'))
        except NoReverseMatch:
            return name
        return format_html('<a href="{}">{}</a>', _url, name)


if settings.COMPUTEDFIELDS_ADMIN:
    admin.site.register(ComputedFieldsAdminModel, ComputedModelsAdmin)
    admin.site.register(ContributingModelsModel, ContributingModelsAdmin)

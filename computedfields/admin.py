from django.contrib import admin
from computedfields.models import ComputedFieldsAdminModel, ComputedFieldsModelType, ContributingModelsModel
from django.apps import apps
from django.conf import settings
from json import dumps
from django.utils.html import escape, mark_safe, format_html
from django.urls import reverse, NoReverseMatch
from django.conf.urls import url
from django.shortcuts import render
from django.core.exceptions import ObjectDoesNotExist
try:
    import pygments
    from pygments.lexers import PythonLexer, JsonLexer
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

    def has_add_permission(self, request, obj=None):
        ""
        return False

    def has_delete_permission(self, request, obj=None):
        ""
        return False

    def dependencies(self, inst):
        model = apps.get_model(inst.app_label, inst.model)
        deps = ComputedFieldsModelType._computed_models
        s = dumps(deps.get(model), indent=4, sort_keys=True)
        if pygments:
            s = mark_safe(
                    pygments.highlight(s, JsonLexer(stripnl=False),
                        HtmlFormatter(noclasses=True, nowrap=True)))
        return format_html(u'<pre>{}</pre>', s)
    
    def computed_fields(self, inst):
        model = apps.get_model(inst.app_label, inst.model)
        cfs = list(model._computed_fields.keys())
        s = dumps(cfs, indent=4, sort_keys=True)
        if pygments:
            s = mark_safe(
                    pygments.highlight(s, JsonLexer(stripnl=False),
                        HtmlFormatter(noclasses=True, nowrap=True)))
        return format_html(u'<pre>{}</pre>', s)
    
    def local_computed_fields_mro(self, inst):
        model = apps.get_model(inst.app_label, inst.model)
        cfs = model._computed_fields.keys()
        entry = ComputedFieldsModelType._local_mro[model]
        base = entry['base']
        deps = {'mro': base, 'fields': {}}
        for field, value in entry['fields'].items():
            deps['fields'][field] = [name for pos, name in enumerate(base) if value & (1 << pos)]
        s = dumps(deps, indent=4, sort_keys=False)
        if pygments:
            s = mark_safe(
                pygments.highlight(s, JsonLexer(stripnl=False), HtmlFormatter(noclasses=True, nowrap=True)))
        return format_html(u'<pre>{}</pre>', s)

    def name(self, obj):
        name = escape(u'%s.%s' % (obj.app_label, obj.model))
        try:
            url = escape(reverse('admin:%s_%s_changelist' % (obj.app_label, obj.model)))
        except NoReverseMatch:
            return name
        return format_html(u'<a href="{}">{}</a>', url, name)

    def get_urls(self):
        urls = super(ComputedModelsAdmin, self).get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        databaseview_urls = [
            url('^computedfields/rendergraph/$',
                self.admin_site.admin_view(self.render_graph),
                name='%s_%s_computedfields_rendergraph' % info),
            url('^computedfields/renderuniongraph/$',
                self.admin_site.admin_view(self.render_uniongraph),
                name='%s_%s_computedfields_renderuniongraph' % info),
            url('^computedfields/modelgraph/(?P<modelid>\d+)/$',
                self.admin_site.admin_view(self.render_modelgraph),
                name='%s_%s_computedfields_modelgraph' % info),
        ]
        return databaseview_urls + urls

    def modelgraph(self, inst):
        model = apps.get_model(inst.app_label, inst.model)
        if not ComputedFieldsModelType._local_mro.get(model, None):
            return 'None'
        url = reverse('admin:%s_%s_computedfields_modelgraph' %
                (self.model._meta.app_label,  self.model._meta.model_name),  args=[inst.id])
        return  mark_safe('''<a href="%s" target="popup"
                   onclick="javascript:open('', 'popup', 'height=400,width=600,resizable=yes')">ModelGraph</a>''' % url)

    def render_graph(self, request, extra_context=None):
        error = 'graphviz must be installed to use this feature.'
        dot = ''
        if Digraph:
            error = ''
            graph = ComputedFieldsModelType._graph
            if not graph:
                # we are in map file mode - create new graph
                from computedfields.graph import ComputedModelsGraph
                graph = ComputedModelsGraph(ComputedFieldsModelType._computed_models)
                graph.remove_redundant()
            dot = mark_safe(str(graph.get_dot()).replace('\n', ' '))
        return render(request, 'computedfields/graph.html', {'error': error, 'dot': dot})
    
    def render_uniongraph(self, request, extra_context=None):
        error = 'graphviz must be installed to use this feature.'
        dot = ''
        if Digraph:
            error = ''
            graph = ComputedFieldsModelType._graph
            if not graph:
                # we are in map file mode - create new graph
                from computedfields.graph import ComputedModelsGraph
                graph = ComputedModelsGraph(ComputedFieldsModelType._computed_models)
                graph.remove_redundant()
            uniongraph = graph.get_uniongraph()
            dot = mark_safe(str(uniongraph.get_dot()).replace('\n', ' '))
        return render(request, 'computedfields/graph.html', {'error': error, 'dot': dot})
    
    def render_modelgraph(self, request, modelid, extra_context=None):
        try:
            inst = self.model.objects.get(pk=modelid)
            model = apps.get_model(inst.app_label, inst.model)
        except ObjectDoesNotExist:
            error = 'illegal value for model'
            return render(request, 'computedfields/graph.html', {'error': error, 'dot': ''})
        error = 'graphviz must be installed to use this feature.'
        dot = ''
        if Digraph:
            error = ''
            graph = ComputedFieldsModelType._graph
            if not graph:
                # we are in map file mode - create new graph
                from computedfields.graph import ComputedModelsGraph
                graph = ComputedModelsGraph(ComputedFieldsModelType._computed_models)
                graph.remove_redundant()
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
    list_display = ('name', 'vulerable_fk_fields')
    list_display_links = None

    def has_add_permission(self, request, obj=None):
        ""
        return False

    def has_delete_permission(self, request, obj=None):
        ""
        return False
    
    def vulerable_fk_fields(self, inst):
        model = apps.get_model(inst.app_label, inst.model)
        vul = ComputedFieldsModelType._fk_map.get(model)
        if vul:
            vul = list(vul)
        vul = dumps(vul, indent=4, sort_keys=True)
        if pygments:
            vul = mark_safe(
                    pygments.highlight(vul, JsonLexer(stripnl=False),
                        HtmlFormatter(noclasses=True, nowrap=True)))
        return format_html(u'<pre>{}</pre>', vul)

    def name(self, obj):
        name = escape(u'%s.%s' % (obj.app_label, obj.model))
        try:
            url = escape(reverse('admin:%s_%s_changelist' % (obj.app_label, obj.model)))
        except NoReverseMatch:
            return name
        return format_html(u'<a href="{}">{}</a>', url, name)


if getattr(settings, 'COMPUTEDFIELDS_ADMIN', False):
    admin.site.register(ComputedFieldsAdminModel, ComputedModelsAdmin)
    admin.site.register(ContributingModelsModel, ContributingModelsAdmin)

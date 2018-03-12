# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from computedfields.models import ComputedFieldsAdminModel, ComputedFieldsModelType
from django.apps import apps
from django.conf import settings
from json import dumps
from django.utils.html import escape, mark_safe
from django.urls import reverse, NoReverseMatch
from django.conf.urls import url
from django.shortcuts import render
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
    in the admin. Also renders the dependency graph if the :mod:`graphviz`
    package is installed.
    """
    actions = None
    change_list_template = 'computedfields/change_list.html'
    list_display = ('name', 'dependencies')
    list_display_links = None

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def dependencies(self, inst):
        model = apps.get_model(inst.app_label, inst.model)
        deps = ComputedFieldsModelType._computed_models
        s = dumps(deps.get(model), indent=4, sort_keys=True)
        if pygments:
            s = pygments.highlight(
                s, JsonLexer(stripnl=False), HtmlFormatter(noclasses=True, nowrap=True))
        return u'<pre>%s</pre>' % s
    dependencies.allow_tags = True

    def name(self, obj):
        name = escape(u'%s.%s' % (obj.app_label, obj.model))
        try:
            url = escape(reverse('admin:%s_%s_changelist' % (obj.app_label, obj.model)))
        except NoReverseMatch:
            return name
        return u'<a href="%s">%s</a>' % (url, name)
    name.allow_tags = True

    def get_urls(self):
        urls = super(ComputedModelsAdmin, self).get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        databaseview_urls = [
            url('^computedfields/rendergraph/$',
                self.admin_site.admin_view(self.render_graph),
                name='%s_%s_computedfields_rendergraph' % info),
        ]
        return databaseview_urls + urls

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


if hasattr(settings, 'COMPUTEDFIELDS_ADMIN') and settings.COMPUTEDFIELDS_ADMIN:
    admin.site.register(ComputedFieldsAdminModel, ComputedModelsAdmin)

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.apps import AppConfig
import sys


class ComputedfieldsConfig(AppConfig):
    name = 'computedfields'

    def ready(self):
        # do not run graph reduction in migrations
        for token in ('makemigrations', 'migrate', 'help', 'rendergraph'):
            if token in sys.argv:  # pragma: no cover
                return

        # normal startup
        from computedfields.models import ComputedFieldsModelType
        ComputedFieldsModelType._resolve_dependencies()

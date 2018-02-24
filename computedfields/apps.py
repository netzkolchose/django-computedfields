# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.apps import AppConfig


class ComputedfieldsConfig(AppConfig):
    name = 'computedfields'

    def ready(self):
        from computedfields.models import ComputedFieldsModelType
        ComputedFieldsModelType._resolve_dependencies()

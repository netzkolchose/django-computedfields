from django.apps import AppConfig
import sys


class ComputedfieldsConfig(AppConfig):
    name = 'computedfields'

    def ready(self):
        # do not run graph reduction in migrations
        for token in ('makemigrations', 'migrate', 'help', 'rendergraph', 'createmap'):
            if token in sys.argv:  # pragma: no cover
                return

        # normal startup
        from computedfields.models import ComputedFieldsModelType
        ComputedFieldsModelType._resolve_dependencies()

        # connect signals
        from computedfields.handlers import (
            postsave_handler, predelete_handler, postdelete_handler, m2m_handler, get_old_handler)
        from django.db.models.signals import post_save, m2m_changed, pre_delete, post_delete, pre_save

        pre_save.connect(
            get_old_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD_PRESAVE')
        post_save.connect(
            postsave_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD')
        pre_delete.connect(
            predelete_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD_PREDELETE')
        post_delete.connect(
            postdelete_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD_POSTDELETE')
        m2m_changed.connect(
            m2m_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD_M2M')

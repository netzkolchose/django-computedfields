import sys
from django.apps import AppConfig
from django.db.models.signals import class_prepared
from .resolver import BOOT_RESOLVER
from .settings import settings


class ComputedfieldsConfig(AppConfig):
    name = 'computedfields'

    def __init__(self, *args, **kwargs):
        super(ComputedfieldsConfig, self).__init__(*args, **kwargs)
        class_prepared.connect(BOOT_RESOLVER.add_model)
        self.settings = settings


    def ready(self):
        # disconnect model discovery to avoid resolver issues with models created later at runtime
        class_prepared.disconnect(BOOT_RESOLVER.add_model)

        # do not run graph reduction in migrations and own commands,
        # that deal with it in their own specific way
        for token in ('makemigrations', 'migrate', 'help', 'rendergraph', 'createmap'):
            if token in sys.argv:  # pragma: no cover
                BOOT_RESOLVER.initialize(True)
                return

        # normal startup
        BOOT_RESOLVER.initialize()

        # connect signals
        from computedfields.handlers import (
            postsave_handler, predelete_handler, postdelete_handler, m2m_handler, get_old_handler)
        from django.db.models.signals import (
            post_save, m2m_changed, pre_delete, post_delete, pre_save)

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

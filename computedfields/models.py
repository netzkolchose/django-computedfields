from typing import Iterable, Optional
from django.db import models
from django.contrib.contenttypes.models import ContentType, ContentTypeManager
from django.utils.translation import gettext_lazy as _
from .resolver import active_resolver, _ComputedFieldsModelBase

__all__ = [
    'ComputedFieldsModel',
    'ComputedField',
    'computed',
    'precomputed',
    'compute',
    'update_computedfields',
    'update_dependent',
    'preupdate_dependent',
    'has_computedfields',
    'get_computedfields',
    'is_computedfield',
    'get_contributing_fks',
    'ComputedFieldsAdminModel',
    'ContributingModelsModel'
]

class ComputedFieldsModel(_ComputedFieldsModelBase, models.Model):
    """
    Abstract base class for models with computed fields. Overloads ``save`` to update
    local computed field values before they are written to the database.

    All models containing a computed field must be derived from this class.
    """
    class Meta:
        abstract = True

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: Optional[str] = None,
        update_fields: Optional[Iterable[str]] = None,
        skip_computedfields: bool = False
    ) -> None:
        """
        Overloaded to update computed field values before writing to the database.

        The method understands a special argument `skip_computedfields` to skip
        the calculation of local computed fields. This is used by the ``@precomputed`` decorator
        to allow to skip a second field calculation with ``@precomputed(skip_after=True)``.
        If you use `skip_computedfields` yourself, make sure to synchronize computed fields
        yourself by other means, e.g. by calling ``update_computedfields`` before writing
        the instance or by a later ``update_dependent`` call.
        """
        if not skip_computedfields:
            update_fields = update_computedfields(self, update_fields)
        return super(ComputedFieldsModel, self).save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields
        )


# some convenient access mappings

# decorators
#: Convenient access to the decorator :meth:`@computed<.resolver.Resolver.computed>`.
computed = active_resolver.computed
#: Convenient access to the decorator :meth:`@precomputed<.resolver.Resolver.precomputed>`.
precomputed = active_resolver.precomputed

# ComputedField factory
#: Convenient access to :meth:`computedfield_factory<.resolver.Resolver.computedfield_factory>`.
ComputedField = active_resolver.computedfield_factory

# computed field updates
#: Convenient access to :meth:`compute<.resolver.Resolver.compute>`.
compute = active_resolver.compute
#: Convenient access to :meth:`update_computedfields<.resolver.Resolver.update_computedfields>`.
update_computedfields = active_resolver.update_computedfields
#: Convenient access to :meth:`update_dependent<.resolver.Resolver.update_dependent>`.
update_dependent = active_resolver.update_dependent
#: Convenient access to :meth:`preupdate_dependent<.resolver.Resolver.preupdate_dependent>`.
preupdate_dependent = active_resolver.preupdate_dependent

# helper
#: Convenient access to :meth:`has_computedfields<.resolver.Resolver.has_computedfields>`.
has_computedfields = active_resolver.has_computedfields
#: Convenient access to :meth:`get_computedfields<.resolver.Resolver.get_computedfields>`.
get_computedfields = active_resolver.get_computedfields
#: Convenient access to :meth:`is_computedfield<.resolver.Resolver.is_computedfield>`.
is_computedfield = active_resolver.is_computedfield
#: Convenient access to :meth:`get_contributing_fks<.resolver.Resolver.get_contributing_fks>`.
get_contributing_fks = active_resolver.get_contributing_fks


class ComputedModelManager(ContentTypeManager):
    def get_queryset(self):
        objs = ContentType.objects.get_for_models(
            *active_resolver.computed_models.keys()).values()
        pks = [model.pk for model in objs]
        return ContentType.objects.filter(pk__in=pks)


class ComputedFieldsAdminModel(ContentType):
    """
    Proxy model to list all ``ComputedFieldsModel`` models with their
    field dependencies in admin. This might be useful during development.
    To enable it, set ``COMPUTEDFIELDS_ADMIN = True`` in `settings.py`.
    """
    objects = ComputedModelManager()

    class Meta:
        proxy = True
        managed = False
        verbose_name = _('Computed Fields Model')
        verbose_name_plural = _('Computed Fields Models')
        ordering = ('app_label', 'model')


class ModelsWithContributingFkFieldsManager(ContentTypeManager):
    def get_queryset(self):
        objs = ContentType.objects.get_for_models(
            *active_resolver.get_contributing_fks().keys()).values()
        pks = [model.pk for model in objs]
        return ContentType.objects.filter(pk__in=pks)


class ContributingModelsModel(ContentType):
    """
    Proxy model to list all models in admin, that contain foreign key relations
    contributing to computed fields. This might be useful during development.
    To enable it, set ``COMPUTEDFIELDS_ADMIN = True`` in `settings.py`.

    .. NOTE::
        A foreign key relation is considered contributing, if it is part of
        a computed field dependency in reverse direction.
    """
    objects = ModelsWithContributingFkFieldsManager()

    class Meta:
        proxy = True
        managed = False
        verbose_name = _('Model with contributing ForeignKey Fields')
        verbose_name_plural = _('Models with contributing ForeignKey Fields')
        ordering = ('app_label', 'model')

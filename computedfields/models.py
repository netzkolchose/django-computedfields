from django.db import models
from .resolver import active_resolver
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _

update_dependent = active_resolver.update_dependent
update_dependent_multi = active_resolver.update_dependent_multi
preupdate_dependent = active_resolver.preupdate_dependent
preupdate_dependent_multi = active_resolver.preupdate_dependent_multi
compute = active_resolver.compute
computed = active_resolver.computed
has_computedfields = active_resolver.has_computedfields
get_contributing_fks = active_resolver.get_contributing_fks
update_computedfields = active_resolver.update_computedfields


class ComputedFieldsModel(models.Model):
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        new_update_fields = update_computedfields(self, kwargs.get('update_fields'))
        if new_update_fields:
            kwargs['update_fields'] = new_update_fields
        return super(ComputedFieldsModel, self).save(*args, **kwargs)


class ComputedModelManager(models.Manager):
    def get_queryset(self):
        objs = ContentType.objects.get_for_models(
            *active_resolver._computed_models.keys()).values()
        pks = [model.pk for model in objs]
        return ContentType.objects.filter(pk__in=pks)


class ComputedFieldsAdminModel(ContentType):
    """
    Proxy model to list all ``ComputedFieldsModel`` models with their
    field dependencies in admin. This might be useful during development.
    To enable it, set ``COMPUTEDFIELDS_ADMIN`` in settings.py to ``True``.
    """
    objects = ComputedModelManager()

    class Meta:
        proxy = True
        managed = False
        verbose_name = _('Computed Fields Model')
        verbose_name_plural = _('Computed Fields Models')
        ordering = ('app_label', 'model')


class ModelsWithContributingFkFieldsManager(models.Manager):
    def get_queryset(self):
        objs = ContentType.objects.get_for_models(
            *active_resolver._fk_map.keys()).values()
        pks = [model.pk for model in objs]
        return ContentType.objects.filter(pk__in=pks)


class ContributingModelsModel(ContentType):
    """
    Proxy model to list all models in admin, that contain fk fields contributing to computed fields.
    This might be useful during development.
    To enable it, set ``COMPUTEDFIELDS_ADMIN`` in settings.py to ``True``.
    An fk field is considered contributing, if it is part of a computed field dependency,
    thus a change to it would impact a computed field.
    """
    objects = ModelsWithContributingFkFieldsManager()

    class Meta:
        proxy = True
        managed = False
        verbose_name = _('Model with contributing Fk Fields')
        verbose_name_plural = _('Models with contributing Fk Fields')
        ordering = ('app_label', 'model')

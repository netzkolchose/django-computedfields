from django.db import models
from computedfields.models import ComputedFieldsModel, computed


class Foo(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=['bar_set.baz_set'])
    def bazzes(self):
        return ', '.join(Baz.objects.filter(
            bar__foo=self).values_list('name', flat=True))

    def __str__(self):
        return self.name


class Bar(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    foo = models.ForeignKey(Foo, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=['foo'])
    def foo_bar(self):
        return self.foo.name + self.name

    def __str__(self):
        return self.name


class Baz(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    bar = models.ForeignKey(Bar, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=['bar#foo_bar'])
    def foo_bar_baz(self):
        return self.bar.foo_bar + self.name

    def __str__(self):
        return self.name


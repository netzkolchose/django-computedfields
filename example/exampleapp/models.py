from django.db import models
from computedfields.models import ComputedFieldsModel, computed


class Foo(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[['bar_set.baz_set', ['name']]])
    def bazzes(self):
        return ', '.join(Baz.objects.filter(
            bar__foo=self).values_list('name', flat=True))

    def __str__(self):
        return self.name


class Bar(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    foo = models.ForeignKey(Foo, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[['self', ['name']], ['foo', ['name']]])
    def foo_bar(self):
        return self.foo.name + self.name

    def __str__(self):
        return self.name


class Baz(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    bar = models.ForeignKey(Bar, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[['self', ['name']], ['bar', ['foo_bar']]])
    def foo_bar_baz(self):
        return self.bar.foo_bar + self.name

    def __str__(self):
        return self.name


class SelfRef(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    xy = models.IntegerField(default=0)

    @computed(models.CharField(max_length=32), depends=[['self', ['name']]])
    def c1(self):
        return self.name.upper()

    @computed(models.CharField(max_length=32), depends=[['self', ['c1']]])
    def c2(self):
        return 'c2' + self.c1

    @computed(models.CharField(max_length=32, default=''), depends=[['self', ['c1']]])
    def c3(self):
        return 'c3' + self.c1

    @computed(models.CharField(max_length=32, default=''), depends=[['self', ['c3']]])
    def c4(self):
        return 'c4' + self.c3

    @computed(models.CharField(max_length=32, default=''), depends=[['self', ['c2', 'c4', 'c6']]])
    def c5(self):
        return 'c5' + self.c2 + self.c4 + self.c6

    @computed(models.CharField(max_length=32, default=''), depends=[['self', ['xy']]])
    def c6(self):
        return 'c6' + str(self.xy)

    @computed(models.CharField(max_length=32, default=''), depends=[['self', ['c8']]])
    def c7(self):
        return 'c7' + self.c8

    @computed(models.CharField(max_length=32, default=''), depends=[])
    def c8(self):
        return 'c8'

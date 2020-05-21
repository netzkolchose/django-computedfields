from django.db import models
import sys
from computedfields.models import ComputedFieldsModel, computed


def model_factory(name, keys):
    """
    Create a test model at runtime. `name` is the model name in lower case, `keys`
    contains all other models to be build like this.

        class A(ComputedFieldsModel):
            name = models.CharField(max_length=5)
            f_ab = models.ForeignKey('B', related_name='ba_f', blank=True, null=True)
            m_ab = models.ManyToManyField('B', related_name='ba_m', blank=True)
            o_ab = models.OneToOneField('B', related_name='ba_o', blank=True, null=True)

            @computed(models.CharField(max_length=5), depends=[])
            def comp(self):
                return ''

    The `comp` function and the depends list will be replaced by the different test cases.
    """
    attrs = {}

    # add module and __unicode__ attr
    attrs.update({
        '__module__': 'test_full.models',
        '__unicode__': lambda self: self.name})

    # name field
    attrs.update({'name': models.CharField(max_length=5)})

    # related fields
    for key in keys:
        fwd_name = name + key
        bwd_name = key + name
        attrs['f_'+fwd_name] = models.ForeignKey(
            key, related_name=bwd_name+'_f', blank=True, null=True, on_delete=models.SET_NULL)
        attrs['m_'+fwd_name] = models.ManyToManyField(
            key, related_name=bwd_name+'_m', blank=True)
        attrs['o_'+fwd_name] = models.OneToOneField(
            key, related_name=bwd_name+'_o', blank=True, null=True, on_delete=models.SET_NULL)

    # comp field
    attrs['comp'] = computed(models.CharField(max_length=20), depends=[])(lambda self: '')

    # needs reset in tests
    attrs['needs_reset'] = True

    # create model class
    model_cls = type(name.upper(), (ComputedFieldsModel,), attrs)
    setattr(sys.modules[__name__], name.upper(), model_cls)
    return model_cls


def generate_models(keys):
    """
    Generate multiple models at runtime.
    """
    return dict((key.upper(), model_factory(key, keys)) for key in keys)


# generate models: A, B ... H for testing purpose
MODELS = generate_models('abcdefgh')


# test no related_name with complicated dependencies
class NoRelatedA(ComputedFieldsModel):
    name = models.CharField(max_length=5)

    @computed(models.CharField(max_length=256), depends=[
        ['norelatedb_set', ['name']],
        ['norelatedb_set.norelatedc_set', ['name']],
        ['norelatedb_set.norelatedc_set.norelatedd', ['comp']]
    ])
    def comp(self):
        res = [self.name]
        for b in self.norelatedb_set.all():
            res.append(b.name)
            for c in b.norelatedc_set.all():
                res.append(c.name)
                try:
                    res.append(c.norelatedd.comp)
                except models.ObjectDoesNotExist:
                    pass
        return '#'.join(res)


class NoRelatedB(models.Model):
    name = models.CharField(max_length=5)
    f_ba = models.ForeignKey(NoRelatedA, blank=True, null=True, on_delete=models.CASCADE)


class NoRelatedC(models.Model):
    name = models.CharField(max_length=5)
    m_cb = models.ManyToManyField(NoRelatedB, blank=True)


class NoRelatedD(ComputedFieldsModel):
    name = models.CharField(max_length=5)
    o_dc = models.OneToOneField(NoRelatedC, blank=True, null=True, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[['o_dc.m_cb.f_ba', ['name']]])
    def comp(self):
        inner = []
        try:
            for b in self.o_dc.m_cb.all():
                if b.f_ba:
                    inner.append(b.f_ba.name)
        except models.ObjectDoesNotExist:
            pass
        return self.name + '-a:' + '#'.join(inner)


class MultipleCompSource(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[['self', ['name']]])
    def upper(self):
        return self.name.upper()

    @computed(models.CharField(max_length=32), depends=[['self', ['name']]])
    def lower(self):
        return self.name.lower()


class MultipleCompRef(ComputedFieldsModel):
    a = models.ForeignKey(MultipleCompSource, related_name='a_set', on_delete=models.CASCADE)
    b = models.ForeignKey(MultipleCompSource, related_name='b_set', on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[['a', ['upper']]])
    def upper_a(self):
        return self.a.upper

    @computed(models.CharField(max_length=32), depends=[['a', ['lower']]])
    def lower_a(self):
        return self.a.lower

    @computed(models.CharField(max_length=32), depends=[['b', ['upper']]])
    def upper_b(self):
        return self.b.upper

    @computed(models.CharField(max_length=32), depends=[['b', ['lower']]])
    def lower_b(self):
        return self.b.lower


# test classes for partial updates with update_fields
class PartialUpdateA(models.Model):
    name = models.CharField(max_length=32)


class PartialUpdateB(ComputedFieldsModel):
    f_ba = models.ForeignKey(PartialUpdateA, related_name='a_set', on_delete=models.CASCADE)
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[['f_ba', ['name']], ['self', ['name']]])
    def comp(self):
        return self.f_ba.name + self.name


# moving related objects
class Parent(ComputedFieldsModel):
    @computed(models.IntegerField(default=0), depends=[['children', ['parent']]])
    def children_count(self):
        return self.children.all().count()

    @computed(models.IntegerField(default=0), depends=[['children.subchildren', ['subparent']]])
    def subchildren_count(self):
        count = 0
        for child in self.children.all():
            count += child.subchildren.all().count()
        return count

    @computed(models.IntegerField(default=0), depends=[['children', ['subchildren_count']]])
    def subchildren_count_proxy(self):
        from functools import reduce
        from operator import add
        return reduce(add, (el.subchildren_count for el in self.children.all()), 0)

class Child(ComputedFieldsModel):
    parent = models.ForeignKey(Parent, related_name='children', on_delete=models.CASCADE)

    @computed(models.IntegerField(default=0), depends=[['subchildren', ['subparent']]])
    def subchildren_count(self):
        return self.subchildren.all().count()

class Subchild(models.Model):
    subparent = models.ForeignKey(Child, related_name='subchildren', on_delete=models.CASCADE)

# example from #15
class XParent(ComputedFieldsModel):
    @computed(models.IntegerField(default=0), depends=[['children', ['value']]])
    def children_value(self):
        return self.children.all().aggregate(sum=models.Sum('value'))['sum'] or 0

class XChild(ComputedFieldsModel):
    parent = models.ForeignKey(XParent, related_name='children', on_delete=models.CASCADE)
    value = models.IntegerField()


# update_dependent/update_dependent_multi tests
class DepBaseA(ComputedFieldsModel):
    @computed(models.CharField(max_length=256), depends=[['sub1.sub2.subfinal', ['name']]])
    def final_proxy(self):
        s = ''
        for s1 in self.sub1.all():
            for s2 in s1.sub2.all():
                for sf in s2.subfinal.all():
                    s += sf.name
        return s

class DepBaseB(ComputedFieldsModel):
    @computed(models.CharField(max_length=256), depends=[['sub1.sub2.subfinal', ['name']]])
    def final_proxy(self):
        s = ''
        for s1 in self.sub1.all():
            for s2 in s1.sub2.all():
                for sf in s2.subfinal.all():
                    s += sf.name
        return s

class DepSub1(ComputedFieldsModel):
    a = models.ForeignKey(DepBaseA, related_name='sub1', on_delete=models.CASCADE)
    b = models.ForeignKey(DepBaseB, related_name='sub1', on_delete=models.CASCADE)


class DepSub2(ComputedFieldsModel):
    sub1 = models.ForeignKey(DepSub1, related_name='sub2', on_delete=models.CASCADE)


class DepSubFinal(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    sub2 = models.ForeignKey(DepSub2, related_name='subfinal', on_delete=models.CASCADE)


# Test classes for abstract model support
class Abstract(ComputedFieldsModel):
    class Meta:
        abstract = True

    a = models.IntegerField(default=0)
    b = models.IntegerField(default=0)

    @computed(models.IntegerField(default=0), depends=[['self', ['a', 'b']]])
    def c(self):
        return self.a + self.b


class Concrete(Abstract):
    d = models.IntegerField(default=0)


class ParentOfAbstract(ComputedFieldsModel):
    @computed(models.IntegerField(default=0), depends=[['children', ['parent']]])
    def children_count(self):
        return self.children.all().count()

    @computed(models.IntegerField(default=0), depends=[['children.subchildren', ['subparent']]])
    def subchildren_count(self):
        count = 0
        for child in self.children.all():
            count += child.subchildren.all().count()
        return count

    @computed(models.IntegerField(default=0), depends=[['children', ['subchildren_count']]])
    def subchildren_count_proxy(self):
        from functools import reduce
        from operator import add
        return reduce(add, (el.subchildren_count for el in self.children.all()), 0)


class AbstractChild(ComputedFieldsModel):
    class Meta:
        abstract = True

    parent = models.ForeignKey(ParentOfAbstract, related_name='children', on_delete=models.CASCADE)


class ConcreteChild(AbstractChild):
    @computed(models.IntegerField(default=0), depends=[['subchildren', ['subparent']]])
    def subchildren_count(self):
        return self.subchildren.all().count()


class AbstractSubchild(models.Model):
    class Meta:
        abstract = True

    subparent = models.ForeignKey(ConcreteChild, related_name='subchildren', on_delete=models.CASCADE)


class ConcreteSubchild(AbstractSubchild):
    pass


class AbstractWithForeignKey(ComputedFieldsModel):
    target = models.ForeignKey(Concrete, related_name="abstract_with_foreign_key", on_delete=models.CASCADE)

    @computed(models.IntegerField(default=0), depends=[['target', ['d']]])
    def target_d(self):
        return self.target.d

    @computed(models.IntegerField(default=0), depends=[['target', ['a', 'b']]])
    def target_c(self):
        return self.target.a + self.target.b

    @computed(models.IntegerField(default=0), depends=[['target', ['c']]])
    def target_c_proxy(self):
        return self.target.c


class ConcreteWithForeignKey(AbstractWithForeignKey):
    concrete_target = models.ForeignKey(Concrete, related_name="concrete_with_foreign_key", on_delete=models.CASCADE)

    @computed(models.IntegerField(default=0), depends=[['target', ['d']]])
    def d(self):
        return self.target.d

    @computed(models.IntegerField(default=0), depends=[['target', ['a', 'b']]])
    def c(self):
        return self.target.a + self.target.b

    @computed(models.IntegerField(default=0), depends=[['target', ['c']]])
    def c_proxy(self):
        return self.target.c

    @computed(models.IntegerField(default=0), depends=[['concrete_target', ['d']]])
    def concrete_d(self):
        return self.concrete_target.d

    @computed(models.IntegerField(default=0), depends=[['concrete_target', ['a', 'b']]])
    def concrete_c(self):
        return self.concrete_target.a + self.concrete_target.b

    @computed(models.IntegerField(default=0), depends=[['concrete_target', ['c']]])
    def concrete_c_proxy(self):
        return self.concrete_target.c


# test local field dependencies
class SelfA(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=34), depends=[['self', ['name']]])
    def c1(self):
        return 'c1' + self.name

    @computed(models.CharField(max_length=74), depends=[['self', ['c1', 'c3']]])
    def c4(self):
        return 'c4' + self.c1 + self.c3

    @computed(models.CharField(max_length=36), depends=[['self', ['c1']]])
    def c2(self):
        return 'c2' + self.c1

    @computed(models.CharField(max_length=38), depends=[['self', ['c2']]])
    def c3(self):
        return 'c3' + self.c2

class SelfB(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    a = models.ForeignKey(SelfA, related_name='self_b', on_delete=models.CASCADE)

    @computed(models.CharField(max_length=34), depends=[['self', ['name']]])
    def c1(self):
        return 'C1' + self.name

    @computed(models.CharField(max_length=118), depends=[['self', ['c1']], ['a', ['c4']]])
    def c2(self):
        return 'C2' + self.c1 + self.a.c4


# old depends notation still working
# FIXME: to be removed with furture version
class OldDependsParent(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=['self#name'])
    def upper(self):
        return self.name.upper()

    @computed(models.CharField(max_length=32), depends=['self#upper', 'children'])
    def proxy(self):
        return self.upper + str(self.children.all().count())

class OldDependsChild(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(OldDependsParent, related_name='children', on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=['self#name', 'parent#upper'])
    def parent_and_self(self):
        return self.parent.upper + self.name


# test update_fields expansion, see https://github.com/netzkolchose/django-computedfields/issues/27
class ChainA(ComputedFieldsModel):
    name = models.CharField(max_length=32)

class ChainB(ComputedFieldsModel):
    a = models.ForeignKey(ChainA, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[['a', ['name']]])
    def comp(self):
        return self.a.name

class ChainC(ComputedFieldsModel):
    b = models.ForeignKey(ChainB, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[['b', ['comp']]])
    def comp(self):
        return self.b.comp

from django.db import models
import sys
from computedfields.models import ComputedFieldsModel, computed, precomputed, ComputedField


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
        ('norelatedb_set', ['name']),
        ('norelatedb_set.norelatedc_set', ['name']),
        ('norelatedb_set.norelatedc_set.norelatedd', ['comp'])
    ])
    def comp(self):
        res = [self.name]
        if not self.pk:
            return '#'.join(res)
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

    @computed(models.CharField(max_length=32), depends=[('o_dc.m_cb.f_ba', ['name'])])
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

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def upper(self):
        return self.name.upper()

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def lower(self):
        return self.name.lower()


class MultipleCompRef(ComputedFieldsModel):
    a = models.ForeignKey(MultipleCompSource, related_name='a_set', on_delete=models.CASCADE)
    b = models.ForeignKey(MultipleCompSource, related_name='b_set', on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[('a', ['upper'])])
    def upper_a(self):
        return self.a.upper

    @computed(models.CharField(max_length=32), depends=[('a', ['lower'])])
    def lower_a(self):
        return self.a.lower

    @computed(models.CharField(max_length=32), depends=[('b', ['upper'])])
    def upper_b(self):
        return self.b.upper

    @computed(models.CharField(max_length=32), depends=[('b', ['lower'])])
    def lower_b(self):
        return self.b.lower


# test classes for partial updates with update_fields
class PartialUpdateA(models.Model):
    name = models.CharField(max_length=32)


class PartialUpdateB(ComputedFieldsModel):
    f_ba = models.ForeignKey(PartialUpdateA, related_name='a_set', on_delete=models.CASCADE)
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[('f_ba', ['name']), ('self', ['name'])])
    def comp(self):
        return self.f_ba.name + self.name


# moving related objects
class Parent(ComputedFieldsModel):
    @computed(models.IntegerField(default=0), depends=[('children', ['parent'])])
    def children_count(self):
        if not self.pk:
            return 0
        return self.children.all().count()

    @computed(models.IntegerField(default=0), depends=[('children.subchildren', ['subparent'])])
    def subchildren_count(self):
        count = 0
        if not self.pk:
            return count
        for child in self.children.all():
            count += child.subchildren.all().count()
        return count

    @computed(models.IntegerField(default=0), depends=[('children', ['subchildren_count'])])
    def subchildren_count_proxy(self):
        from functools import reduce
        from operator import add
        if not self.pk:
            return 0
        return reduce(add, (el.subchildren_count for el in self.children.all()), 0)

class Child(ComputedFieldsModel):
    parent = models.ForeignKey(Parent, related_name='children', on_delete=models.CASCADE)

    @computed(models.IntegerField(default=0), depends=[('subchildren', ['subparent'])])
    def subchildren_count(self):
        if not self.pk:
            return 0
        return self.subchildren.all().count()

class Subchild(models.Model):
    subparent = models.ForeignKey(Child, related_name='subchildren', on_delete=models.CASCADE)

# example from #15
class XParent(ComputedFieldsModel):
    @computed(models.IntegerField(default=0), depends=[('children', ['value'])])
    def children_value(self):
        if not self.pk:
            return 0
        return self.children.all().aggregate(sum=models.Sum('value'))['sum'] or 0

class XChild(models.Model):
    parent = models.ForeignKey(XParent, related_name='children', on_delete=models.CASCADE)
    value = models.IntegerField()


# update_dependent/update_dependent_multi tests
class DepBaseA(ComputedFieldsModel):
    @computed(models.CharField(max_length=256), depends=[('sub1.sub2.subfinal', ['name'])])
    def final_proxy(self):
        s = ''
        if not self.pk:
            return s
        for s1 in self.sub1.all().order_by('pk'):
            for s2 in s1.sub2.all().order_by('pk'):
                for sf in s2.subfinal.all().order_by('pk'):
                    s += sf.name
        return s

class DepBaseB(ComputedFieldsModel):
    @computed(models.CharField(max_length=256), depends=[('sub1.sub2.subfinal', ['name'])])
    def final_proxy(self):
        s = ''
        if not self.pk:
            return s
        for s1 in self.sub1.all().order_by('pk'):
            for s2 in s1.sub2.all().order_by('pk'):
                for sf in s2.subfinal.all().order_by('pk'):
                    s += sf.name
        return s

class DepSub1(models.Model):
    a = models.ForeignKey(DepBaseA, related_name='sub1', on_delete=models.CASCADE)
    b = models.ForeignKey(DepBaseB, related_name='sub1', on_delete=models.CASCADE)


class DepSub2(models.Model):
    sub1 = models.ForeignKey(DepSub1, related_name='sub2', on_delete=models.CASCADE)


class DepSubFinal(models.Model):
    name = models.CharField(max_length=32)
    sub2 = models.ForeignKey(DepSub2, related_name='subfinal', on_delete=models.CASCADE)


# Test classes for abstract model support
class Abstract(ComputedFieldsModel):
    class Meta:
        abstract = True

    a = models.IntegerField(default=0)
    b = models.IntegerField(default=0)

    @computed(models.IntegerField(default=0), depends=[('self', ['a', 'b'])])
    def c(self):
        return self.a + self.b

class ConcreteB(Abstract):
    name = models.CharField(max_length=32)

class Concrete(Abstract):
    d = models.IntegerField(default=0)


class ParentOfAbstract(ComputedFieldsModel):
    @computed(models.IntegerField(default=0), depends=[('children', ['parent'])])
    def children_count(self):
        if not self.pk:
            return 0
        return self.children.all().count()

    @computed(models.IntegerField(default=0), depends=[('children.subchildren', ['subparent'])])
    def subchildren_count(self):
        count = 0
        if not self.pk:
            return count
        for child in self.children.all():
            count += child.subchildren.all().count()
        return count

    @computed(models.IntegerField(default=0), depends=[('children', ['subchildren_count'])])
    def subchildren_count_proxy(self):
        from functools import reduce
        from operator import add
        if not self.pk:
            return 0
        return reduce(add, (el.subchildren_count for el in self.children.all()), 0)


class AbstractChild(ComputedFieldsModel):
    class Meta:
        abstract = True

    parent = models.ForeignKey(ParentOfAbstract, related_name='children', on_delete=models.CASCADE)


class ConcreteChild(AbstractChild):
    @computed(models.IntegerField(default=0), depends=[('subchildren', ['subparent'])])
    def subchildren_count(self):
        if not self.pk:
            return 0
        return self.subchildren.all().count()


class AbstractSubchild(models.Model):
    class Meta:
        abstract = True

    subparent = models.ForeignKey(ConcreteChild, related_name='subchildren', on_delete=models.CASCADE)


class ConcreteSubchild(AbstractSubchild):
    pass


class AbstractWithForeignKey(ComputedFieldsModel):
    class Meta:
        abstract = True

    target = models.ForeignKey(Concrete, related_name='%(class)s', on_delete=models.CASCADE)

    @computed(models.IntegerField(default=0), depends=[('target', ['d'])])
    def target_d(self):
        return self.target.d

    @computed(models.IntegerField(default=0), depends=[('target', ['a', 'b'])])
    def target_c(self):
        return self.target.a + self.target.b

    @computed(models.IntegerField(default=0), depends=[('target', ['c'])])
    def target_c_proxy(self):
        return self.target.c


class ConcreteWithForeignKey(AbstractWithForeignKey):
    concrete_target = models.ForeignKey(Concrete, related_name="concrete_with_foreign_key", on_delete=models.CASCADE)

    @computed(models.IntegerField(default=0), depends=[('target', ['d'])])
    def d(self):
        return self.target.d

    @computed(models.IntegerField(default=0), depends=[('target', ['a', 'b'])])
    def c(self):
        return self.target.a + self.target.b

    @computed(models.IntegerField(default=0), depends=[('target', ['c'])])
    def c_proxy(self):
        return self.target.c

    @computed(models.IntegerField(default=0), depends=[('concrete_target', ['d'])])
    def concrete_d(self):
        return self.concrete_target.d

    @computed(models.IntegerField(default=0), depends=[('concrete_target', ['a', 'b'])])
    def concrete_c(self):
        return self.concrete_target.a + self.concrete_target.b

    @computed(models.IntegerField(default=0), depends=[('concrete_target', ['c'])])
    def concrete_c_proxy(self):
        return self.concrete_target.c


class ConcreteWithForeignKey2(AbstractWithForeignKey):
    @computed(models.IntegerField(default=0), depends=[('target', ['d'])])
    def d2(self):
        return self.target.d


# test local field dependencies
class SelfA(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=34), depends=[('self', ['name'])])
    def c1(self):
        return 'c1' + self.name

    @computed(models.CharField(max_length=74), depends=[('self', ['c1', 'c3'])])
    def c4(self):
        return 'c4' + self.c1 + self.c3

    @computed(models.CharField(max_length=36), depends=[('self', ['c1'])])
    def c2(self):
        return 'c2' + self.c1

    @computed(models.CharField(max_length=38), depends=[('self', ['c2'])])
    def c3(self):
        return 'c3' + self.c2

class SelfB(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    a = models.ForeignKey(SelfA, related_name='self_b', on_delete=models.CASCADE)

    @computed(models.CharField(max_length=34), depends=[('self', ['name'])])
    def c1(self):
        return 'C1' + self.name

    @computed(models.CharField(max_length=118), depends=[('self', ['c1']), ('a', ['c4'])])
    def c2(self):
        return 'C2' + self.c1 + self.a.c4


# test update_fields expansion, see https://github.com/netzkolchose/django-computedfields/issues/27
class ChainA(models.Model):
    name = models.CharField(max_length=32)

class ChainB(ComputedFieldsModel):
    a = models.ForeignKey(ChainA, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[('a', ['name'])])
    def comp(self):
        return self.a.name

class ChainC(ComputedFieldsModel):
    b = models.ForeignKey(ChainB, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[('b', ['comp'])])
    def comp(self):
        return self.b.comp

class ExpandA(models.Model):
    name = models.CharField(max_length=32)

class ExpandB(models.Model):
    a = models.ForeignKey(ExpandA, on_delete=models.CASCADE)

class ExpandC(models.Model):
    b = models.ForeignKey(ExpandB, on_delete=models.CASCADE)

class ExpandD(ComputedFieldsModel):
    c = models.ForeignKey(ExpandC, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[('c.b.a', ['name'])])
    def comp(self):
        return self.c.b.a.name


# test select_related
class ParentNotO(models.Model):
    name = models.CharField(max_length=32)
    
class ChildNotO(models.Model):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(ParentNotO, on_delete=models.CASCADE)

class SubChildNotO(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(ChildNotO, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32),
        depends=[
            ('parent', ['name']),
            ('parent.parent', ['name'])
        ]
    )
    def parents(self):
        return self.name + '$' + self.parent.name + '$' + self.parent.parent.name

class ParentO(models.Model):
    name = models.CharField(max_length=32)
    
class ChildO(models.Model):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(ParentO, on_delete=models.CASCADE)

class SubChildO(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(ChildO, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32),
        depends=[
            ('parent', ['name']),
            ('parent.parent', ['name'])
        ],
        select_related=('parent__parent',)
    )
    def parents(self):
        return self.name + '$' + self.parent.name + '$' + self.parent.parent.name


# test prefetch_related
class ParentReverseNotO(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=256),
        depends=[
            ('children', ['name']),
            ('children.subchildren', ['name']),
        ]
    )
    def children_comp(self):
        s = []
        if not self.pk:
            return '$'.join(s)
        for child in self.children.all():
            substr = child.name
            ss = []
            for sub in child.subchildren.all():
                ss.append(sub.name)
            if ss:
                substr += '#' + ','.join(ss)
            s.append(substr)
        return '$'.join(s)
    
class ChildReverseNotO(models.Model):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(ParentReverseNotO, related_name='children', on_delete=models.CASCADE)

class SubChildReverseNotO(models.Model):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(ChildReverseNotO, related_name='subchildren', on_delete=models.CASCADE)

class ParentReverseO(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=256),
        depends=[
            ('children', ['name']),
            ('children.subchildren', ['name']),
        ],
        prefetch_related=('children__subchildren',)
    )
    def children_comp(self):
        s = []
        if not self.pk:
            return '$'.join(s)
        for child in self.children.all():
            substr = child.name
            ss = []
            for sub in child.subchildren.all():
                ss.append(sub.name)
            if ss:
                substr += '#' + ','.join(ss)
            s.append(substr)
        return '$'.join(s)
    
class ChildReverseO(models.Model):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(ParentReverseO, related_name='children', on_delete=models.CASCADE)

class SubChildReverseO(models.Model):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(ChildReverseO, related_name='subchildren', on_delete=models.CASCADE)


# compute tests
class ComputeLocal(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    xy = models.IntegerField(default=0)

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def c1(self):
        return self.name.upper()

    @computed(models.CharField(max_length=32), depends=[('self', ['c1'])])
    def c2(self):
        return 'c2' + self.c1

    @computed(models.CharField(max_length=32, default=''), depends=[('self', ['c1'])])
    def c3(self):
        return 'c3' + self.c1

    @computed(models.CharField(max_length=32, default=''), depends=[('self', ['c3'])])
    def c4(self):
        return 'c4' + self.c3

    @computed(models.CharField(max_length=32, default=''), depends=[('self', ['c2', 'c4', 'c6'])])
    def c5(self):
        return 'c5' + self.c2 + self.c4 + self.c6

    @computed(models.CharField(max_length=32, default=''), depends=[('self', ['xy'])])
    def c6(self):
        return 'c6' + str(self.xy)

    @computed(models.CharField(max_length=32, default=''), depends=[('self', ['c8'])])
    def c7(self):
        return 'c7' + self.c8

    @computed(models.CharField(max_length=32, default=''))
    def c8(self):
        return 'c8'

# test for local cf updates from update_dependent/multi
class LocalBulkUpdate(ComputedFieldsModel):
    fk = models.ForeignKey(ComputeLocal, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[('fk', ['c5'])])
    def same_as_fk_c5(self):
        return self.fk.c5


# test #33 / #34
class Registration(ComputedFieldsModel):
    @computed(models.FloatField(default=0), depends=[('payment_set', ['amount'])])
    def total_amount(self):
        paid = 0
        if not self.pk:
            return paid
        for cur_payment in self.payment_set.all():
            paid += cur_payment.amount
        return paid

class Payment(models.Model):
    amount = models.FloatField()
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE)


from django.db.models import Prefetch
# test M2M and through model
class Person(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=256),
        depends=[
            ('groups', ['name']),
            ('membership', ['person'])  # needed for through model changes
        ],
        prefetch_related=['groups']
    )
    def my_groups(self):
        if not self.pk:
            return ''
        result = []
        for group in self.groups.all().order_by('pk'):
            result.append(group.name)
        return ','.join(result)

class Group(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    members = models.ManyToManyField(Person, related_name='groups', through='Membership')

    @computed(models.CharField(max_length=256),
        depends=[
            ('members', ['name']),
            ('membership', ['group'])  # needed for through model changes
        ],
        prefetch_related=['members']
    )
    def my_members(self):
        if not self.pk:
            return ''
        result = []
        for member in self.members.all().order_by('pk'):
            result.append(member.name)
        return ','.join(result)

class Membership(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='membership')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='membership')


# test precomputed decorator with custom save methods
class NotPrecomputed(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def upper(self):
        return self.name.upper()

    def save(self, *args, **kwargs):
        self._temp = self.upper # store upper value to eval in test
        self.name = 'changed'   # ugly part - some concrete fields gets changed here
        super(NotPrecomputed, self).save(*args, **kwargs)

class Precomputed(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def upper(self):
        return self.name.upper()

    @precomputed
    def save(self, *args, **kwargs):
        self._temp = self.upper # store upper value to eval in test
        self.name = 'changed'   # ugly part - some concrete fields gets changed here
        super(Precomputed, self).save(*args, **kwargs)

class PrecomputedEmptyArgs(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def upper(self):
        return self.name.upper()

    @precomputed()
    def save(self, *args, **kwargs):
        self._temp = self.upper # store upper value to eval in test
        self.name = 'changed'   # ugly part - some concrete fields gets changed here
        super(PrecomputedEmptyArgs, self).save(*args, **kwargs)

class PrecomputedNotSkip(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def upper(self):
        return self.name.upper()

    @precomputed(skip_after=False)
    def save(self, *args, **kwargs):
        self._temp = self.upper # store upper value to eval in test
        self.name = 'changed'   # ugly part - some concrete fields gets changed here
        super(PrecomputedNotSkip, self).save(*args, **kwargs)

class PrecomputedSkip(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def upper(self):
        return self.name.upper()

    @precomputed(skip_after=True)
    def save(self, *args, **kwargs):
        self._temp = self.upper # store upper value to eval in test
        self.name = 'changed'   # ugly part - some concrete fields gets changed here
        super(PrecomputedSkip, self).save(*args, **kwargs)


# fixture and updatedata testing
class FixtureParent(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.IntegerField(default=0), depends=[('children', ['parent'])])
    def children_count(self):
        if not self.pk:
            return 0
        return self.children.count()

class FixtureChild(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(FixtureParent, related_name='children', on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[
        ('self', ['name']),
        ('parent', ['name', 'children_count'])
    ])
    def path(self):
        return '/{}#{}/{}'.format(self.parent.name, self.parent.children_count, self.name)


# better m2m support: #43
class MGroup(models.Model):
    pass

class MItem(models.Model):
    pass

class MUser(models.Model):
    groups = models.ManyToManyField(MGroup, related_name="users")
    items = models.ManyToManyField(MItem, related_name="users")

class MAgent(ComputedFieldsModel):
    user = models.OneToOneField(MUser, related_name="agent", on_delete=models.CASCADE)

    @computed(models.IntegerField(default=0), depends=[("user.items", ["id"])])
    def counter(self):
        # This is used to detect when Agent gets updated
        return self.counter + 1


# recursive tree tests - fix #46
class Tree(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey('Tree', null=True, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[
        ('self', ['name']),
        # ('parent', ['path']) -- gets added in specific test case test_simpletree.py
    ])
    def path(self):
        return '{}/{}'.format(self.parent.path if self.parent else '', self.name)


# test o2o relations
class OBackward(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[('source', ['name'])])
    def forward_name(self):
        # special handling of o2o relations
        # other than non existant fk relations o2o raise an exception
        try:
            return self.source.name
        except type(self).source.RelatedObjectDoesNotExist:
            return ''

class OSource(models.Model):
    name = models.CharField(max_length=32)
    o = models.OneToOneField(OBackward, related_name='source', on_delete=models.CASCADE)

class ORelated(ComputedFieldsModel):
    name = models.CharField(max_length=32)

class OForward(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    o = models.OneToOneField(ORelated, related_name='forward', on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[('o', ['name'])])
    def backward_name(self):
        # special handling of o2o relations
        # other than non existant fk relations o2o raise an exception
        try:
            return self.o.name
        except type(self).o.RelatedObjectDoesNotExist:
            return ''


# multi table tests
class MtRelated(models.Model):
    name = models.CharField(max_length=32)

class MtBase(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    rel_on_base = models.ForeignKey(MtRelated, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def upper(self):
        return self.name.upper()

    @computed(models.CharField(max_length=32), depends=[
        # special case: deps resolver will filter on inherited model instances
        # for matching access tokens:
        # - MtDerived instance will never depend on 'mtderived2'
        # - MtDerived2 instance will never depend on 'mtderived'
        # - relation path will be shortened to the actual model level (up to 'self')
        ('mtderived', ['upper_combined']),
        ('mtderived2', ['z']),
        ('mtderived2.mtsubderived', ['sub'])
    ])
    def pulled(self):
        if hasattr(self, 'mtderived'):
            return '###' + self.mtderived.upper_combined
        if hasattr(self, 'mtderived2'):
            if hasattr(self.mtderived2, 'mtsubderived'):
                return 'SUB pulled:' + self.mtderived2.mtsubderived.sub
            else:
                return 'D2:' + self.mtderived2.z
        return ''

class MtDerived(MtBase):
    dname = models.CharField(max_length=32)
    rel_on_derived = models.ForeignKey(MtRelated, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32), depends=[
        ('self', ['dname', 'upper']),
        ('rel_on_base', ['name']),
        ('rel_on_derived', ['name'])
    ])
    def upper_combined(self):
        return '{}/{}#{}:{}'.format(
            self.upper, self.dname.upper(), self.rel_on_base.name, self.rel_on_derived.name)

class MtDerived2(MtBase):
    z = models.CharField(max_length=32)

class MtSubDerived(MtDerived2):
    sub = models.CharField(max_length=32)


# Test classes for multi table inheritance support
class ParentModel(ComputedFieldsModel):
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)

    @computed(models.IntegerField(default=0), depends=[("self", ["x", "y"])])
    def z(self):
        return self.x + self.y

    @computed(models.CharField(max_length=255, null=True, blank=True), depends=[
        ("childmodel", ["username"]),
        ("childmodel2", ["pseudo"])
    ])
    def name(self):
        if hasattr(self, "childmodel"):
            return self.childmodel.username
        elif hasattr(self, "childmodel2"):
            return self.childmodel2.pseudo


class ChildModel(ParentModel):
    username = models.CharField(max_length=255, default="")

    a = models.IntegerField(default=0)
    b = models.IntegerField(default=0)

    @computed(models.IntegerField(default=0), depends=[("self", ["a", "b"])])
    def c(self):
        return self.a + self.b


class ChildModel2(ParentModel):
    pseudo = models.CharField(max_length=255, default="")

    @computed(models.CharField(max_length=255, null=True, blank=True), depends=[("parentmodel_ptr", ["name", "z", "x"])])
    def other_name(self):
        return f"{self.x}{self.name}{self.z}"


class DependsOnParent(ComputedFieldsModel):
    parent = models.ForeignKey(ParentModel, on_delete=models.CASCADE)

    @computed(models.IntegerField(default=0), depends=[
        ("parent", ["x"]),
        ("parent.childmodel", ["x"]),   # descending field recovery
    ])
    def x2(self):
        return self.parent.x * 2


class DependsOnParentComputed(ComputedFieldsModel):
    parent = models.ForeignKey(ParentModel, on_delete=models.CASCADE)

    @computed(models.IntegerField(default=0), depends=[
        ("parent", ["z"]),
        ("parent.childmodel", ["z"])    # descending field recovery
    ])
    def z2(self):
        return self.parent.z * 2


# ptr based multi table access
class MtPtrBase(models.Model):
  basename = models.CharField(max_length=32)

class MtPtrDerived(MtPtrBase, ComputedFieldsModel):
  @computed(models.CharField(max_length=32), depends=[
    ('self', ['basename']),             # catches updates from Derived{basename}
    ('mtptrbase_ptr', ['basename'])     # catches updates from Base{basename} - ascending field recovery
  ])
  def comp(self):
      return self.basename


# test multi table example in docs
class User(ComputedFieldsModel):
    forname = models.CharField(max_length=32)
    surname = models.CharField(max_length=32)

    @computed(models.CharField(max_length=64), depends=[('self', ['forname', 'surname'])])
    def fullname(self):
        return '{}, {}'.format(self.surname, self.forname)

class EmailUser(User):
    email = models.CharField(max_length=32)

    @computed(models.CharField(max_length=128), depends=[
        ('self', ['email', 'fullname']),
        ('user_ptr', ['fullname'])          # trigger updates from User type as well
    ])
    def email_contact(self):
        return '{} <{}>'.format(self.fullname, self.email)

class Work(ComputedFieldsModel):
    subject = models.CharField(max_length=32)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=64), depends=[
        ('self', ['subject']),
        ('user', ['fullname']),
        ('user.emailuser', ['fullname'])    # trigger updates from EmailUser type as well
    ])
    def descriptive_assigment(self):
        return '"{}" is assigned to "{}"'.format(self.subject, self.user.fullname)

# issue #93
class MultiBase(ComputedFieldsModel):
    @computed(models.CharField(max_length=32), depends=[
        ('multia', ['f_on_a']),         # pull custom field from A descendant
        ('multib', ['f_on_b']),         # pull custom field from B descendant
        ('multib.multic', ['f_on_c'])   # pull custom field from C descendant
    ])
    def comp(self):
        # since we dont know the actual sub model,
        # we have to guard the attribute access
        # important: isinstance check will not work here!
        if hasattr(self, 'multia'):
            return self.multia.f_on_a
        if hasattr(self, 'multib'):
            if hasattr(self.multib, 'multic'):
                return self.multib.multic.f_on_c
            return self.multib.f_on_b
        return ''

class MultiA(MultiBase):
    f_on_a = models.CharField(max_length=32, default='a')
class MultiB(MultiBase):
    f_on_b = models.CharField(max_length=32, default='b')
class MultiC(MultiB):
    f_on_c = models.CharField(max_length=32, default='sub-c')



# proxy model tests - see test_proxymodels.py
class ProxyParent(Parent):
    class Meta:
        proxy = True
class ProxyChild(Child):
    class Meta:
        proxy = True
class ProxySubchild(Subchild):
    class Meta:
        proxy = True
class ProxyXParent(XParent):
    class Meta:
        proxy = True
class ProxyXChild(XChild):
    class Meta:
        proxy = True
# proy m2m
class ProxyMGroup(MGroup):
    class Meta:
        proxy = True
class ProxyMItem(MItem):
    class Meta:
        proxy = True
class ProxyMUser(MUser):
    class Meta:
        proxy = True
class ProxyMAgent(MAgent):
    class Meta:
        proxy = True
# local mro
class AllLocal(ComputedFieldsModel):
    f1 = models.CharField(max_length=32)
    inject = models.CharField(max_length=32, default='F4')
    @computed(models.CharField(max_length=32), depends=[('self', ['f1'])])
    def f2(self):
        return self.f1.upper()
    @computed(models.CharField(max_length=32), depends=[('self', ['f2'])])
    def f3(self):
        return self.f2 + 'F3'
    @computed(models.CharField(max_length=32), depends=[('self', ['f2', 'inject'])])
    def f4(self):
        return self.f2 + self.inject
    @computed(models.CharField(max_length=32), depends=[('self', ['f4'])])
    def f5(self):
        return self.f4 + 'F5'
class ProxyAllLocal(AllLocal):
    class Meta:
        proxy = True


# test different querysizes
class Querysize(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])], querysize=10)
    def q10(self):
        return self.name

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])], querysize=100)
    def q100(self):
        return self.name

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])], querysize=1000)
    def q1000(self):
        return self.name

    @computed(models.CharField(max_length=32), depends=[('self', ['name', 'q10'])], querysize=100)
    def c_10_100(self):
        return self.name

    @computed(models.CharField(max_length=32), depends=[('self', ['name', 'q10'])], querysize=1)
    def c_10_1(self):
        return self.name

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def default(self):
        return self.name


# ComputedField factory: direct usage test
def calc_d(inst):
    return inst.a * inst.b

class FactorySimple(ComputedFieldsModel):
    a = models.IntegerField()
    b = models.IntegerField()
    c = ComputedField(models.IntegerField(), compute=lambda inst: inst.a + inst.b)
    d = ComputedField(models.IntegerField(), compute=calc_d)


# better M2M handling #131
class HaTag(models.Model):
    name = models.CharField(max_length=100, unique=True)

class Ha(ComputedFieldsModel):
    tags = models.ManyToManyField(HaTag, blank=True, related_name="ha_s")

    @computed(
        models.CharField(null=False, blank=True, max_length=100),
        depends=[("tags", ["name"])],
    )
    def all_tags(self):
        v = [] if not self.pk else list(self.tags.all().values_list('name', flat=True).order_by('pk'))
        return ','.join(v)

class HaTagProxy(HaTag):
    class Meta:
        proxy = True

class HaProxy(Ha):
    class Meta:
        proxy = True


# related_name vs. related_query_name issue #165
class RNFoo(ComputedFieldsModel):
    @computed(models.CharField(max_length=256), depends=[('bars', ['b'])])
    def comp(self):
        s = ''
        if self.pk:
            for bar in self.bars.all().order_by('pk'):
                s += bar.b
        return s

class RNBar(models.Model):
    b = models.CharField(max_length=10)
    foo = models.ForeignKey(RNFoo, related_name='bars', related_query_name='bar', on_delete=models.CASCADE)

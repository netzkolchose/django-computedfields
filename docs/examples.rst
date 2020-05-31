Examples
========


Dependency Examples
-------------------

The following examples may give you a first idea on how to use the `depends` keyword of the
computed decorator for different scenarios.


No Dependencies
^^^^^^^^^^^^^^^

The most basic example is a computed field, that has no field dependencies at all.
It can be constructed by setting `depends` to an empty container, e.g.:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):

        @computed(Field(...), depends=[])
        def comp(self):
            return some_value_pulled_from_elsewhere

Such a field will only be recalculated by calling ``save()`` or ``save(update_fields=[comp, ...])``
on a model instance. It will not be touched by the auto resolver, unless you force the recalculating
by directly calling ``update_dependent(MyComputedModel.objects.all(). update_fields=None)``.

.. NOTE::

    The empty container is currently needed due to the transition from the old `depends` syntax
    to the new one. Until support for the old syntax gets removed, there is a shim in place, that
    automatically expands ``depends=None`` to ``depends=[['self', list_of_local_concrete_fields]]``.


Local Fields
^^^^^^^^^^^^

A more useful computed field example would do some calculation based on some other model local fields:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):
        fieldA = Field(...)
        fieldB = Field(...)

        @computed(Field(...), depends=[['self', ['fieldA', 'fieldB']]])
        def comp(self):
            return some_calc(self.fieldA, self.fieldB)

This can be achieve in a safe manner by placing a `self` rule in `depends`, listing local source fields
on the right side as shown above.

.. admonition:: Background on `self` rule

    At a first glance it seems weird, that you should declare dependencies on model local fields.
    Well in previous versions it was not needed at all, but turned out as a major shortcoming of
    the old depends syntax leading to unresolvable ambiguity. The new syntax and the need to put
    local fields in a `self` rule enables :mod:`django-computedfields` to properly derive
    the execution order of local computed fields (MRO) and to correctly expand on `update_fields`
    given to a partial save call.

    `Warning:` Technically the `self` rule is not needed, if there are no other local computed fields
    depending on `comp` and you always do a full instance save. But this will break as soon as
    you or some third party package uses partial update with ``save(update_fields=[...])``.
    Thus it is a good idea, to provide a `self` rule right from the beginning for local source
    fields as well.


Local Computed Fields
^^^^^^^^^^^^^^^^^^^^^

To depend on another local computed field, simply list it in the `self` rule as another local field:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):
        fieldA = Field(...)
        fieldB = Field(...)
        fieldC = Field(...)

        @computed(Field(...), depends=[['self', ['fieldA', 'fieldB']]])
        def comp(self):
            return some_calc(self.fieldA, self.fieldB)
        
        @computed(Field(...), depends=[['self', ['fieldC', 'comp']]])
        def final(self):
            return some__other_calc(self.fieldC, self.comp)

The auto resolver will take care, that the computed fields are calculated in the correct order (`MRO`).
In the example above it will make sure, that `final` gets recalculated after `comp`. This also works
with a partial save with ``save(update_fields=['fieldA'])``. Here the resolver will expand `update_fields`
to ``['fieldA', 'comp', 'final']``.

.. WARNING::

    For correct `MRO` resolving computed fields should never be omitted in the `self` dependency rule,
    otherwise the value of dependent computed fields is undetermined.

The ability to depend on other computed fields introduces the problem of possible update cycles:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):
        fieldA = Field(...)
        fieldB = Field(...)
        fieldC = Field(...)

        @computed(Field(...), depends=[['self', ['fieldA', 'fieldB', 'final']]])
        def comp(self):
            return some_calc(self.fieldA, self.fieldB, self.final)
        
        @computed(Field(...), depends=[['self', ['fieldC', 'comp']]])
        def final(self):
            return some__other_calc(self.fieldC, self.comp)

There is no way to create or update such an instance, as `comp` relies on `final`,
which itself relies on `comp`. Here the the dependency resolver will throw a cycling exception
during startup.

.. NOTE::

    Dependencies to other local computed fields always must be cycle-free.


Related Model Fields
^^^^^^^^^^^^^^^^^^^^

Dependencies to fields on related models can be expressed with the relation name on the left side:

.. code-block:: python

    class Foo(models.Model):
        a = Field(...)
        x = Field(...)
    
    class Bar(models.Model):
        b = Field(...)
        baz = models.ForeignKey(Baz, related_name='bars', ...)

    class Baz(ComputedFieldsModel):
        c = Field(...)
        foo = models.ForeignKey(Foo, related_name='bazs', ...)

        @computed(Field(...), depends=[
            ['self', ['c']],
            ['foo', ['a']],   # fk forward relation to foo.a (accidentally forgetting foo.x)
            ['bars', ['b']]   # fk reverse relation to bar.b in self.bars
        ])
        def comp(self):
            for bar in self.bars.all():
                # do something with bar.b
            # do something with self.foo.a
            # wrong: self.foo.x somehow alters the result here
            return ...

Note that the method result should not rely on any other field from the relations than those listed
in `depends`. If you accidentally forget to list some field here (as shown for `foo.x` above),
the resolver will not update dependent instances for certain field updates (above: changes to `foo.x`
may not trigger an update on `Foo.bazs.comp`).
:mod:`django-computedfields` has no measures to spot a forgotten source field here, it fully relies on
your `depends` declarations. If in doubt, if you correctly caught all relevant source fields,
you probably should test the computed field values against all of your critical business logic actions.

.. WARNING::

    Accidentally forgetting a source field in `depends` may lead to hard to track down desync issues.
    Make sure, that you listed in `depends` all source fields the method pulls data from.

The same rule applies for deeper nested relations, simply list the relation paths on the left side
with their corresponding source fields on the right side:

.. code-block:: python

    @computed(Field(...), depends=[
        ['related_set', ['a', 'b']],
        ['related_set.fk', ['xy']]
    ])
    def comp(self):
        result = 0
        for related in self.related_set.all():
            result -= related.a
            result += related.b
            result += related.fk.xy
        return result

For more advanced things like doing SQL aggregations or field annotations yourself you should refer
to the true concrete source fields behind the annotation:

.. code-block:: python

    @computed(Field(...), depends=[
        ['related_set', ['value']]        # aggregation itself relies on field 'value'
    ])
    def with_aggregation(self):
        return self.related_set.aggregate(total=Sum('value'))['total'] or some_default

Here the aggregation is done over the field `value`, thus it should be listed in `depends`
to properly get updated on changes of `value` on the foreign model. `totals` on the interim queryset
is only an annotated field with no persistent database representation, thus cannot be used
as field in the dependency declaration. Same goes for even more complicated queryset manipulations:

.. code-block:: python

    @computed(Field(...), depends=[
        ['related_set', ['a', 'b']],
        ['related_set.fk', ['c']]
    ])
    def with_complicated_aggregation(self):
        return (self.related_set
                .select_related('fk')
                .annotate(intermediate=F('a')+F('b')+F('fk__c'))
                .aggregate(total=Sum('intermediate'))['total']
            or some_default)

Here both fields `total` and `intermediate` are annotated and cannot be used in `depends`.
Instead resolve all annotated fields backwards and collect the concrete source fields,
which reveals `a` and `b` on `related_set` and `c` on `related_set.fk` as the real source fields
in the example above.

.. NOTE::

    The resolver expands dependencies on nested foreign key relations automatically:

    .. code-block:: python

        # shorthand notation of nested forward fk relations
        depends = ['a.b.c', ['fieldX']]
        # expands internally to
        depends = [
          ['a.b.c', ['fieldX']],
          ['a.b', ['c']],
          ['a', ['b']],
          ['self', ['a']]
        ]

        # shorthand notation of nested reverse fk relations
        depends = ['a_set.b_set.c_set', ['fieldX']]
        # expands internally to
        depends = [
          ['a_set.b_set.c_set', ['fieldX', 'fk_field_on_C_pointing_to_B']],
          ['a_set.b_set', ['fk_field_on_B_pointing_to_A']],
          ['a_set', ['fk_field_on_A_pointing_to_self']]
        ]

    This is needed to correctly spot and update computed fields on relation changes itself
    (e.g. moving children to a different parent).

    Note that because of this dependency expansion it is not possible to omit foreign key
    relations on purpose, if they are part of a dependency relation.


Related Computed Fields
^^^^^^^^^^^^^^^^^^^^^^^

Depending on foreign computed fields works likewise as for other foreign source fields,
simply list them on the right side of the relation rule.

Again the auto resolver will throw a cycling exception by default, if you created a cycling
update. But other than for local computed field dependencies this can be supressed by setting
``COMPUTEDFIELDS_ALLOW_RECURSION`` to ``True`` in `settings.py`, which allows to use
computed fields on self referencing models, e.g. tree like structures.
Note that this currently disables intermodel dependency optimizations project-wide and might result
in high "update pressure". It also might lead throw a `RuntimeError` later on, if you created
a real recursion on record level by accident.

.. TIP::

    Depending on other computed fields is an easy way to lower the "update pressure" later on
    for complicated dependencies by isolating relatively static dependencies from fast turning entities.


Many-To-Many Fields
^^^^^^^^^^^^^^^^^^^

Django's `ManyToManyField` can be used in the dependency declaration on the left side as a relation:

.. code-block:: python

    class Person(ComputedFieldsModel):
        name = models.CharField(max_length=32)

        @computed(models.CharField(max_length=256), depends=[['groups', ['name']]])
        def groupnames(self):
            if not self.pk:
                return ''
            return ','.join(self.groups.all().values_list('name', flat=True))

    class Group(models.Model):
        name = models.CharField(max_length=32)
        members = models.ManyToManyField(Person, related_name='groups')

M2M relations are tested to work in both directions with their custom manager methods like
`add`, `set`, `remove` and `clear`. Also actions done to instances on boths ends should correctly update
computed fields through the m2m field. Still there are some specifics that need to be mentioned here.

In the method above there is a clause skipping the actual logic if the instance has
no `pk` value yet. That clause is needed since Django will not allow access to an m2m relation manager before
the instance was saved to the database. After the initial save the m2m relation can be accessed,
now correctly pulling field values across the m2m relation.

M2M fields allow to declare a custom `through` model for the join table. To use computed fields on that model
or to pull fields from that model to either side of the m2m relation, you cannot use the m2m field anymore.
Instead use the foreign key relations declared on the `through` model in `depends`.

Another important issue around m2m fields is the risk to cause a rather high update pressure later on,
if carelessly used. Here it helps to remember, that the `n:m` relation in fact means, that every single instance
in `n` potentially updates `m` instances and vice versa. If you have multiple computed fields with dependency rules
spanning through an m2m field in either direction, the update penalty will explode creating a new bottleneck
in your project. Although there are some ways to further optimize computed fields updates, they are still quite
limited for m2m fields. Also see below under optimization examples. 

.. WARNING::

    M2M fields may create a high update pressure on computed fields and should be avoided in `depends`
    as much as possible.


Forced Update of Computed Fields
--------------------------------

The simplest way to force a model to resync all its computed fields is to resave all model instances:

.. code-block:: python

    for inst in desynced_model.objects.all():
        inst.save()

While this is easy to comprehend, it has the major drawback of resyncing all dependencies as well
for every single save step touching those models over and over, thus will show bad runtime for
complicated dependencies on big tables. A slightly better way is to call `update_dependent` instead:

.. code-block:: python

    from computedfields.models import update_dependent
    update_dependent(desynced_model.objects.all())

which will touch dependent models only once with an altered queryset containing all affected rows.

If you have more knowledge about the action that caused a partial desync, you can customize
the queryset accordingly:

.. code-block:: python

    # given: some bulk action happened before like
    # desynced_model.objects.filter(fieldA='xy').update(fieldB='z')

    # either do
    for inst in desynced_model.objects.filter(fieldA='xy'):
        inst.save(update_fields=['fieldB'])
    # or
    update_dependent(desynced_model.objects.filter(fieldA='xy'), update_fields=['fieldB'])

Here both `save` and `update_dependent` will take care, that all dependent computed fields get updated.
Again using `update_dependent` has the advantage of further reducing the update pressure. Providing
`update_fields` will narrow the update path to computed fields that actually rely on the listed
source fields.

A full resync of all computed fields project-wide can be triggered by calling the management command
`updatedata`. This comes handy if you cannot track down the cause of a desync or do not know which
models/fields are actually affected.

.. NOTE::

    If you do bulk actions yourself, you should always call `update_dependent` afterwards with
    the changeset. This is also true for normal models, that do not hold any computed fields themselves.
    Note that the resolver operates on all project-wide models, for models with no dependent
    computed fields it has a very small footprint in `O(1)`. Also note the documentation for
    `preupdate_dependent` and `update_dependent_multi`.


Optimization Examples
---------------------

.. TODO::

    To be written:

    - `select_related` example
    - `prefetch_related` example
    - notes on complicated dependencies incl M2M
    - Possible savings on using `update_fields`
    - some more guidance for bulk actions and `update_dependent`
    - TBD

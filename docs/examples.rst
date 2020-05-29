Examples
========


Dependency Examples
-------------------

The following examples may give you a first idea on how to use the `depends` keyword of the computed decorator
for basic dependency types.


No dependencies
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


Dependency to local fields
^^^^^^^^^^^^^^^^^^^^^^^^^^

A more useful computed field example would do some calculation based on some other model local fields:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):
        fieldA = Field(...)
        fieldB = Field(...)

        @computed(Field(...), depends=[['self', ['fieldA', 'fieldB']]])
        def comp(self):
            return some_calc(self.fieldA, self.fieldB)

This can be achieve in a safe manner by placing a `self` rule in `depends` as shown above.

.. admonition:: Background on `self` rule

    At a first glance it seems weird, that you should declare dependencies on model local fields.
    Well in previous versions it was not needed at all, but turned out as a major shortcoming of
    the old depends syntax leading to unresolvable ambiguity. The new syntax and the need to put
    local fields in a `self` rule enables :mod:`django-computedfields` to properly derive
    the execution order of local computed fields (MRO) and to correctly expand on `update_fields`
    given to a partial save call.

.. WARNING::

    Technically the `self` rule is not needed, if there are no other local computed fields depending on `comp`
    and you always do a full instance save. Although this might be the case for 80% of the trivial use cases,
    it will certainly break under more advanced scenarios, like third party apps doing partial updates with
    ``save(update_fields=[...])`` or using bulk actions. Thus it is a good idea, to apply a `self` rule right
    from the beginning listing all local concrete field sources.



Dependency to computed fields
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To depend on another local computed field, simply list it in the `self` rule:

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
In the example above it will make sure, that `final` gets recalculated after `comp`. This also works with a partial
save with ``save(update_fields=['fieldA'])``, given that `fieldA` was changed. For that the resolver expands
`update_fields` internally to ``['fieldA', 'comp', 'final']``.

.. NOTE::

    For correct `MRO` resolving computed fields should never be omitted in the `self` dependency rule, otherwise
    the result of dependent computed fields is undetermined.

The ability to depend on other computed fields introduces the problem of possible update cycles:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):
        fieldA = Field(...)
        fieldB = Field(...)
        fieldC = Field(...)

        @computed(Field(...), depends=[['self', ['fieldA', 'fieldB', 'final']]])
        def comp(self):
            return some_calc(self.fieldA, self.fieldB)
        
        @computed(Field(...), depends=[['self', ['fieldC', 'comp']]])
        def final(self):
            return some__other_calc(self.fieldC, self.comp)

There is no way to create or update such an instance, as `comp` relies on `final`, which itself relies on `comp`.
Here the the dependency resolver will throw a cycling exception during startup. Note that `self` dependencies
always must be cycle-free.


Dependency to related model fields
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
        foo = models.ForeignKey(Foo, related_name='bars', ...)

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

Note that the computed field method result should not rely on any other field from the relations
than those listed in `depends`. If you accidentally forget to list some field here like `foo.x` in the example,
the resolver will not update dependent instances of `Baz` on a partial update like ``Foo.save(update_fields=['x'])``.
Note that :mod:`django-computedfields` has no measures to spot a forgotten source field here, it relies fully on
your valid `depends` declarations. If in doubt, whether you caught all relevant source fields, you probably should
test the validity of computed field contents against all of your critical business logic actions.

The same rule applies for deeper nested relations, simply list them on the left side, but dont forget to catch
all concrete fields on the right side your method pulls data from:

.. code-block:: python

    @computed(Field(...), depends=[
      ['related_set', ['a', 'b']],
      ['related_set.fk', ['xy']],
    ])
    def comp(self):
        result = 0
        for related in self.related_set.all():
            result -= related.a
            result += related.b
            result += related.fk.xy
        return result

For more advanced things like doing SQL aggregations or field annotations yourself also make sure to correctly refer
to the orginal concrete fields as source fields:

.. code-block:: python

    @computed(Field(...), depends=[
      ['related_set', ['value']]        # aggregation itself relies on field 'value'
    ])
    def with_aggregation(self):
        return self.related_set.aggregate(total=Sum('value'))['total'] or some_default

Here the aggregation was done on the field `value`, thus it should be listed in `depends` to correctly get caught
and updated by the resolver on changes of `value` on the foreign model. Note that `totals`
on the interim queryset is only an annotated field which has no persistent database representation, thus cannot be used
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

Here both fields `total` and `intermediate` are annotated and cannot be used in `depends`. Instead resolve
the annotated fields backwards and collect all concrete fields, which reveals `a` and `b` on `related_set`
and `c` on `related_set.fk` as true concrete source fields.

.. NOTE::

    The auto resolver expands dependencies on relational fields on the left side automatically:

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

    Since providing all of those interim dependencies on your own would be exhausting and error-prone,
    it is enough to write the shorthand declaration.
    Note that because of this dependency expansion it is not possible to omit fk field
    relations on purpose, if they are part of a dependency relation chain.

Depending on foreign computed fields works likewise, simply list them as source on the right side.
Again the auto resolver will throw a cycling exception by default, if you created a cycling
update. Other than for local computed field dependencies this can be supressed by setting
``COMPUTEDFIELDS_ALLOW_RECURSION`` to ``True`` in `settings.py`, which allows to use computed fields on self
referencing models, e.g. tree like structures. Note that this currently disables intermodel dependency optimizations
project-wide and might result in high "update pressure". It might also lead to a `RuntimeError` exception
during runtime, if it is a real recursion on record level.


.. TIP::

    Depending on other computed fields is an easy way to lower the "update pressure" later on
    for complicated dependencies by isolating relatively static dependencies from fast turning entities.



Optimization Examples
---------------------

.. TODO::

    To be written:

    - `select_related` example
    - `prefetch_related` example
    - notes on complicated dependencies
    - Possible savings on using `update_fields`
    - some more guidance for bulk actions and `update_dependent`
    - TBD

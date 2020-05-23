Optimizations
=============

The way :mod:`django-computedfields` denormalizes data by precalculating fields at insert/update
time puts a major burden on these actions. Furthermore it synchronizes data between all database
relevant actions from Python, which can cause high update load for computed fields under certain
circumstances. The following tries to give some hints on how to avoid major insert/update bottlenecks.


@computed decorator in detail
-----------------------------

The full decorator declaration reads as:

.. code:: python

    def computed(field, depends=None, select_related=None, select_related=None)

Explanation of the arguments:

- ``field``
    Should be a concrete model field type, that is capable to represent the result of the decorated method.
    The field type must be supported by the `update_fields` keyword of ``save``, since :mod:`django-computedfields`
    heavily relies on partial field updates internally (thus non-concrete fields will not work).

    Compound fields (multiple concrete DB fields) or complicated fields with external logic might work as well,
    but are untested. `ForeignKey` is reported to work (do this on your own risk and with proper integrity tests,
    as it is likely to mess with ORM/transaction assumptions during updates).

    Generic relations with `GenericForeignKey` never gonna work, due to the static nature of the internal dependency graph.

- ``depends``
    Dependency listing of the computed field in the form ``[(relation, list_of_concrete_fieldnames), ...]``.

    The relation should be a string representation of the attribute access (e.g. ``'relA.relB'``) and can contain
    any basic relation type and their backrelations. Generic relations are not supported, also non-relational concrete fields
    must not occur here.

    The right side should list all concrete fieldnames the method pulls data from to calculate
    its value (e.g. for aggrates put the aggregated fieldname there). Forgetting to list a field here most certainly
    will lead to missed updates, as the underlying dependency graph does quite aggressive update optimizations.

    To declare a computed field with no dependencies, set `depends` to an empty iterable. This does not prevent
    a field update, if triggered by other means (e.g. a direct ``save()`` call always re-evaluates all
    local computed fields).

    `Note:` Other than in earlier versions dependencies to local concrete fields (incl. other computed fields)
    should also be listed with ``'self'`` as relation name. Missing the `self` entries will lead to
    undetermined local update behavior, esp. for models with several computed fields or when saved with
    ``save(update_fields=[...])``.

- ``select_related``
    Optional listing of field lookups, that should be joined into the select-for-update queryset to avoid
    additional subqueries by relational field access in the method. Basically the same as for other ORM functions.

- ``prefetch_related``
    Optional listing of field lookups, that should be prefetched and associated with the select-for-update queryset.
    Basically the same as for other ORM functions, but harder to get done right than `select_related`.
    See official Django docs for limitations, and below for some usage hints.


``save`` with `update_fields`
-----------------------------

Django's ORM supports partial model instance updates by providing `update_fields` to ``save``.
This is a great way to lower the update penalty by limiting the DB writes to fields that actually changed.
To keep computed fields in sync with partial writes, :mod:`django-computedfields` will expand `update_fields`
by computed fields, that have dependency intersections, example:

.. code-block:: python

    class MyModel(ComputedFieldsModel):
        name = models.CharField(max_length=256)

        @computed(models.CharField(max_length=256), depends=[['self', ['name']]])
        def uppername(self):
            return self.name.upper()

    # some MyModel obj
    obj.name = 'abc'
    obj.save(update_fields=['name'])  # expanded to ['name', 'uppername']

This deviation from Django's default behavior favours data integrity over strict field listing.
(A future version might provide a save argument to indicate sticking to a given field listing.)


Denormalization pattern
-----------------------

To not suffer not much from updates of computed fields in your project, it is helpful to understand,
which kind of update stress relational dependencies create on the database.
There are two fundamental cases, which greatly differ in that aspect, `n:1` versus `1:n` relations.

n:1 relations - `select_related`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In Django's ORM this is expressed with a `ForeignKey` field on the model itself:

.. code-block:: python

    class MyModel(ComputedFieldsModel):
        fk = models.ForeignKey(OtherModel, ...)

        @computed(Field(...), depends=[['fk', ['field_on_other_model']]])
        def comp(self):
            return self.fk.field_on_other_model

In denormalization terms this is a **FETCH**, as a certain value from a single record of a
different table is pulled into the local space, maybe further processed and finally persisted locally.

Upon a change in an instance `other` of ``OtherModel`` :mod:`django-computedfields` has to determine,
which instances of ``MyModel`` are actually linked to `other`.
This is done with a select query filtering for the relation and triggering the re-evaluation of the
computed field by calling `save`:

.. code-block:: python

    # action
    other.field_on_other_model = 'some new value'
    other.save()

    # update triggered by computedfields
    for entry in MyModel.objects.filter(fk=other).distinct():
        entry.save(update_fields=['comp'])

Since the relation is a foreign key on ``MyModel``, there is a high chance, that multiple entries will be affected
by that single change (update of dependent entries is 1:n, reverse of declarated relation).
`save` itself calls into the method associated with the computed field for every single instance of the queryset.

`Room for optimization?`

Here is a suboptimal access pattern hidden - every single method call will trigger another database lookup
into `OtherModel` to resolve the access to ``self.fk.field_on_other_model`` during the method run.
To avoid that, we can use the `select_related` keyword of the decorator, which instructs the ORM to operate on
a JOIN table extended by values from `fk` instead:

.. code-block:: python

    class MyModel(ComputedFieldsModel):
        fk = models.ForeignKey(OtherModel, ...)

        @computed(Field(...),
            depends=[['fk', ['field_on_other_model']],
            select_related=['fk']
        ])
        def comp(self):
            return self.fk.field_on_other_model

which will lower the query load by `n` for `n` entries to be updated. The underlying queryset will be expanded
by the corresponding `select_related` calls. This also works for multiple FETCHs,
multiple computed fields on one model and over several n:1 relations.

Of course this does not come for free - multiple n:1 relations put into `select_related` will let grow
the JOIN table rather quick, and the entries for multiple computed fields will even stack on the final queryset,
thus the DBMS might struggle to get it done if applied all over the place. This is also the reason, why it
is not done automatically by :mod:`django-computedfields`.


1:n relations - `prefetch_related`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In Django's ORM this is expressed as the reverse relation to a `ForeignKey`:

.. code-block:: python

    class MyModel(ComputedFieldsModel):
        fk = models.ForeignKey(OtherModel, ...)

        @computed(Field(...), depends=[['others', ['value']]])
        def total(self):
            return self.others.aggregate(total=Sum('value'))['total']

    class OtherModel(models.Model):
        value = models.IntegerField()
        fk = models.ForeignKey(MyModel, related_name='others', ...)

In denormalization terms this is often an **AGGREGATE**, as multiple values returned from the relation
are used to do some kind of aggregation on it (e.g. SUM, AVG, MAX).

A change to a single instance of ``OtherModel`` would result in the update logic to touch one entry in `MyModel`,
as the select query to get all entries with dependent computed fields is again the reverse of the
declarated relation (n:1, further reduces to 1:1 here, since we only changed one in ``OtherModel``).

But looking at the actual method code reveals, that more database interaction is needed to correctly update
the `total` field - the ORM has to do another query into ``OtherModel`` to get the aggregation done
(this step is somewhat obscure in Django's ORM notation).

So far this cannot be done any better in terms of query load on the database. But this changes,
as soon as we have deeper nested 1:n relations, e.g. behind a n:1 relation (``'fk.fk_reverse'``)
or another 1:n relation (``'fk_reverse.fk_reverse'``).

For those more complicated relations Django's ORM knows another way to reduce the query load - `prefetch_related`.
Other than for `select_related` above, basic rules when and how to use `prefetch_related` are much harder to find,
as it depends alot on the circumstances, from DB schematics down to plain record count for a particular model.
Still the ``@computed`` decorator allows to place prefetch lookups,
but keep in mind to have an eye on the query count yourself.


.. NOTE::

    Django's ``ManyToManyField`` relations are not handled here explicitly. From a relational perspective
    they are special cases of ``'fk.fk_reverse'`` relations, thus fall under the latter category of "complicated relations".
    Definitely try to avoid them in conjunction with computed fields.


.. NOTE::
    Django's ``OneToOneField`` relations are special cases of 1:n and n:1 relations with reduced update needs
    and handled transparently as listed above.

.. NOTE::
    In terms of denormalization techniques we also skipped **EXTEND** here. Well EXTENDs can easily be done
    either by field annotations or by property methods on a model in Django.
    Nothing to get into :mod:`django-computedfields` business by default, unless the calculation penalty is really high.
    Then they can be constructed with `self` dependencies as shown above.


Complex deep nested relations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

So you really want to declare computed fields with dependencies like:

.. code-block:: python

    class X(ComputedFieldsModel):
        a = models.ForeignKey(OtherModel, ...)

        @computed(Field(..),
            depends=[
                ['a', ['a1', 'a2', ...]],
                ['a.b_reverse', ['b1', 'b2', ...]],
                ['a.b_reverse.c', ['c1', 'c2', ...]],
                ['a.b_reverse.c.d_reverse', ['d1', 'd2', ...]],
                [...]
            ]
        )
        def comp1(self): ...

        @computed(Field(..),
            depends=[
                ['self', ['comp1']],
                ['x', ['x1', 'x2', ...]],
                ['x.y_reverse', ['y1', 'y2', ...]],
                ['x.y_reverse.z', ['z1', 'z2', ...]],
                [...]
            ]
        )
        def comp2(self): ...

To make it simple - yes that is possible with :mod:`django-computedfields` as long as things are cyclefree
(even that can be suppressed to some degree).
Optimizing updates of such a beast is challenging for sure, and cannot be blueprinted by any means.
But how to approach it? Well a few ideas regarding this:

- You should not have built this monster in the first place.
  :mod:`django-computedfields` might look like a nice hammer,
  but it should not turn all your database needs into a nail.
  Maybe look for better suiting tools, like reporting tools crafted for your particular purpose.
- Not convinced? Well, maybe try to identify good use cases for `prefetch_related`,
  the uglier the dependency chain is, the higher the chance you should use a custom `Prefetch` object.
  All on your own risk.
- Still here? Well, maybe do some set theory maths on what you came up with.
  There is a high chance you have intersections created, that are better handled by
  bulk actions and manually triggering `update_dependent` and `update_dependent_multi`.
  Note that :mod:`django-computedfields` tries to keep computed fields in sync for normal instance actions,
  which can create a rather bad update penalty for deeply nested dependencies.
  Also note that you leave normal Django ground here and prolly cannot use many of the default goodies anymore,
  like the admin interface. But sure, writing your own custom update managers will keep you on track to some degree.
- Still not done? Geez, well blame it all on the DBMS itself. Wait no - you are already on O...
  Just kidding - of course, DBMS specific things like native triggers and stored procedures would help
  to squeeze the best performance out of your project. Sad news - :mod:`django-computedfields` does not know anything
  about that, it is only a small helper acting on top of Django's ORM. If you end up here,
  you prolly have bigger issues to handle. Maybe think about switching the framework, other DBMS, database sharding etc.


Fixtures
--------

:mod:`django-computedfields` skips intermodel computed fields updates during fixtures.
Run the management command ``updatedata`` after applying fixtures to synchronize their values.


Migrations
----------

On migration level computed fields are handled as other ordinary concrete fields defined on a model,
thus you can apply any data transfer/transition to them as with other concrete fields.
If you run into migration issues due to changed properties on the `field` argument - the data part
can be ignored/skipped by a custom migration rule. In that case, dont forget to recalculate
the computed field values afterwards to get everything back in sync (e.g. run `updatedata`).

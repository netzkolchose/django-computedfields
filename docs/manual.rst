User Guide
==========

:mod:`django-computedfields` provides autoupdated database fields for
model methods.


Installation
------------

Install the package with pip:

.. code:: bash

    $ pip install django-computedfields

and add ``computedfields`` to your ``INSTALLED_APPS``.

For graph rendering also install :mod:`graphviz`:

.. code:: bash

    $ pip install graphviz


Settings
--------

The module respects optional settings in `settings.py`:

- ``COMPUTEDFIELDS_MAP``
    Used to set a file path for the pickled resolver map. To create the pickled resolver map
    point this setting to a writeable path and call the management command ``createmap``.
    This should always be used in production mode in multi process environments
    to avoid the expensive map creation on every process launch. If set, the file must
    be recreated after model changes to get used by the resolver.

- ``COMPUTEDFIELDS_ADMIN``
    Set this to ``True`` to get a listing of ``ComputedFieldsModel`` models with their field
    dependencies in admin. Useful during development.

- ``COMPUTEDFIELDS_ALLOW_RECURSION``
    Normally cycling updates to the same model field indicate an error in database design.
    Therefore the dependency resolver raises a ``CycleNodeException`` if a cycle was
    encountered. For more complicated setups (like tree structures) you can disable the
    recursion check. This comes with the drawback, that the underlying graph cannot
    linearize and optimize the update paths anymore.

- ``COMPUTEDFIELDS_BATCHSIZE``
    Set the batch size used for computed field updates by the auto resolver (default 100).
    Internally the updates are done by a `bulk_update` on a computed fields model for all
    affected rows and computed fields. Note that taking a rather high value here might
    penalize update performance due high memory usage on Python side to hold the row instances
    and construct the final SQL command. This is further restricted by certain database adapters.

Basic usage
-----------

Simply derive your model from ``ComputedFieldsModel`` and place
the ``@computed`` decorator on a method:

.. code-block:: python

    from django.db import models
    from computedfields.models import ComputedFieldsModel, computed, compute

    class Person(ComputedFieldsModel):
        forename = models.CharField(max_length=32)
        surname = models.CharField(max_length=32)

        @computed(models.CharField(max_length=32), depends=[['self', ['surname', 'forename']]])
        def combined(self):
            return f'{self.surname}, {self.forename}'

``combined`` will be turned into a real database field and can be accessed
and searched like any other database field. During saving the associated method gets called
and its result written to the database. With ``compute(instance, 'fieldname')`` you can
inspect the value that will be written, which is useful if you have pending
changes:

    >>> person = Person(forename='Leeroy', surname='Jenkins')
    >>> person.combined             # empty since not saved yet
    >>> compute(person, 'combined') # outputs 'Jenkins, Leeroy'
    >>> person.save()
    >>> person.combined             # outputs 'Jenkins, Leeroy'
    >>> Person.objects.filter(combined__<some condition>)  # used in a queryset

The ``@computed`` decorator expects a model field instance as first argument to hold the
result of the decorated method.


Automatic Updates
-----------------

The  `depends` keyword argument of the ``@computed`` decorator can be used with any relation
to indicate dependencies to fields on other models as well.

The example above extended by a model ``Address``:

.. code-block:: python

    class Address(ComputedFieldsModel):
        person = models.ForeignKeyField(Person)
        street = models.CharField(max_length=32)
        postal = models.CharField(max_length=32)
        city = models.CharField(max_length=32)

        @computed(models.CharField(max_length=256), depends=[
            ['self', ['street', 'postal', 'city']],
            ['person', ['combined']]
        ])
        def full_address(self):
            return f'{self.person.combined}, {self.street}, {self.postal} {self.city}'

Now a change to ``self.street``, ``self.postal``, ``self.city`` or ``person.combined``
will update ``full_address``. Also changing ``self.person`` will trigger an update of ``full_address``.

Dependencies should be listed as ``['relation_path', list_of_concrete_fieldnames]``.
The relation path can span serveral models, simply name the relation
in python style with a dot (e.g. ``'a.b.c'``). A relation can be any of
foreign key, m2m, o2o and their back relations.
The fieldnames should be a list of strings of concrete fields on the foreign model the method
pulls data from.

.. NOTE::

    The example above contains a special depends rule with ``'self'`` as relation name.
    While it looks awkward to declare model local dependencies explicitly, it is needed
    to correctly trigger computed field updates under any circumstances.
    
    Rule of thumb regarding `depends` - list **ALL** concrete fields a computed field pulls data from,
    even local ones with ``'self'``. Also see examples for further details and more complicated
    situations with annotated fields.

.. NOTE::

    If you allow relations to contain ``NULL`` values you have to handle this case explicitly:

    .. CODE:: python

        @computed(models.CharField(max_length=32), depends=[['nullable_relation', ['field']]])
        def compfield(self):
            # special handling of NULL here as access to
            # self.nullable_relation.field would fail
            if not self.nullable_relation:
                return 'something else'
            # normal invocation with correct data pull across correct relation
            return self.nullable_relation.field

    A special case in this regard are m2m relations during the first save of a newly
    created instance, which cannot access the relation yet. You have to handle this case
    explicitly as well:

    .. CODE:: python

        @computed(models.CharField(max_length=32), depends=[['m2m', ['field']]])
        def compfield(self):
            # no pk yet, access to .m2m will fail
            if not self.pk:
                return ''
            # normal data pull across m2m relation
            return ''.join(self.m2m.all().values_list('field', flat=True))

    Pulling field dependencies over m2m relations has several more drawbacks, in general
    it is a good idea to avoid m2m relations in `depends` as much as possible.
    Also see examples about m2m relations.

.. WARNING::

    With `depends` rules you can easily end up with recursive updates.
    The dependency resolver tries to detect cycling dependencies and might
    raise a ``CycleNodeException`` during startup.


Custom `save` method
--------------------

If you have a custom ``save`` method defined on your model, it is important to note,
that by default local computed field values are not yet updated to their new values during the invocation,
as this happens in ``ComputedFieldModel.save`` afterwards. Thus code in ``save`` still sees old values.

With the decorator ``@precomputed`` you can change that behavior to also update computed fields
before entering your custom save method:

.. code-block:: python

    class SomeModel(ComputedFieldsModel):
        fieldA = ...

        @computed(..., depends=['self', ['fieldA']])
        def comp(self):
            # do something with self.fieldA
            return ...
        
        @precomputed
        def save(self, *args, **kwargs):
            # with @precomputed self.comp already contains
            # the updated value based on self.fieldA changes
            ...
            super(SomeModel, self).save(*args, **kwargs)

It is also possible to further customize the update behavior by applying `skip_computedfields=True`
to ``save`` or by using the ``precomputed`` decorator with the keyword argument `skip_after=True`.
Both will skip the late field updates done by default in ``ComputedFieldModel.save``, thus you have to
make sure to correctly update field values yourself, e.g. by calling ``update_computedfields``.

Fur further guidance see API docs and the source of :meth:`ComputedFieldsModel.save<.models.ComputedFieldsModel.save>` and
:meth:`@precomputed<.resolver.Resolver.precomputed>`.


How does it work internally?
----------------------------

On django startup the dependency resolver collects registered models and computed fields.
Once all project-wide models are constructed and available (on ``app.ready``)
the models and fields are merged and resolved into model and field endpoints.

In the next step the dependency endpoints and computed fields are converted into an adjacency list and inserted
into a directed graph (inter-model dependency graph). The graph does a cycle check during path linearization and
removes redundant subpaths. The remaining edges are converted into a reverse lookup map containing source models
and computed fields to be updated with their queryset access string. For model local field dependencies a similar
graph reduction per model takes place, returning an MRO for local computed fields methods. Finally a union graph of
inter-model and local dependencies is build and does a last cycle check. The whole expensive graph sanitizing process
can be skipped in production by using a precalculated lookup map by setting ``COMPUTEDFIELDS_MAP`` in `settings.py`
(see above).

During runtime certain signal handlers in `handlers.py` hook into model instance actions and trigger
the needed additional changes on associated computed fields given by the resolver maps.
The signal handlers itself call into ``update_dependent``, which creates select querysets for all needed
computed field updates.

In the next step ``resolver.bulk_updater`` applies `select_related` and `prefetch_related` optimizations
to the queryset (if defined) and executes the queryset pulling all possible affected records. It walks the
instances calculating computed field values in in topological order and places the results
in the database by batched `bulk_update` calls.

If another computed field on a different model depends on these changes the process repeats until all
computed fields have been finally updated.

.. NOTE::

    Computed field updates on foreign models are guarded by transactions and get triggered by a `post_save`
    signal handler. Their database values are always in sync between two database relevant model instance
    actions in Python, unless a transaction error occured. Note that this transaction guard does not include
    local computed fields, as they are recalculated during a normal ``save()`` call prior the foreign dependency
    handling. It is your own responsibility to apply appropriate guards over a batch of model instances.
    
    For more advanced usage in conjunction with bulk actions and `update_dependent` see below and in the
    examples documentation.

On ORM level all updates are turned into select querysets filtering on dependent computed field models
in ``update_dependent``. A dependency like ``['a.b.c', [...]]`` of a computed field on model `X` will either
be turned into a queryset like ``X.objects.filter(a__b__c=instance)`` or ``X.objects.filter(a__b__c__in=instance)``,
depending on `instance` being a single model instance or a queryset of model `C`.

The auto resolver only triggers field updates for real values changes by comparing old and new value.
If a `depends` rule contains a 1:`n` relation (reverse fk relation), ``update_dependent`` additionally updates
old relations, that were grabbed by a `pre_save` signal handler.
Similar measures to catch old relations are in place for m2m relations and delete actions (see `handlers.py`).

.. NOTE::

    The fact that you have list all field dependencies explicitly would allow another aggressive optimization in
    the resolver by filtering the select for update queryset for tracked concrete field changes.
    But to achieve arbitrary concrete field change tracking, a before-after comparison is needed, either by
    another SELECT query, or by some copy-on-write logic on any dependency chain model field.
    Currently both seems inappropriate, compared to a slightly sub-optimal single SELECT query for pending updates.


Advanced Usage
--------------

The runtime model described above does not work with bulk actions.
:mod:`django-computedfields` still can be used in combination with bulk actions,
but you have to trigger the needed updates yourself by calling ``update_dependent``, example:

    >>> from computedfields.models import update_dependent
    >>> Entry.objects.filter(pub_date__year=2010).update(comments_on=False)
    >>> update_dependent(Entry.objects.filter(pub_date__year=2010))

Special care is needed, if the bulk changes involve foreign key fields itself,
that are part of a dependency chain. Here related computed model instances have to be collected
before doing the bulk change to correctly update the old relations as well after the action took place:

    >>> # given: some computed fields model depends somehow on Entry.fk_field
    >>> from computedfields.models import update_dependent, preupdate_dependent
    >>> old_relations = preupdate_dependent(Entry.objects.filter(pub_date__year=2010))
    >>> Entry.objects.filter(pub_date__year=2010).update(fk_field=new_related_obj)
    >>> update_dependent(Entry.objects.filter(pub_date__year=2010), old=old_relations)

.. NOTE::

    Handling of old relations doubles the needed database interactions and should not be used,
    if the bulk action does not involve any relation updates at all. It can also be skipped,
    if the foreign key fields do not contribute to a computed field. Since this is sometimes hard to spot,
    :mod:`django-computedfields` provides a convenient listing of contributing foreign key fields accessible
    by ``models.get_contributing_fks()`` or as admin view (if ``COMPUTEDFIELDS_ADMIN`` is set).


For multiple bulk actions consider using ``update_dependent_multi`` in conjunction with
``preupdate_dependent_multi``, which will avoid unnecessary multiplied updates across affected tables.

See method description in the API Reference for further details.


Model Inheritance Support
-------------------------

Abstract Base Classes
^^^^^^^^^^^^^^^^^^^^^

Computed fields are fully supported with abstract model class inheritance. They can be defined
on abstract models or on the final model. They are treated as local computed fields on the final model.

Multi Table Inheritance
^^^^^^^^^^^^^^^^^^^^^^^

Multi table inheritance is supported with the following restriction:

.. NOTE::

    **No automatic up- or downcasting** - the resolver strictly limits updates to model types listed in `depends`.
    Also see example documentation on how to expand updates to neighboring model types manually.


Proxy Models
^^^^^^^^^^^^

Computed fields cannot be placed on proxy models, as it would involve a change to the table,
which is not allowed. Computed fields placed on the original model the proxy links to,
can be used as any other concrete field.


Management Commands
-------------------

- ``createmap``
    recreates the pickled resolver map file. Set the path with ``COMPUTEDFIELDS_MAP`` in `settings.py`.

- ``rendergraph <filename>``
    renders the inter-model dependency graph to `filename`. Note that this command currently only handles
    the inter-model graph, not the individual model graphs and final union graph (PRs are welcome).

- ``updatedata``
    does a full update on all project-wide computed fields. Useful if you ran into serious out of sync issues,
    did multiple bulk changes or after applying fixtures. Note that this command is currently not runtime
    optimized (PRs are welcome).


General Usage Notes
-------------------

:mod:`django-computedfields` provides an easy way to denormalize database data with Django in an automated fashion.
As with any denormalization it should only be used as a last resort to optimize certain query bottlenecks for otherwise
highly normalized data.


Best Practices
^^^^^^^^^^^^^^

- start highly normalized
- cover needed field calculations with field annotations where possible
- do other calculations in normal methods/properties

These steps should be followed first, as they guarantee low to no redundancy of the data if properly done,
before resorting to any denormalization trickery. Of course complicated field calculations create
additional workload either on the database or in Python, which might turn into serious query bottlenecks in your project.

That is the point where :mod:`django-computedfields` can help by creating pre-computed fields.
It can remove the recurring calculation workload during queries by providing precalculated values.
Please keep in mind, that this comes to a price:

- additional space requirement in database
- redundant data (as with any denormalization)
- possible data integrity issues (sync vs. desync state)
- higher project complexity on Django side (signal hooks, ``app.ready`` hook with resolver initialization)
- higher insert/update costs, which might create new bottlenecks

If your project suffers from query bottlenecks created by recurring field calculations and
you have ruled out worse negative side effects from the list above,
:mod:`django-computedfields` can help to speed up some parts of your Django project.


Specific Usage Hints
^^^^^^^^^^^^^^^^^^^^

- Try to avoid deep nested dependencies in general. The way :mod:`django-computedfields` works internally
  will create rather big JOIN tables for many or long relations. If you hit that ground, either try to resort
  to bulk actions with manually using ``update_dependent`` or rework your scheme by introducing additional
  denormalization models or interim computed fields higher up in the dependency chain.
- Try to avoid multiple 1:`n` relations in a dependency chain like ``['fk_back_a.fk_back_b...', [...]]`` or
  ``['m2m_a.m2m_b...', [...]]``, as the query load might explode. Although the auto resolver tries to touch
  affected computed fields only once, it does not help much, if method invocations have to touch 80%
  of all database entries to get the updates done.
- Try to apply `select_related` and `prefetch_related` optimizations for complicated dependencies. While this can
  reduce the query load by far, it also increases memory usage alot, thus it needs proper testing to find the sweep spot.
  Also see optimization examples documentation.
- Try to reduce the "update pressure" by grouping update paths by dimensions like update frequency or update penalty
  (isolate the slowpokes). Mix in fast turning entities late.
- Avoid recursive models. The graph optimization relies on cycle-free model-field path linearization
  during model construction time, which cannot account record level by design. It is still possible to
  use :mod:`django-computedfields` with recursive models (as needed for tree like structures) by setting
  ``COMPUTEDFIELDS_ALLOW_RECURSION = True`` in `settings.py`. Note that this currently disables
  all graph optimizations project-wide for computed fields updates and roughly doubles the update query needs.
  (A future version might allow to explicit mark intended recursions while other update paths still get optimized.)


Fixtures
--------

:mod:`django-computedfields` skips intermodel computed fields updates during fixtures.
Run the management command `updatedata` after applying fixtures to resynchronize their values.


Migrations
----------

On migration level computed fields are handled as other ordinary concrete fields defined on a model,
thus you can apply any migration to them as with other concrete fields.

Still for computed fields you should not rely on data migrations by default and instead resynchronize
their values manually. If you have made changes to a field, that a computed field depends on
(or a computed field itself), either resynchronize the values by calling `update_dependent` with
a full queryset of the changed model (partial update), or do a full resync with the management command
`updatedata`. The latter should be preferred, if you made several changes or have changes,
that affect relations on the dependency graph.


Motivation
----------

:mod:`django-computedfields` is inspired by odoo's computed fields and the lack of
a similar feature in Django's ORM.


Changelog
---------
- 0.1.7
    - add list type support for ``update_fields`` in signal handlers
- 0.1.6
    - maintenace version with CI test dependencies changes:
        - removed Python 3.6
        - removed Django 2.2
        - added Python 3.10
        - added Django 4.0
        - move dev environment to Python 3.10 and Django 3.2

      Note that Django 2.2 will keep working until real incompatible code changes occur.
      This may happen by any later release, thus treat 0.1.6 as last compatible version.

- 0.1.5
    - fix error on model instance cloning
- 0.1.4
    - Django 3.2 support
- 0.1.3
    - better multi table inheritance support and test cases
    - explicit docs for multi table inheritance
- 0.1.2
    - bugfix: o2o reverse name access
    - add docs about model inheritance support
- 0.1.1
    - bugfix: add missing migration
- 0.1.0
    - fix recursion on empty queryset
    - dependency expansion on M2M fields
    - `m2m_changed` handler with filtering on m2m fields
    - remove custom metaclass, introducing `Resolver` class
    - new decorator `@precomputed` for custom save methods
    - remove old `depends` syntax
    - docs update
- 0.0.23:
    - Bugfix: Fixing leaking computed fields in model inheritance.
- 0.0.22:
    - Automatic dependency expansion on reverse relations.
    - Example documentation.
- 0.0.21:
    - Bugfix: Fixing undefined _batchsize for pickled map usage.
- 0.0.20
    - Use `bulk_update` for computed field updates.
    - Allow custom update optimizations with `select_related` and `prefetch_related`.
    - Respect computed field MRO in `compute`.
    - Allow updates on local computed fields from `update_dependent` simplifying bulk actions on `ComputedFieldsModel`.
- 0.0.19
    - Better graph expansion on relation paths with support for `update_fields`.
- 0.0.18
    - New `depends` syntax deprecating the old one.
    - MRO of local computed field methods implemented.
- 0.0.17
    - Dropped Python 2.7 and Django 1.11 support.

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

The module respects optional settings in settings.py:

- ``COMPUTEDFIELDS_MAP``
    Used to set a file path for the pickled resolver map. To create the pickled resolver map
    point this setting to a writeable path and call the management command ``createmap``.
    This should always be used in production mode in multi process environments
    to avoid the expensive map creation on every process launch. If set, the file must
    be recreated after model changes.

- ``COMPUTEDFIELDS_ADMIN``
    Set this to ``True`` to get a listing of ``ComputedFieldsModel`` models with their field
    dependencies in admin. Useful during development.

- ``COMPUTEDFIELDS_ALLOW_RECURSION``
    Normally cycling updates to the same model field indicate an error in database design.
    Therefore the dependency resolver raises a ``CycleNodeException`` if a cycle was
    encountered. For more complicated setups (like tree structures) you can disable the
    recursion check. This comes with the drawback, that the underlying graph cannot
    linearize and optimize the update paths anymore.


Basic usage
-----------

Simply derive your model from ``ComputedFieldsModel`` and place
the ``@computed`` decorator on a method:

.. code-block:: python

    from django.db import models
    from computedfields.models import ComputedFieldsModel, computed

    class Person(ComputedFieldsModel):
        forename = models.CharField(max_length=32)
        surname = models.CharField(max_length=32)

        @computed(models.CharField(max_length=32), depends=[['self', ['surname', 'forename']]])
        def combined(self):
            return u'%s, %s' % (self.surname, self.forename)

``combined`` will be turned into a real database field and can be accessed
and searched like any other database field. During saving the associated method gets called
and its result written to the database. With the method ``compute('fieldname')`` you can
inspect the value that will be written, which is useful if you have pending
changes:

    >>> person = Person(forename='Leeroy', surname='Jenkins')
    >>> person.combined             # empty since not saved yet
    >>> person.compute('combined')  # outputs 'Jenkins, Leeroy'
    >>> person.save()
    >>> person.combined             # outputs 'Jenkins, Leeroy'
    >>> Person.objects.filter(combined__<some condition>)  # used in a queryset

The ``@computed`` decorator expects a model field instance as first argument to hold the
result of the decorated method.


Automatic Updates
-----------------

The  `depends` keyword argument of the decorator can be used with any relation to indicate
dependencies to fields on other models as well.

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
            return u'%s, %s, %s %s' % (self.person.combined, self.street,
                                       self.postal, self.city)

Now a change to ``self.street``, ``self.postal``, ``self.city`` or ``person.combined``
will update ``full_address``.

Dependencies should be listed as ``['relation_name', fieldnames_on_that_model]``.
The relation can span serveral models, simply name the relation
in python style with a dot (e.g. ``'a.b.c'``). A relation can be of any of
foreign key, m2m, o2o and their back relations.
The fieldnames should be a list of strings of concrete fields on the foreign model.

.. WARNING::

    The old `depends` syntax is deprecated and should not be used anymore. It will be removed with
    a future version.

.. NOTE::

    The computed method gets evaluated in the model instance save method. If you
    allow relations to contain ``NULL`` values you have to handle this case explicitly:

    .. CODE:: python

        @computed(models.CharField(max_length=32), depends=[['nullable_relation', ['field']]])
        def compfield(self):
            if not self.nullable_relation:          # special handling of NULL here
                return 'something else'
            return self.nullable_relation.field     # some code referring the correct field

    Computed fields directly depending on m2m relations cannot run the associated
    method successfully on the first ``save`` if the instance was newly created
    (due to Django's order of saving the instance and m2m relations). Therefore
    you have to handle this case explicitly as well:

    .. CODE:: python

        @computed(models.CharField(max_length=32), depends=[['m2m', ['field']]])
        def compfield(self):
            if not self.pk:  # no pk yet, access to .m2m will fail
                return ''
            return ''.join(self.m2m.all().values_list('field', flat=True))

    Generally you should avoid nested m2m relations in dependendies
    as much as possible since the update penalty will explode.

.. NOTE::

    To get proper updates from local field dependencies under any cicumstances
    it is important to provide a `self` entry in ``depends``:

    .. CODE:: python

        address.city = 'New City'
        address.save(update_fields=['city'])  # also updates .full_address

    This works because of the dependency declaration to ``['self', [..., 'city']]`` above.
    Beside correct expansion of ``update_fields`` this is also needed to determine
    the correct execution order of computed fields methods for local dependent computed fields (`MRO`).
    Also note that from version 0.0.19 onwards `update_fields` will slightly deviate from django's
    default behavior. It will be auto expanded by dependent local computed fields and also trigger
    updates on foreign dependent computed fields.

.. CAUTION::

    With the depends strings you can easily end up with recursive updates.
    The dependency resolver tries to detect cycling dependencies and might
    raise a ``CycleNodeException``.


How does it work internally?
----------------------------

``ComputedFieldsModel`` is based on its own metaclass derived from django's model metaclass.
The metaclass collects methods annotated by ``@computed`` and creates the needed database fields
during model construction. Once all project-wide models are constructed and available (on ``app.ready``)
the collected dependency strings are resolved into model and field endpoints with a certain query access string.

In the next step the dependency endpoints and computed fields are converted into an adjacency list and inserted
into a directed graph. The graph does a cycle check during path linearization and removes redundant subpaths.
The remaining edges are converted into a reverse lookup map containing source models and computed fields
to be updated with their queryset access string. For model local field dependencies a similar graph reduction per
model takes place, returning an MRO for local computed fields methods. Finally a union graph of
inter-model and local dependencies is build and does a last cycle check. The expensive graph sanitizing process
can be skipped in production by using a precalculated lookup map (see above).

During runtime certain signal handlers in ``handlers.py`` hook into model instance actions and trigger
the needed additional changes on associated computed fields given by the lookup map.
The signal handlers itself call into ``update_dependent``, which creates querysets for all needed
computed fields updates. A computed field finally gets updated in the database by calling the instance's save method,
which itself calls all to be updated computed fields methods in topological order and places the results in the database.
Currently this is done on individual instance basis (room for improvement with `bulk_update`).
If another computed field on a different model depends on the changes the process repeats until
all computed fields have been updated.

.. NOTE::

    The computed field updates are guarded by transactions and get triggered by post signal handlers.
    The database values of computed fields are always in sync between two database relevant
    instance actions in Python, unless a transaction error occured.

On ORM level all updates are turned into querysets filtering on dependent computed fields models
in ``update_dependent``. A dependency like ``['a.b.c', [...]]`` on a computed fields model `X` will either
be turned into a queryset like ``X.objects.filter(a__b__c=instance)`` or ``X.objects.filter(a__b__c__in=instance)``,
depending on ``instance`` being a single model instance or a queryset of model ``C``.
The queryset gets further reduced by ``.distinct()`` to rule out duplicated entries.
Finally the objects of the queryset get saved with the computed fields name applied to ``update_fields``.
Note that ``save`` only will create an UPDATE query if the computed field value has changed.
If a depends string contains a 1:n relation (reverse fk relation), ``update_dependent`` additionally updates
old relations, that were grabbed by a pre_save signal handler.
Similar measures to catch old relations are in place for M2M and delete actions (see handlers.py).

Currently ``update_dependent`` does not further optimize the update queries. It is suggested above to list all
field dependencies explicitly, which would allow another optimization by comparing field values before and after
the change and further filtering the queryset. To achieve a real before-after comparison, either another SELECT
query is needed and carried forward, or any dependency chain model has to do some copy-on-write for fields in question. 
Currently both seems inappropriate, compared to a single slightly sub-optimal SELECT query for pending updates.


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
    if the foreign key fields to be updated are not part of any computed fields dependency chain.
    Since this is sometimes hard to spot, :mod:`django-computedfields` provides a convenient listing
    of contributing foreign key fields accessible by ``models.get_contributing_fks()`` or as admin view
    (``COMPUTEDFIELDS_ADMIN`` must be set).


For multiple bulk actions consider using ``update_dependent_multi`` in conjunction with
``preupdate_dependent_multi``, which will avoid unnecessary multiplied updates across the database tables.

See method description in the API Reference for further details.


Management Commands
-------------------

- ``createmap``
    recreates the pickled resolver map. Set the file path with ``COMPUTEDFIELDS_MAP``
    in settings.py.

- ``rendergraph <filename>``
    renders the intermodel dependency graph to <filename>. Note that with version 0.0.18
    the internal graph handling got extended by model local graphs and a final union graph.
    Currently this command does not deal with those additional graphs
    (help to get the command fixed is more than welcome).

- ``updatedata``
    does a full update on all computed fields in the project. Only useful after
    tons of bulk changes, e.g. from fixtures.


General Usage Notes
-------------------

:mod:`django-computedfields` provides an easy way to denormalize database data with Django in an automated fashion.
As with any denormalization it should only be used as a last resort to optimize certain query bottlenecks for otherwise
highly normalized data.


Best Practices
^^^^^^^^^^^^^^

- always start highly normalized
- cover needed field calculations with field annotations where possible
- do other calculations, that cannot be covered in field annotations, in normal methods/properties

These steps should always be followed first, as they guarantee low to no redundancy of the data if properly done,
before resorting to any denormalization trickery. Of course complicated field calculations create
additional workload either on the database or in Python, which might turn into serious query bottlenecks in your project.

That is the point where :mod:`django-computedfields` can help by creating (pre-) computed fields.
It can greatly lower recurring query workload by providing a precalculated value instead of recalculating it everytime.
Please keep in mind, that this comes to a price:

- additional space requirement in database
- redundant data (as with any denormalization)
- higher project complexity (different model metaclass, signal hooks, ``app.ready`` hook)
- higher insert/update costs, which might create new bottlenecks if carelessly used

If your project suffers from query bottlenecks created by recurring field calculations and
you have ruled out worse negative side effects from the list above,
:mod:`django-computedfields` certainly can help to speed up some parts of your Django project.


Specific Usage Hints
^^^^^^^^^^^^^^^^^^^^

- Try to avoid deep nested dependencies. The way :mod:`django-computedfields` works internally will create
  rather big JOIN tables for many long relations. If you hit that ground, either try to resort
  to bulk actions with manually using ``update_dependent`` or rework your scheme by introducing additional
  denormalization models.
- Try to avoid multiple 1:n relations in a dependency chain like ``['fk_back_a.fk_back_b...', [...]]`` or
  ``['m2m_a.m2m_b...', [...]]``, as the query penalty might explode. Although the querysets are stripped down by
  ``.distinct()`` before doing the updates, the DBMS might have a hard time to join and filter the entries
  in the first place, if the tables are getting big.
- Try to keep the record count low on related computed fields models, as ``update_dependent`` has to run the method
  for every associated record to correctly update its value. (For future versions this is less of a problem
  once `select_related`, `prefetch_related` and `bulk_update` optimizations are in place.)
- Avoid recursive models. The graph optimization relies on cycle-free model-field path linearization
  during model construction time, which cannot account record level by design. It is still possible to
  use :mod:`django-computedfields` with recursive models (as needed for tree like structures) by setting
  ``COMPUTEDFIELDS_ALLOW_RECURSION`` to ``True`` in `settings.py`. Note that this currently disables
  all graph optimizations project-wide for computed fields updates and roughly doubles the update query needs.
  (A future version might allow to explicit mark intended recursions while other update paths still get optimized.)


Motivation
----------

:mod:`django-computedfields` is inspired by odoo's computed fields and the lack of
a similar feature in Django's ORM.


Changelog
---------

- 0.0.19
    - Better graph expansion on relation paths with support for `update_fields`.
- 0.0.18
    - New `depends` syntax deprecating the old one.
    - MRO of local computed field methods implemented.
- 0.0.17
    - Dropped Python 2.7 and Django 1.11 support.

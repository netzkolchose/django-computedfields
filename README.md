[![build](https://github.com/netzkolchose/django-computedfields/actions/workflows/build.yml/badge.svg)](https://github.com/netzkolchose/django-computedfields/actions/workflows/build.yml)
[![Coverage Status](https://coveralls.io/repos/github/netzkolchose/django-computedfields/badge.svg?branch=master)](https://coveralls.io/github/netzkolchose/django-computedfields?branch=master)


### django-computedfields

django-computedfields provides autoupdated database fields
for model methods.

Tested with Django 3.2 and 4.2 (Python 3.8 to 3.11).


#### Example

Just derive your model from `ComputedFieldsModel` and place
the `@computed` decorator at a method:

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, computed

class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[('self', ['name'])])
    def computed_field(self):
        return self.name.upper()
```

`computed_field` will be turned into a real database field
and can be accessed and searched like any other database field.
During saving the associated method gets called and it’s result
written to the database.


#### How to recalculate without saving the model record

If you need to recalculate the computed field but without saving it, use
`from computedfields.models import compute`

```python
>>> from computedfields.models import compute
>>> person = MyModel.objects.get(id=1)  # this is to retrieve existing record
>>> person.computed_field               # outputs 'BERTY'
>>> person.name = 'nina'                # changing the dependent field `name` to nina
>>> compute(person, 'computed_field')   # outputs 'NINA'
>>> person.computed_field               # outputs 'BERTY' because the `person` is not yet saved
>>> person.save()                       # alters the database record for `name` and `computed_field`
>>> person.computed_field               # outputs 'NINA'
```

#### `depends` keyword

The  `depends` keyword argument can be used with any relation to indicate dependencies to fields on other models as well:

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, computed

class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    fk = models.ForeignKey(SomeModel)

    @computed(
        models.CharField(max_length=32),
        depends=[
            ('self', ['name']),
            ('fk', ['fieldname'])
        ]
    )
    def computed_field(self):
        return self.name.upper() + self.fk.fieldname
```

Now changes to `self.name`, `fk` or `fk.fieldname` will update `computed_field`.


#### Alternative Syntax

Instead of using the `@computed` decorator with inline field definitions,
you can also use a more declarative syntax with `ComputedField`, example from above rewritten:

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, ComputedField

def get_upper_string(inst):
    return inst.name.upper()

class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    computed_field = ComputedField(
        models.CharField(max_length=32),
        depends=[('self', ['name'])],
        compute=get_upper_string
    )
```


#### Documentation

The documentation can be found [here](https://django-computedfields.readthedocs.io/en/latest/index.html).


#### Changelog

- 0.2.9
    - fix related_query_name issue
- 0.2.8
    - Django 5.2 support
- 0.2.7
    - setuptools issue fixed
- 0.2.6
    - Django 5.1 support
- 0.2.5
    - Django 5.0 & Python 3.12 support
    - Django 3.2 support dropped
- 0.2.4
    - performance improvement: use OR for simple multi dependency query construction
    - performance improvement: better queryset narrowing for M2M lookups
    - `ComputedField` for a more declarative code style added

- 0.2.3
    - performance improvement: use UNION for multi dependency query construction

- 0.2.2
    - Django 4.2 support
    - Use `model._base_manager` instead of `model.objects` to prevent using overridden `models.objects` with a custom manager

- 0.2.1
    - Django 4.1 support

- 0.2.0 - next beta release
    - new features:
        - better memory control for the update resolver via
          ``COMPUTEDFIELDS_QUERYSIZE`` or as argument on ``@computed``
        - update optimization - early update-tree exit
        - faster updates with ``COMPUTEDFIELDS_FASTUPDATE``
        - `checkdata` command
        - `showdependencies` command
        - typing support for computed fields

    - enhancements:
        - better `updatedata` command

    - removed features:
        - transitive reduction on intermodel graph (due to negative impact)
        - pickled resolver map (due to showing low benefit)
        - `update_dependent_multi` and `preupdate_dependent_multi`
          (due to showing low benefit and being a code nuisance)
        - Django 2.2 shims removed

    - bug fixes:
        - regression on proxy models fixed
        - sliced querset support for mysql fixed

- 0.1.7
    - add list type support for `update_fields` in signal handlers

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
    - remove custom metaclass, introducing *Resolver* class
    - new decorator `@precomputed` for custom save methods
    - old *depends* syntax removed
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
    - Allow custom update optimizations with *select_related* and *prefetch_related*.
    - Respect computed field MRO in `compute`.
    - Allow updates on local computed fields from `update_dependent` simplifying bulk actions on `ComputedFieldsModel`.
- 0.0.19
    - Better graph expansion on relation paths with support for *update_fields*.
- 0.0.18
    - New *depends* syntax deprecating the old one.
    - MRO of local computed field methods implemented.
- 0.0.17
    - Dropped Python 2.7 and Django 1.11 support.

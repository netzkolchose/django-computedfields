[![Build Status](https://travis-ci.org/netzkolchose/django-computedfields.svg?branch=master)](https://travis-ci.org/netzkolchose/django-computedfields)
[![Coverage Status](https://coveralls.io/repos/github/netzkolchose/django-computedfields/badge.svg?branch=master)](https://coveralls.io/github/netzkolchose/django-computedfields?branch=master)

### django-computedfields ###

django-computedfields provides autoupdated database fields
for model methods.

Tested with Django 2.2 and 3.0 (Python 3.6 to 3.8).


#### Example ####

Just derive your model from `ComputedFieldsModel` and place
the `@computed` decorator at a method:

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, computed

class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[['self', ['name']]])
    def computed_field(self):
        return self.name.upper()
```

`computed_field` will be turned into a real database field
and can be accessed and searched like any other database field.
During saving the associated method gets called and it’s result
written to the database. With the method `compute('fieldname')`
you can inspect the value that will be written, which is useful
if you have pending changes:

```python
>>> person = MyModel(forename='berty')
>>> person.computed_field             # empty since not saved yet
>>> person.compute('computed_field')  # outputs 'BERTY'
>>> person.save()
>>> person.computed_field             # outputs 'BERTY'
```

The  `depends` keyword argument can be used with any relation to indicate dependencies to fields on other models as well:

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, computed

class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    fk = models.ForeignKey(SomeModel)

    @computed(models.CharField(max_length=32), depends=[['self', ['name']], ['fk', ['fieldname']]])
    def computed_field(self):
        return self.name.upper() + self.fk.fieldname
```

Now changes to `self.name` or `fk.fieldname` will update `computed_field`.


#### Documentation ####

The documentation can be found [here](https://django-computedfields.readthedocs.io/en/latest/index.html).


#### Changelog ####

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

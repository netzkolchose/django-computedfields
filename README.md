### django-computedfields ###

**Goal:** Make it possible to autogenerate real db fields
from model decorator functions.


#### Design & API ###

The functionality is provided by a custom model metaclass, that turns
all `@computed` decorated methods into real model fields. The fields
can be accessed normally and represent the db value. With the method
`model_object.compute('fieldname')` the computed value can be accessed.
Upon saving all computed fields are written to db.

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, computed


class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    
    @computed(models.CharField(max_length=32), depends=[])
    def other(self):
        return '%s-pansen' % self.name
```

Access to the value:

```python
obj = MyModel()
obj.other               # get db value
obj.compute('other')    # get computed value
obj.save()              # writes computed value to db
```

The `computed` decorator supports a `'depends'` keyword argument to indicate dependencies to other
models. On startup the module creates paths to resolve those dependencies and update computed
fields automatically.

**TODO:**

- better path resolver
- management command to drilldown paths and avoid heavy computation on every thread start
- tests for all possible relations
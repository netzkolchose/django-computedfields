from django.db import models
from computedfields.models import computed, ComputedFieldsModel
from contextlib import ContextDecorator
from django.db import connection


class QueryCounter(ContextDecorator):
    def __init__(self, show_queries=False, fmt_string=None):
        super(QueryCounter, self).__init__()
        self.show_queries = show_queries
        self.fmt_string = fmt_string or '{count} queries'

    def __enter__(self):
        self.initial = len(connection.queries)
        return self

    def __exit__(self, *exc):
        if not any(exc):
            excess = len(connection.queries) - self.initial
            print(self.fmt_string.format(**{'count': excess}))
            if self.show_queries:
                for q in connection.queries[-excess:]:
                    print(q['sql'])
        return False


class BParent(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    
class BChild(models.Model):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(BParent, on_delete=models.CASCADE)

class BSubChild(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(BChild, on_delete=models.CASCADE)

    @computed(models.CharField(max_length=32),
        depends=[
            ['parent', ['name']],
            ['parent.parent', ['name']]
        ],
        select_related=('parent__parent',)
    )
    def parents(self):
        return self.name + '$' + self.parent.name + '$' + self.parent.parent.name


class BParentReverse(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=256),
        depends=[
            ['children', ['name']],
            ['children.subchildren', ['name']],
        ],
        prefetch_related=('children__subchildren',)
    )
    def children_comp(self):
        s = []
        for child in self.children.all():
            s.append(child.name)
            ss = []
            for sub in child.subchildren.all():
                ss.append(sub.name)
            if ss:
                s.append('#'.join(ss))
        return '$'.join(s)
    
class BChildReverse(models.Model):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(BParentReverse, related_name='children', on_delete=models.CASCADE)

class BSubChildReverse(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    parent = models.ForeignKey(BChildReverse, related_name='subchildren', on_delete=models.CASCADE)

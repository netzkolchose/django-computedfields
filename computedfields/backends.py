from fast_update.fast import fast_update
from fast_update.update import flat_update
from django.db.models import QuerySet
from typing import Sequence, Any, Iterable


def FAST(queryset: QuerySet, objs: Sequence[Any], fields: Iterable[str]) -> int:
    return fast_update(queryset, objs, tuple(fields), None, True)

def FLAT(queryset: QuerySet, objs: Sequence[Any], fields: Iterable[str]) -> int:
    return flat_update(queryset, objs, tuple(fields), True)

def SAVE(queryset: QuerySet, objs: Sequence[Any], fields: Iterable[str]) -> int:
    from .resolver import NotComputed
    with NotComputed():
        for inst in objs:
            inst.save(update_fields=fields)
        return len(objs)

def BULK(queryset: QuerySet, objs: Sequence[Any], fields: Iterable[str]) -> int:
    return queryset.model._base_manager.bulk_update(objs, fields)

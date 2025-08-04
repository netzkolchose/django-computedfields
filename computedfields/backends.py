from fast_update.fast import fast_update
from fast_update.update import flat_update
from django.db.models import QuerySet
from typing import Sequence, Any, Iterable


def fast(queryset: QuerySet, objs: Sequence[Any], fields: Iterable[str]) -> int:
    return fast_update(queryset, objs, tuple(fields), None, True)

def flat(queryset: QuerySet, objs: Sequence[Any], fields: Iterable[str]) -> int:
    return flat_update(queryset, objs, tuple(fields), True)

def save(queryset: QuerySet, objs: Sequence[Any], fields: Iterable[str]) -> int:
    from .resolver import NotComputed
    with NotComputed():
        for inst in objs:
            inst.save(update_fields=fields)
        return len(objs)

def bulk(queryset: QuerySet, objs: Sequence[Any], fields: Iterable[str]) -> int:
    return queryset.model._base_manager.bulk_update(objs, fields)


UPDATE_IMPLEMENTATIONS = {
    'FAST': fast,
    'FLAT': flat,
    'SAVE': save,
    'BULK': bulk
}

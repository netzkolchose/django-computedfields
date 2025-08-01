from collections import defaultdict
from operator import attrgetter
from django.db.models import QuerySet, Manager
import math

from typing import Sequence, Any, Iterable, List


"""
Cost Prediction for Updates

To decide, whether the merge attempt saves any runtime, we do a cost prediction
with these assumptions:

- any value transfer costs 1w
- an UPDATE(1) call costs 10w and grows in O(lb n) for n pks

work in flat mode:
Flat means, that we transfer values for each object in a separate UPDATE.
    ==> n * UPDATE(1) + n * field_count (for n updates)

work in merged mode:
In merged mode we sum the costs of two update components:
    flat residues  ==> n * UPDATE(1) + counted_values (for n flat residues)
    merged updates ==> n * UPDATE(m) + counted_values (for n updates with m pks)

If the ratio of merged/flat work is below 0.8, the merged updates get applied.

The predictor works close enough in local tests with sqlite and postgres,
but will hugely be skewed by several factors:
- weight of field types (an integer is cheaper than a long string)
- DB latency (with higher latency merge will be underestimated)

Both, type weighing and latency measuring is def. out of scope,
thus the predictor gives only a conversative estimate preferring flat mode.
"""


def upd_pk_work(n):
    return 10 + math.log2(n)
UDP_1 = upd_pk_work(1)


def predictor(objs, fields, merged_updates, unhashable):
    # flat work
    flat_work = (len(fields) + UDP_1) * len(objs)

    # flat residues
    uh_work = len(unhashable.keys()) * UDP_1 + sum(map(len, unhashable.values()))

    # merged updates
    mg_work = (sum(upd_pk_work(len(o)) for o in merged_updates.keys())
               + sum(map(len, merged_updates.values())))

    return (uh_work + mg_work) / flat_work


def _update_inner(
    manager: Manager,
    objs: Sequence[Any],
    fields: List[str],
    force_flat: bool
) -> None:
    # try merging updates if we have at least 3 objects
    # NOTE: the update order is not preserved for duplicate pks
    # we assume, that those dont occur due to DISTINCT/UNION
    if not force_flat and len(objs) > 2:
        merged_pks = defaultdict(lambda: defaultdict(list))
        unhashable = defaultdict(dict)

        for fieldname in fields:
            accu = merged_pks[fieldname]
            get_value = attrgetter(fieldname)
            for o in objs:
                value = get_value(o)
                try:
                    accu[value].append(o.pk)
                except TypeError:
                    unhashable[o.pk][fieldname] = value
            # TODO: should we bail out early, if merge looks bad?

        merged_updates = defaultdict(dict)
        for fieldname, pkdata in merged_pks.items():
            for value, pks in pkdata.items():
                if len(pks) == 1:
                    # transfer to unhashable to allow field merge there
                    unhashable[list(pks)[0]][fieldname] = value
                else:
                    merged_updates[frozenset(pks)][fieldname] = value

        if predictor(objs, fields, merged_updates, unhashable) < 0.8:
            for pks, data in merged_updates.items():
                manager.filter(pk__in=pks).update(**data)
            for pk, data in unhashable.items():
                manager.filter(pk=pk).update(**data)
            return

    # use flat updates on objs
    get_values = attrgetter(*fields)
    if len(fields) == 1:
        for o in objs:
            manager.filter(pk=o.pk).update(**{fields[0]: get_values(o)})
    else:
        for o in objs:
            manager.filter(pk=o.pk).update(**dict(zip(fields, get_values(o))))


def _update(
    queryset: QuerySet,
    objs: Sequence[Any],
    fieldnames: Iterable[str],
    force_flat: bool = False
) -> None:
    """
    Updates fieldnames of objs with the help of Manager.update().

    The update supports 2 operation modes *merged* and *flat*.
    By default *merged* is active and will try to merge the values into less UPDATE calls.
    For many intersecting values this will increase the update performance significantly.
    The merge comes with the downside of re-ordering the updates and might even touch a row
    in the database multiple times. It also does not work with duplicates anymore.

    If you need strict update order or have other constraints like touching a row just once,
    you can force to use the *flat* mode by setting *force_flat=True*. In *flat* mode,
    each object creates at least one UPDATE with preserved order.
    """
    model = queryset.model

    # separate MT parent fields
    non_local_fields = defaultdict(list)
    local_fields = []
    for fieldname in fieldnames:
        field = model._meta.get_field(fieldname)
        if field not in model._meta.local_fields:
            non_local_fields[field.model._base_manager].append(fieldname)
        else:
            local_fields.append(fieldname)
    
    # perform the updates on model, then on parent models
    if local_fields:
        _update_inner(model._base_manager, objs, local_fields, force_flat)
    for manager, fields in non_local_fields.items():
        _update_inner(manager, objs, fields, force_flat)
    # FIXME: return updated row count


def flat_update(
    queryset: QuerySet,
    objs: Sequence[Any],
    fieldnames: Iterable[str],
    force_flat: bool = False
) -> None:
    return _update(queryset, objs, fieldnames, True)


def merged_update(
    queryset: QuerySet,
    objs: Sequence[Any],
    fieldnames: Iterable[str],
    force_flat: bool = False
) -> None:
    return _update(queryset, objs, fieldnames, False)

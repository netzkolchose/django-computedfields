from itertools import tee, zip_longest
from django.db.models import Model, QuerySet
from typing import Any, Generator, Iterable, Iterator, List, Sequence, Type, TypeVar, Tuple

T = TypeVar('T', covariant=True)


def pairwise(iterable: Sequence[T]) -> Iterator[Tuple[T, T]]:
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def modelname(model: Type[Model]) -> str:
    return f'{model._meta.app_label}.{model._meta.model_name}'


def is_sublist(needle: Sequence[Any], haystack: Sequence[Any]) -> bool:
    if not needle:
        return True
    if not haystack:
        return False
    max_k = len(needle) - 1
    k = 0
    for elem in haystack:
        if elem != needle[k]:
            k = 0
            continue
        if k == max_k:
            return True
        k += 1
    return False


def parent_to_inherited_path(parent: Type[Model], inherited: Type[Model]) -> List[str]:
    """
    Pull relation path segments from `parent` to `inherited` model
    in multi table inheritance.
    """
    bases = inherited._meta.get_base_chain(parent)
    relations: List[str] = []
    model = inherited
    for base in bases:
        relations.append(model._meta.parents[base].remote_field.name)
        model = base
    return relations[::-1]


def skip_equal_segments(ps: Sequence[str], rs: Sequence[str]) -> List[str]:
    """
    Skips all equal segments from the beginning of `ps` and `rs`
    returning left over segments from `ps`.
    """
    add: bool = False
    ret: List[str] = []
    for left, right in zip_longest(ps, rs):
        if left is None:
            break
        if left != right:
            add = True
        if add:
            ret.append(left)
    return ret


def subquery_pk(qs: QuerySet, using: str = 'default') -> Iterable[Any]:
    from django.db import connections
    if connections[using].vendor == 'mysql':
        return list(qs.values_list('pk', flat=True).iterator())
    return qs.values('pk').iterator()


def slice_iterator(qs: 'QuerySet[Model]', size: int) ->  Generator[Model, None, None]:
    """
    Generator for either sliced or iterated querysets.
    This greatly lowers the needed memory for big querysets,
    that easily would grow to GBs of RAM by normal iteration.
    Uses either .iterator(size) or slicing, depending on prefetch settings.
    (favors prefetch with higher memory needs over blunt iterator optimization)
    """
    if not qs._prefetch_related_lookups:
        for obj in qs.iterator(size):
            yield obj
    else:
        pos = 0
        while True:
            c = 0
            for obj in qs.order_by('pk')[pos:pos+size]:
                yield obj
                c += 1
            if c < size:
                break
            pos += size

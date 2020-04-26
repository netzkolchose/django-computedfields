Optimizations
=============


- build a query/record inspector as context decorator
- should return:
    - numbers of queries
    - numbers of records touched
    - verbose:
        - show queries
        - record expansion through relations possible?

- When should computedfields (not) be used? ...

- give optimization hints about typical denormalization pattern
    - with annotations in the first place
    - with python methods in the second place, probably with caching
    - if possible, use db level methods (db views, stored procedures)
    - use computedfields (if ypu are lazy, skip steps above)
    - find update bottlenecks, inspect with query inspector
    - DOs and DONTs, examples for the following types
    - FETCH
        - pulling data from n : 1 relations
        - in computedfields 'fka.fkb...'
        - use select_related
    - EXTEND
        - pulling data from same table row
        - no special handling in computedfields needed
    - AGGREGATE
        - pulling data from 1 : n relations
        - do some aggregating on the data (SUM, AVG, MAX, ...)
        - in computedfields 'fka_reverse.fkb_reverse...'
        - use prefetch_related or "upside-down" querying in method, otherwise really bad runtime
    - COMPLEX
        - mixture of FETCH/EXTEND/AGGREGATE
        - often done by (external) reporting tools to extract complex data (drilldown)
        - easy to end up with in computedfields, but hard to optimize!
        - examples ['fka.fkb_reverse', 'm2ma.m2mb']
        --> needs special attention
        --> still no reporting tool without additional measures (like auditing/timetracking)


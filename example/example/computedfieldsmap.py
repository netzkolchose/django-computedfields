data = b"""(dp1
."""
try:
    from cPickle import loads
except ImportError:
    from pickle import loads

map = loads(data)

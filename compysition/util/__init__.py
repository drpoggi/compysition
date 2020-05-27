import warnings
from contextlib import contextmanager
import sys

__all__ = ('ignore', 'try_decode', 'PY2', 'PY3', 'PY3_5plus', 'get_uuid', 'iterkeys', 'iteritems', 'itervalues', 'range_')

@contextmanager
def ignore(*exceptions):
	try:
		yield
	except exceptions:
		pass

_default_warning_filter = 'always'

def set_warning_filter():
    warnings.simplefilter(_default_warning_filter, DeprecationWarning)
    warnings.simplefilter(_default_warning_filter, PendingDeprecationWarning)

@contextmanager
def suppress_deprecation():
    warnings.simplefilter("ignore", DeprecationWarning)
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    yield
    warnings.simplefilter(_default_warning_filter, DeprecationWarning)
    warnings.simplefilter(_default_warning_filter, PendingDeprecationWarning)

def raise_(exception):
    raise exception

'''
	Version specific utils
'''

PY3 = True if sys.version_info[0] == 3 else False
PY3_5plus = PY3 and sys.version_info[1] > 5
PY2 = False if PY3 else True

def _get_decode():
	if PY2:
		return lambda data: data.decode().encode('latin-1')
	return lambda data: data.decode()

def _get_encode():
	if PY2:
		return lambda data: data
	return lambda data: data.encode()

_decode = _get_decode()
_encode = _get_encode()

def try_decode(data):
	with ignore(KeyError, AttributeError):
		return _decode(data)
	return data

def try_encode(data):
	with ignore(AttributeError):
		return _encode(data)
	return data

def _get_uuid_func():
	from uuid import uuid4 as uuid
	if PY2:
		return lambda: uuid().get_hex()
	return lambda: uuid().hex

def _get_iterkeys():
	if PY2:
		return lambda obj: obj.iterkeys()
	return lambda obj: iter(obj.keys())

def _get_iteritems():
	if PY2:
		return lambda obj: obj.iteritems()
	return lambda obj: iter(obj.items())

def _get_itervalues():
	if PY2:
		return lambda obj: obj.itervalues()
	return lambda obj: iter(obj.values())

def _get_range():
	if PY2:
		return xrange
	return range

range_ = _get_range()
get_uuid = _get_uuid_func()
iterkeys = _get_iterkeys()
iteritems = _get_iteritems()
itervalues = _get_itervalues()
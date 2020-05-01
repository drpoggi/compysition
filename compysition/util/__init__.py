import warnings
from contextlib import contextmanager

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

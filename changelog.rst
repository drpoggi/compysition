Compysition changelog
=====================

Version
1.3.1

- Added python2/python3/python3.5+ flags.
    - Used flags to implement version specific functionality (s.a. iterables, imports, etc.).
- Made adjustments to remove warnings.
- Adjusted event functions to ensure the decoding of bytearrays (python3 utilizes bytearrays quite often).
- Replaced python2 specific HTTPServer testutils with new python2 and python3 compatible versions
- Adjusted metaclass implementations to support python2 and python3
- Wrapped filter and map functions with list() to support python2 and python3
- Ensured all current unittests were successfully running under python2 and python3
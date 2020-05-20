Compysition changelog
=====================

Version
1.3.1

- Adjusted pickling techniques to improve performance.
    - Now utilizes highest pickle protocol in mpdactor functions.
    - event cloning now utilizes direct pickling vs deepcopy
    - actor-actor event passing now uses new event xclone function which utilizes locally stored raw pickle data and iteration to increase performance
- Added __slots__ to various event types to decrease memory footprint.
    - Adjusted event pickling functions to accomodate __slots__ and keep event dynamicness.
Compysition changelog
=====================

Version
1.3.0

- Adjusted pickling techniques to improve performance.
    - Now utilizes highest pickle protocol in mpdactor functions.
    - event cloning now utilizes direct pickling vs deepcopy
    - actor-actor event passing now uses new event xclone function which utilizes locally stored raw pickle data and iteration to increase performance
- Added __slots__ to various event types to decrease memory footprint.
    - Adjusted event pickling functions to accomodate __slots__ and keep event dynamicness.
- Added new event types to better support requests with 'application/x-www-form-urlencoded' mime-types.
    - Adds ability to respond to requests in 'application/x-www-form-urlencoded' format.
    - Includes special event types for JSON/XML data passed via 'application/x-www-form-urlencoded'.  However the use of these special types is NOT the default behavior. They optional via an HTTPServer parameter to preserve functionality.
    - All non-JSON/XML based data passed via 'application/x-www-form-urlencoded' is interpreted via the new XWWWFORMHttpEvent which makes converting this mime-type to JSON and/or XML a built in feature.
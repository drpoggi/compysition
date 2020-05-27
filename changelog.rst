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
- Adjusted ContentTypePlugin to properly validate Content-Type headers.
    - Now validates all incoming requests vs only the first.
    - Now instantly triggers HTTP errors when met with requests containing missing/empty Content-Type headers and have a non-empty body.
- Extracted accept header logic from HTTPServer into an AcceptPlugin.
    - No longer ignores Accept header altogether when an unknown mime-type is encountered.
    - Implements route based Accept definitions.
    - No longer selects target response Content-Type prior to service processing.  Now performs narrowing functions upon receiving a request and selects target response Content-Type immediately prior to send response.  Narrowed mime-types are stored in responders dict to mimize event size.  Selection now prioritizes matching incoming mime-type, service desired mime-type, current event type's corresponding mime-type, and defaults to first available mime-type from narrowing process.
    - Implements new response object _CompysitionHTTPError which is used to pass a request's matching route to HTTPServer's optional Bottle error handler.  Allowing for route Accept type definitions to be applied to these Bottle handled errors.
- Added python2/python3/python3.5+ flags.
    - Used flags to implement version specific functionality (s.a. iterables, imports, etc.).
- Made adjustments to remove warnings.
- Adjusted event functions to ensure the decoding of bytearrays (python3 utilizes bytearrays quite often).
- Replaced python2 specific HTTPServer testutils with new python2 and python3 compatible versions
- Adjusted metaclass implementations to support python2 and python3
- Wrapped filter and map functions with list() to support python2 and python3
- Ensured all current unittests were successfully running under python2 and python3
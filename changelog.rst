Compysition changelog
=====================

Version
1.3.0

- Added new event types to better support requests with 'application/x-www-form-urlencoded' mime-types.
    - Adds ability to respond to requests in 'application/x-www-form-urlencoded' format.
    - Includes special event types for JSON/XML data passed via 'application/x-www-form-urlencoded'.  However the use of these special types is NOT the default behavior. They optional via an HTTPServer parameter to preserve functionality.
    - All non-JSON/XML based data passed via 'application/x-www-form-urlencoded' is interpreted via the new XWWWFORMHttpEvent which makes converting this mime-type to JSON and/or XML a built in feature.
- Reworked unittests in tests/test_actor.py to better test the overall functionality rather than method calls.
Compysition changelog
=====================

Version
1.3.0

- Added new event types to better support requests with 'application/x-www-form-urlencoded' mime-types.
    - Adds ability to respond to requests in 'application/x-www-form-urlencoded' format.
    - Includes special event types for JSON/XML data passed via 'application/x-www-form-urlencoded'.  However the use of these special types is NOT the default behavior. They optional via an HTTPServer parameter to preserve functionality.
    - All non-JSON/XML based data passed via 'application/x-www-form-urlencoded' is interpreted via the new XWWWFORMHttpEvent which makes converting this mime-type to JSON and/or XML a built in feature.

1.3.1

- Fixed CallbackUDPEventProducer to properly persist callback capabilities through master/slave changes.
- Added EventDataCompare Actor
- Fixed Decimal import for Events

1.3.2

- Adjusted x-www-form-urlencoded JSON/XML handling to be case insensitive
    - Required minor changes to HTTPServer, _XMLXWWWFORMHttpEvent, and _JSONXWWWFORMHttpEvent

1.3.3

- Fixed x-www-form-urlencoded decode/encode functionality.
	- Now properly decodes `+`s as ` `s and encodes ` `s as `+`s
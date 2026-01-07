# Basic tools for interacting with the database

This module provides tools for interacting with a database connection that are
usable both from Zope and other modules.

As a first step, it has a Connection class that provides a unified execute
method as well as a wrapper that can be used to pass a ZRDBConnection from Zope
to obtain a similar class. Future increments will include CRUD functions for
DB-Utils compatible database interactions.

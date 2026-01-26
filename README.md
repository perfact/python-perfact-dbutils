# Basic tools for interacting with the database

This module provides tools for interacting with a database connection that are
usable both from Zope and other modules.

As a first step, it has a Connection class that provides a unified execute
method as well as a wrapper that can be used to pass a ZRDBConnection from Zope
to obtain a similar class. Future increments will include CRUD functions for
DB-Utils compatible database interactions.

# Implement and run tests

If you add new functions place your tests below `perfact/dbutils/tests`.
Implement your test using `pytest`.

You may have to install postgres if not already installed:
`sudo apt install postgresql-<version>`

Now you can run your tests by running `tox`. All tests need to succeed and your
tests need to cover 100% of the code. Tox will tell you which lines are
missing.
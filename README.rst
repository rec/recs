recs: @rec's tiny useful Python toolbox
--------------------------------------------

Contains one essential thing, and a few other minorly useful bits.


``ImportAllTest``: test that all modules import successfully
===============================================================

Not every file is covered by unit tests, particularly scripts;  and unit tests
won't report any new warnings that occur.

``ImportAllTest`` automatically loads each Python file or module reachable from
your root directory.  Warnings are by default treated as errors.

I drop this into each new project as my first test.  It inevitably catches a
host of problems, particularly when I'm in rapid development and running a
subset of tests.

In the most common usage, just add this tiny file
`all_test.py <https://raw.githubusercontent.com/rec/import_all/master/all_test.py/>`_.
anywhere in your unit test directory:

.. code-block:: python

    import import_all


    class ImportAllTest(import_all.TestCase):
        pass

You can customize how warnings are treated here.

`all_test.py <https://raw.githubusercontent.com/rec/import_all/master/all_test.py/>`_.

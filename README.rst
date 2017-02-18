chimera-qc plugin
=================

Simple quality control checker plugin for https://github.com/astroufsc/chimera. Runs SEXtractor on OBJECT images and
calculate statistics on them.


Installation
------------

Installation instructions. Dependencies, etc...

::

    pip install -U git+https://github.com/astroufsc/chimera-qc.git


Configuration Example
---------------------

Here goes an example of the configuration to be added on ``chimera.config`` file.

::

    controllers:

      - type: QualityControl
        name: qc
        camera: /Camera/0
        sex_params: ~/.chimera/sextractor.json


Contact
-------

For more information, contact us on chimera's discussion list:
https://groups.google.com/forum/#!forum/chimera-discuss

Bug reports and patches are welcome and can be sent over our GitHub page:
https://github.com/astroufsc/chimera-qc/

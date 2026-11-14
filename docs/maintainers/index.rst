Maintainers
===========

Use this section for project-maintenance procedures. Keep work scoped to the
requested task. Commits, releases, publishing and repository-setting changes
each require explicit maintainer authorization.

* :doc:`documentation`: build, check and publish these docs, and add branding assets.
* :doc:`installed-wheel-qualification`: verify an installed candidate and run the opt-in read-only checks.
* :doc:`pat-rotation-qualification`: separately qualify one deliberate test PAT rotation.

For contributor guidance, see the repository's
`CONTRIBUTING.md <https://github.com/jeffshurtliff/sfdctrust/blob/main/CONTRIBUTING.md>`_
and ``AGENTS.md`` files. For release
history, see the :doc:`../CHANGELOG`.

.. toctree::
   :maxdepth: 1
   :hidden:

   documentation
   ci-and-publishing
   ci-publishing-evidence
   compatibility-qualification
   sqlite-pat-store
   sqlite-pat-recovery-evidence
   installed-wheel-qualification
   pat-rotation-qualification

"""CreatorIQX worker package.

Deliberately thin: it exists so the worker is a separately deployable unit
(spec §13 repo layout) without duplicating any job code. The real Celery app
and task definitions live in ``creatoriqx_api.modules.jobs.infrastructure``
(ADR 0003) - see this package's README for the run command.
"""

__version__ = "0.1.0"

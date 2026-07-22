# SPDX-License-Identifier: Apache-2.0
"""Version planes.

These are three independent numbers and conflating them causes real damage:

``LIB_VERSION``
    SemVer of this library. Bumps freely.

``FORMAT_VERSION``
    The on-disk / hash contract. Every recipe blob in every store on every
    machine records the FORMAT_VERSION it was written under. Bumping this is the
    most expensive event in the project: it requires a migration in
    ``migrate/`` and a regeneration of ``tests/contract/hashes.json``. It should
    bump almost never.

``HASH_ALGO_PREFIX``
    Namespaces the hash so a future algorithm change is detectable rather than
    silently ambiguous. Stored as part of every hash string.
"""

LIB_VERSION = "0.1.0"

FORMAT_VERSION = 1

HASH_ALGO_PREFIX = "sc1"

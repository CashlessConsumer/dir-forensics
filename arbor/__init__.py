"""dir-forensics — metadata-only directory forensics.

Generic analysis pipeline for directory listings (leak dumps, bucket indexes,
local trees, web directory listings). Input: a canonical inventory JSON
({depth, dirs[], files{relpath: meta}, stats}). Output: tree, depth, extension,
duplicate, security-flag and tier-0 dedup artifacts — all driven by a case
config, never by file contents.
"""

__version__ = "0.1.0"

# Offline strategy (sketch)

Not designed in detail. Recorded so the API does not accidentally foreclose it.

## The shape

Content addressing makes offline sync unusually tractable: versions are
immutable and identified by hash, so a cached version is *never* stale — it is
either the one you want or it is not.

1. Mirror the store locally: version records keyed by `version_id`
2. Sync is "which refs moved?", not "what changed?" — compare HEAD hashes
3. An immutable version, once fetched, needs no revalidation ever

## What is hard

**Offline authoring.** Editing offline creates a version whose parent is the
last one seen, which is a fork if the server has moved on. That is exactly the
merge problem deferred in the roadmap, so v1 of the mobile client should be
**read-only offline, write online**.

## What the API must not foreclose

- `GET /recipes/{slug}/versions/{hash}` must return the exact canonical bytes,
  so the client can verify the hash itself rather than trusting the transport
- Listing endpoints should expose HEAD hashes so a client can diff cheaply
- Nothing may assume the client holds the *latest* version

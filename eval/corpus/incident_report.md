# Incident report — search outage, 12 February 2026

## Summary

Search returned no results for **47 minutes**, between 14:03 and 14:50 UTC. Approximately
**2,300 users** were affected. No data was lost.

## Cause

A migration added a column to the `documents` table and rebuilt the index. The rebuild acquired
an exclusive lock that the search query could not read through. The migration had been tested
against a 10,000 row table, where the rebuild took under a second; production holds 4.1 million
rows, where it took 47 minutes.

## Detection

The on-call engineer was paged at 14:11, eight minutes after the outage began. Detection was slow
because the health check queried a table that was not locked.

## Resolution

The migration was allowed to complete rather than being cancelled, because cancelling would have
left the index in an inconsistent state requiring a longer rebuild.

## Actions

1. Health checks must exercise the same query path as user traffic. Owner: Priya. Due 28 February.
2. Index rebuilds move to `CREATE INDEX CONCURRENTLY`. Owner: Marcus. Due 20 February.
3. Migrations are tested against a production-sized copy before release. Owner: Priya. Due
   15 March.

## What went well

The decision not to cancel the migration was correct and was made within four minutes of the page.

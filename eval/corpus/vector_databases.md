# Vector database evaluation — internal note

## pgvector

pgvector is a PostgreSQL extension that stores embeddings alongside relational data. It supports
two index types: IVFFlat and HNSW. On our benchmark of 1.2 million chunks, HNSW returned in
**14 milliseconds** at 96% recall, while IVFFlat returned in 31 milliseconds at 91% recall.

pgvector requires no separate service. Our operations team scored it **9 out of 10** for
maintenance burden, the highest of the three we tested.

The maximum dimension pgvector supports for an indexed column is **2000**.

## Qdrant

Qdrant is a purpose-built vector database written in Rust. On the same benchmark it returned in
**9 milliseconds** at 98% recall — the fastest we measured.

It runs as a separate service, which our operations team scored **5 out of 10** for maintenance
burden. It requires roughly 6 GB of RAM for our corpus size.

Qdrant supports filtering on payload fields during search, which pgvector achieves only through
a WHERE clause that can defeat the index.

## Weaviate

Weaviate returned in **19 milliseconds** at 94% recall. Its distinguishing feature is built-in
module support for generating embeddings at write time, removing a step from the ingestion
pipeline.

Operations scored it **6 out of 10**. It requires the most configuration of the three.

## Decision

We selected **pgvector**, accepting a 5 millisecond latency penalty in exchange for having no
additional service to operate. The decision was made on 3 March 2026 and will be revisited when
the corpus exceeds 10 million chunks.

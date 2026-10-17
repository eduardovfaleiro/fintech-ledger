# Benchmark methodology

The repository uses two kinds of evidence. Cases 1–5 compare execution plans collected with `EXPLAIN (ANALYZE, BUFFERS)`. Cases 6–8 also measure latency distributions from the client, because one isolated execution would hide variance and, in the concurrent case, lock contention.

## Measurement protocol

- Latency is measured with Python's monotonic `perf_counter_ns`, around the complete database call and result fetch.
- Warm-up executions are discarded before measurement.
- No sample is removed as an outlier.
- Results report the arithmetic mean, minimum, maximum and the p50, p95 and p99 percentiles.
- Percentiles use linear interpolation between adjacent ordered samples.
- Raw samples, execution plans, parameters and environment metadata are stored in [`results/`](results/).
- The N+1 benchmark alternates the order of the two approaches on every execution to reduce ordering bias.
- The scale benchmark runs each scenario 30 times against a disposable `UNLOGGED` table.
- The concurrency benchmark uses one database connection per worker and verifies that every job is claimed exactly once.

## Reference environment

The published results were collected locally with PostgreSQL 18.4 in Docker, Python 3.12, an AMD Ryzen 5 7530U (6 cores/12 threads), 32 GB of RAM and NVMe storage. PostgreSQL used 128 MB of `shared_buffers`, 4 GB of `effective_cache_size`, 4 MB of `work_mem` and up to two parallel workers per gather.

## Reproduction and limitations

Run the benchmarks with:

```bash
make benchmark-n-plus-one
make benchmark-scale
make benchmark-skip-locked
```

The measurements use a warm cache and a local client, so absolute latency will vary on other machines. The scale test repeats the original 10-million-row data set to reach 50 million rows. The concurrency test deliberately keeps each batch transaction open for 5 ms to make queue-head contention observable. The useful comparison is between approaches measured in the same environment, not the absolute time as a production capacity claim.

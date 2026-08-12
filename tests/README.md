# Tests

- `fixtures/` holds **real, trimmed** job records captured from the legacy system.
  Use them to test filters, dedup, cache, and the AI layer **without live calls**.
- Tests must never hit a live AI provider or a live website. Mock the network.
- Run: `pytest`

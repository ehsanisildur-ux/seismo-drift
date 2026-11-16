# SeismoDrift

SeismoDrift keeps an append-only, daily signal for a bounded region using the USGS earthquake catalog. Each transaction seals the next UTC day, saves the observations that drove the calculation, and updates a cumulative score and opening or clearing state.

Deploy with `sd1:` followed by JSON containing `start` (YYYY-MM-DD), integer `west`, `east`, `south`, and `north` (at most four degrees per axis), and integer `allowance`, `trigger`, and `clear`. The allowance is 1–63, and the limits satisfy 0 ≤ clear < trigger ≤ 1024. The box cannot cross the antimeridian. The caller cannot change the configuration after deployment.

Anyone can call `advance(expected_day)` at least two complete UTC days after that day closes. The leader and validators independently retrieve the configured day from USGS. They normalize the actual earthquake IDs, times, coordinates, and magnitudes, check the filters locally, and compare the complete normalized observation used by the contract. Source timestamp and feature order can vary. A mismatch in any retained event is material, including when the two counts match. An unverified day can be retried.

The query counts magnitude 4.5 and greater earthquakes in the configured box. The contract uses half-open UTC days and caps the daily input at 64. At the cap, the stored events establish a lower bound. The score is `max(0, previous_score + count - allowance)`. It opens at or above `trigger` and clears at or below `clear`. The signal describes counts observed in the catalog at recording time. Its thresholds are application parameters and do not estimate earthquake probabilities or provide emergency warnings. Later catalog revisions do not rewrite sealed days.

`get_state()` returns the configuration, next day, score, and signal state. `get_day(day)` returns the normalized evidence, query URL, observation digest, and before-and-after state, or an empty object for an unsealed day.

[USGS FDSN event query](https://earthquake.usgs.gov/fdsnws/event/1/) · [NIST CUSUM reference](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm)

## Verification

```sh
pip install -r requirements-dev.txt
genvm-lint download --version v0.2.16
genvm-lint check contracts/seismo_drift.py
python -m pytest tests/direct -q
npm ci
node --test tests/rpc-preflight.test.cjs
```

The hosted proof separately fetches the July 3–5, 2019 USGS catalog data for a box around Ridgecrest. It verifies each onchain event and independently calculates scores as maximum suffix sums. Direct tests also exercise clearing, the cap, the settlement lag, and inconsistent or unavailable evidence. Fixtures preserve the public catalog responses used by the direct tests. Generic CLI receipt transport is reused under MIT.

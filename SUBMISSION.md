# SeismoDrift — Consensus earthquake catalog monitor

**Category** Builder → Intelligent Contracts

SeismoDrift maintains a sequential cumulative signal from the USGS earthquake catalog. For each eligible UTC day, the leader and validators independently fetch event records and require exact agreement on normalized IDs, times, coordinates and magnitudes. The verified count drives a capped daily input and a cumulative score with separate opening and clearing thresholds. Each sealed day stores its source, events and before-and-after state. StudioNet verified the July 3–5, 2019 Ridgecrest window. Counts of 0, 4 and 1 produced scores of 0, 2 and 1, opening the signal at the threshold and holding it below that threshold. Skip and replay calls reverted. All six receipts finalized with MAJORITY_AGREE. The signal describes catalog observations using configured thresholds.

- [GenLayer contract](contracts/seismo_drift.py)
- [StudioNet deployment](https://explorer-studio.genlayer.com/tx/0x11b230c79aac3d33bbaf04e3bb84f6cc2bd71bb50f96a6a8d88a489f595de959)
- [Signal opening transaction](https://explorer-studio.genlayer.com/tx/0xdd7c49960b1f3004cd98c9ba99b0ac67a5cdc029ba82816c885bd8a8fc96d876)
- [Receipts and verified state](proofs/README.md)

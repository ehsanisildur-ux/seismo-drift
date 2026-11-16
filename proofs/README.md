# StudioNet proofs

Contract address 0xD9A1346E5c151126773E89f6e77BAB8f0C31fF9B

The run fetched the July 3–5, 2019 data directly from USGS, verified every retained event against the onchain records, and recomputed the score using maximum suffix sums. Two wallets exercised permissionless advancement.

[Workflow](https://github.com/ehsanisildur-ux/seismo-drift/actions/runs/43938055385) · [Verified state and events](verified.json)

| Outcome | Explorer | Receipt | Agree / disagree / idle |
| --- | --- | --- | --- |
| Deployed the monitor with no sealed days | [Transaction](https://explorer-studio.genlayer.com/tx/0x11b230c79aac3d33bbaf04e3bb84f6cc2bd71bb50f96a6a8d88a489f595de959) | [JSON](deploy-receipt.json) | 4 / 0 / 1 |
| Rejected a skipped UTC day | [Transaction](https://explorer-studio.genlayer.com/tx/0xb380693f068a92dd3ae95d54885a31bf9544db3e77e47ee3290cd24e43fe0dd2) | [JSON](reject-skip-receipt.json) | 3 / 0 / 2 |
| July 3 recorded zero events and kept the signal inactive | [Transaction](https://explorer-studio.genlayer.com/tx/0xf1032b9875adc45643b4eced446b8be76eeb312b9129056616755997f6232a4c) | [JSON](quiet-receipt.json) | 3 / 0 / 2 |
| July 4 recorded four events and opened at score 2 | [Transaction](https://explorer-studio.genlayer.com/tx/0xdd7c49960b1f3004cd98c9ba99b0ac67a5cdc029ba82816c885bd8a8fc96d876) | [JSON](open-receipt.json) | 3 / 0 / 2 |
| July 5 recorded one event and held the signal at score 1 | [Transaction](https://explorer-studio.genlayer.com/tx/0xbae279f0e68c5784d7148cb89ee627bf9f11935c798f9b21946a1480855d1d13) | [JSON](hold-receipt.json) | 3 / 0 / 2 |
| Rejected resealing July 4 | [Transaction](https://explorer-studio.genlayer.com/tx/0x5fd5f90b68bb98ff622e347b7d4ba46f572c7cb0b3536585ed5b72c806b0db21) | [JSON](reject-replay-receipt.json) | 3 / 0 / 2 |

All six receipts finalized with MAJORITY_AGREE. The skipped and repeated calls reverted without a state update.

The example uses an allowance of 2, an opening score of 2, and a clearing score of 0. The July 5 score is below the opening threshold but above the clearing threshold.

Source revision 090f8653b624ff7c8bd7cf848d5221e8112412f3

Contract SHA-256 213ea89c6d5fb94082130d75c45cf87b8a8e7f79c53ccc483983b9e4596761f0

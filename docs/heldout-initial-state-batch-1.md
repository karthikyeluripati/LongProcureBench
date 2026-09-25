# Held-out initial-state batch 1

This batch adds five **real public electrical procurement starting states** for
the future held-out paper evaluation slice. It deliberately does **not** author
their synthetic long-horizon episodes yet.

## Why states now, episodes later

The current 20 episodes were used to build and debug the runtime, inspect model
trajectories, audit checkpoint fairness, and design Evaluator v0.2. They are
development/calibration data.

For the held-out slice, the cleaner procedure is:

1. collect and freeze real public starting states;
2. design and freeze stronger agent architectures using episodes 001–020 only;
3. only then author the held-out synthetic event/oracle layer against the frozen
   episode ontology and evaluator;
4. run final evaluation without architecture or evaluator tuning on those
   held-out results.

This keeps the held-out procurement sources independent from the stronger-agent
design while still using the same schema and evaluator machinery.

## Batch 1 sources

| Package | Buyer/source | Equipment | Useful public constraints |
| --- | --- | --- | --- |
| us-port-angeles-mec-2025-18 | City of Port Angeles | Six pad-mounted transformer bid items | quantities, voltages, USD 800k estimate, Buy American / transformer standards |
| us-eweb-rfp-25-030-g | Eugene Water & Electric Board / OregonBuys | 21/28/38 MVA GSU transformer | quantity, major transformer attributes, bid timing |
| us-lompoc-rfq-3099 | City of Lompoc | Electric transformers | public RFQ identity and dates; detailed attachment remains unavailable in the reviewed index |
| us-columbus-rfq029445 | City of Columbus | Medium-voltage pad-mounted distribution switchgear | approved-equal rule and bidder experience requirements |
| us-njang-w50s8f26qa022 | 177th Fighter Wing / SAM.gov | 200 kW generator + ATS | quantity, small-business set-aside, bid timing |

Unknown public facts remain null and are explicitly recorded in
`missing_information`. No supplier response, offered price, negotiation, award,
or later outcome is included.

## Status

- Held-out target: 10 starting states
- Batch 1 collected: 5
- Held-out synthetic episodes authored: 0

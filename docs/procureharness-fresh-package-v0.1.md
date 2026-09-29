# ProcureHarness fresh package 031–050 v0.1

This package creates the fresh real-public procurement slice preregistered by the
ProcureHarness architecture-search protocol.

## Split

- **031–040**: architecture-search validation. These episodes may become exposed
  only after this package is frozen.
- **041–050**: final method test. These episodes remain untouched by model-backed
  ProcureHarness architecture search until the winning architecture is frozen.
- Episodes **021–030 remain diagnostic-only** for methods designed after their
  prior exposure.

No model/provider calls are executed by this PR.

## Grounding boundary

Each starting state is reconstructed only from the cited official public buyer
notice. Supplier identities, quotes, messages, qualification states, and event
timing in the episode layer are synthetic controlled benchmark facts. Unknown
public fields remain null with explicit missing-information records.

## Fresh packages

| ID | Episode | Package | Buyer | Public procurement |
| ---: | --- | --- | --- | --- |
| 031 | `electrical-imperial-ev-phase1-031` | `us-imperial-ca-ev-phase1-2026-09` | City of Imperial | EV Charging Station Installation, Phase I – CRPL-5134(030) |
| 032 | `electrical-imperial-ev-phase23-032` | `us-imperial-ca-ev-phase23-2026-06` | City of Imperial | EV Charging Station Installation, Phase II & Phase III – CRPL-5134(033) |
| 033 | `electrical-lewiston-ev-chargers-033` | `us-lewiston-me-ev-chargers-2026-008` | City of Lewiston, Maine | 2026-008 Installation of EV Charging Stations |
| 034 | `electrical-idaho-falls-ev-chargers-034` | `us-idaho-falls-ev-build-ifp-26-07` | City of Idaho Falls | EV Charging Stations Build |
| 035 | `electrical-union-township-ev-chargers-035` | `us-union-township-oh-ev-pid122828` | Union Township, Clermont County, Ohio | Union Township EV Chargers Project / PID #122828 |
| 036 | `electrical-methuen-stadium-led-036` | `us-methuen-ma-mhs-led-lighting-2026` | City of Methuen | LED Light, electrical panels, and new electrical service installation - MHS Stadium lower turf field |
| 037 | `electrical-philadelphia-led-phase5-037` | `us-philadelphia-led-6711r-b2626934` | City of Philadelphia, Department of Aviation | PHL-1983.35 LED Lighting Upgrades, Phase 5 |
| 038 | `electrical-hampton-fountain-led-038` | `us-hampton-va-fountain-led-rfp27-14tm` | City of Hampton | RFP 27-14TM Fountain Repairs |
| 039 | `electrical-danville-pole-transformer-039` | `us-danville-va-pole-transformer-qb25-26-075` | City of Danville, Virginia | QB 25-26-075 Single Phase Pole Mount Transformer |
| 040 | `electrical-danville-substation-transformers-040` | `us-danville-va-substation-transformers-qb25-26-085` | City of Danville, Virginia | QB 25-26-085 67 to 12.47/7.2 kV Substation Power Transformers |
| 041 | `electrical-danvers-transformers-041` | `us-danvers-ma-transformers-2026-31` | Town of Danvers | Purchase of Pole-Mount and Pad-Mount Transformers |
| 042 | `electrical-rocky-mount-transformer-upgrade-042` | `us-rocky-mount-nc-substation10-transformer-320-040226fd` | City of Rocky Mount | Substation 10 Transformer Upgrade |
| 043 | `electrical-rocky-mount-breakers-043` | `us-rocky-mount-nc-69kv-breakers-320-010926fd` | City of Rocky Mount | 69kV Circuit Breakers for the North POD Substation |
| 044 | `electrical-siloam-circuit-switchers-044` | `us-siloam-springs-ar-69kv-circuit-switchers-2026` | City of Siloam Springs Electric Department | Bid - Substation 69KV Circuit Switchers |
| 045 | `electrical-eweb-mcc-vfd-plc-045` | `us-eweb-mcc-vfd-plc-rfp26-057-gs` | Eugene Water & Electric Board | EWEB RFP 26-057-GS MCC with Integrated VFD, and PLC Build for City View 1150 Pump Station |
| 046 | `electrical-odot-alkali-generator-046` | `us-odot-alkali-lake-generator-00016455` | Oregon Department of Transportation | Alkali Lake MS - Replace Main Shop Backup Generator Project |
| 047 | `electrical-portland-tx-generator-047` | `us-portland-tx-generator-rfb6631` | City of Portland, Texas | Installation of Emergency Backup Generator and Automatic Transfer Switch (ATS) |
| 048 | `electrical-marshfield-generator-048` | `us-marshfield-mo-generator-10-15-2025` | City of Marshfield, Missouri | Request for Proposal for 26 kW Generator |
| 049 | `electrical-dubuque-generator-049` | `us-dubuque-county-generator-08042025-it016` | Dubuque County, Iowa | RFP - (1) Generator and (1) Transfer Switch |
| 050 | `electrical-philadelphia-substation-switchgear-050` | `us-philadelphia-substation-switchgear-b2625884` | City of Philadelphia, Department of Aviation | PHL-1690.25 Substation BBC-EBBC Switchgear Replacement |

## Mechanism rotation

The 20 episodes rotate four frozen, already-supported mechanisms:

1. requirement clarification + supplier non-response/follow-up;
2. supplier question + compliant quote revision;
3. midstream requirement change + full quote refresh;
4. supplier withdrawal + eligibility/delivery recovery.

This changes only benchmark data. It introduces no new action, event, evaluator,
or controller semantics.

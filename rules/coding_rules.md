# 2. Failure-mode categories and coding rules

*Version 1.2, October 2026 (v1.1 used for the main 300-report run). Reviewed against a reference design-stage FMEA (see the catheter-pms-ai repository) and a 20-report pilot.*

Each report is coded on six fields. The AI and the human reviewer use exactly the same
definitions, so their results can be compared in the validation step.

| Field | What it records |
|---|---|
| A. Primary failure mode | The one category that best describes what went wrong (table below) |
| B. Secondary failure mode | Optional second category, when a report clearly describes two (e.g. kink leading to occlusion) |
| C. Phase of use | When it happened |
| D. Harm severity | How badly the patient was affected, on a 5-level ISO 14971-style scale |
| E. Likely contributor | Device, use, patient, or unclear |
| F. Retained fragment | Yes / No: was any part of the device left in the patient? |
| G. User harm | Yes / No: was a user (nurse, doctor, carer) exposed to harm, e.g. blood splash or needlestick? |
| H. Complaint group | Links reports that describe the same complaint (e.g. one complaint, five devices, five reports) so it is counted once in trends |

Every coded report also gets a **confidence level** (high, medium, low) and a **supporting quote**
copied from the report text.

---

## A. Failure-mode categories

### Device integrity

| Code | Category | Include | Exclude | Example report |
|---|---|---|---|---|
| FM01 | **Catheter body break, fracture or separation** | Snap, break, tear, hole, rupture or crack anywhere in the catheter tube itself, **inside or outside the body**, including the tip and the joint where the tube meets the hub; catheter separating into pieces | Cracks or leaks at the hub, extension leg, clamp or connector (FM02) | 3006260740-2022-06006 (PICC ruptured at 9.5 cm) |
| FM02 | **External component failure** (hub, extension leg, clamp, connector, valve, septum, suture wing) | Leak, crack, break or detachment of these parts, including the rubber septum or stopper that holds a stylet or guidewire | Breach of the indwelling shaft (FM01) | 0001625425-2023-00919 (crack at base where extension joins); 3006260740-2022-05998 (leak at suture wing and hub) |
| FM03 | **Occlusion or failure to infuse / aspirate** | Cannot flush, infuse or draw blood; occlusion of any cause | A visible kink is the cause (code FM04 primary, FM03 secondary) | 2518902-2023-00001 (did not aspirate, infused with resistance) |
| FM04 | **Kink, deformation or ballooning** | Material deformation without a breach: kink, ballooning, accordioning, flattening | Deformation that ends in a breach (FM01 or FM02) | 3006260740-2022-05954 (catheter ballooned inside patient) |
| FM05 | **Insertion accessory failure** | Problems with guidewire, introducer, sheath, needle or stylet, including retained or knotted guidewires | Problems with the catheter itself during insertion (FM01-FM04) | 3006260740-2022-05963 (micro-introducer sheath folded back) |
| FM06 | **Tip malposition or migration** | Tip in the wrong place, catheter moved in or out after placement | Catheter pulled out by the patient with no device fault (FM12, contributor = use or patient) | 3006260740-2023-00603 (catheter migrated out after 5 months) |
| FM07 | **Difficult insertion or removal, no defect found** | Resistance, inability to advance or remove, where no device defect is described | Removal that ends in breakage (FM01) | to be added |
| FM08 | **Packaging, labelling or assembly defect found before use** | Foreign material in pack, damaged sterile barrier, wrong or missing labelling, missing or unattached component (e.g. cuff not attached) found out of the box | Infection in the patient (FM09); a part that fails during use (FM01/FM02) | 3006260740-2022-05976 (hair-like material in package) |

### Clinical complications

Use these when the report describes a patient complication **without** a device failure from
FM01-FM08. If a device failure is also described, code the device failure as primary and the
complication as secondary.

| Code | Category | Include | Example report |
|---|---|---|---|
| FM09 | **Infection** | Site infection, line infection, bloodstream infection, sepsis, fever attributed to the line | 3006260740-2022-06023 |
| FM10 | **Thrombosis or thrombophlebitis** | DVT, catheter-related thrombus, phlebitis | 3006260740-2023-00058 |
| FM11 | **Vessel or cardiac injury, extravasation** | Vessel perforation, cardiac tamponade, arrhythmia from tip position, infusate leaking into tissue | 3006260740-2022-05980 (vessel perforation, chest pain) |
| FM12 | **Other or insufficient information** | Anything that fits no category above, or reports too vague to code | |
| FM13 | **Local tissue or hypersensitivity reaction** | Redness, swelling, rash, itching, inflammation or allergic reaction at or around the site, without confirmed infection | 3006260740-2022-06059 (redness or swelling at insertion site) |

FM13 was added in v1.0 because the reference FMEA includes "line rejected by the body
(poor biocompatibility)", which no v0.1 category covered.

### Priority rules when a report fits more than one category

1. A **breach** of the device (FM01, FM02) beats deformation (FM04) and occlusion (FM03).
2. A **device failure** (FM01-FM08) beats a clinical complication (FM09-FM11).
3. A **cause** beats an effect: kink causing occlusion = FM04 primary, FM03 secondary.
4. If two categories are equally supported, pick the one that came first in time and record the other as secondary.
5. **Leak at the insertion site with no visible breach:** code FM01 with confidence "low", because a breach of the tube under the skin is the most likely source. If the report names another source (e.g. hub), use that.
6. **Leak with no location given:** code FM12 with confidence "low", not FM01 or FM02.

---

## C. Phase of use

| Code | Phase |
|---|---|
| P1 | Before use (out of the box, preparation, priming) |
| P2 | Insertion |
| P3 | In use / dwell (infusion, flushing, dressing changes, maintenance) |
| P4 | Removal |
| P5 | Unknown |

## D. Harm severity

5-level scale, the same number of levels as the reference FMEA (S1-S5). The reference FMEA did
not define its levels in words, so the definitions below are used for coding.

| Level | Name | Definition | Typical example |
|---|---|---|---|
| S1 | Negligible | No injury; inconvenience or delay only | Leak noticed out of the box; replaced before use |
| S2 | Minor | Temporary harm, no intervention beyond routine care | Line removed and not replaced; line repaired or trimmed; treatment briefly delayed |
| S3 | Serious | Medical intervention needed | Antibiotics for infection, anticoagulation, **any unplanned replacement of the central line** (new line inserted, over-the-wire exchange), extravasation needing treatment |
| S4 | Critical | Life-threatening, permanent harm, or invasive retrieval | Fragment retrieved in cath lab, cardiac tamponade |
| S5 | Catastrophic | Death | |

Severity describes harm to the **patient only**; harm to users is recorded in field G.
If the report says there was no patient involvement or no injury, use S1. If harm is not
described at all, use S1 and set confidence to low.

## E. Likely contributor

| Code | Meaning |
|---|---|
| DEV | Report describes a device defect (e.g. crack found on inspection) |
| USE | Report describes a use error or deviation (e.g. forced flush with small syringe, cut catheter) |
| PAT | Patient factors (e.g. patient pulled the line out, anatomy) |
| UNK | Not enough information |

This is a **suggestion from the report text only**, not a root-cause conclusion. Manufacturer
investigation results in the narrative can be used if present.

## F. Retained fragment

Yes if any part of the catheter, guidewire or other accessory was left in the patient, even
if later retrieved. This is tracked separately because it is the highest-severity hazardous
situation for this device type.

---

## G. User harm

ISO 14971 covers harm to users as well as patients. Mark "Yes" when the report describes a
user being exposed to blood or body fluid, a sharps injury, or another injury. The severity
field (D) still refers to the patient.

## H. Complaint group

When the report says the same complaint covers several devices or patients, or the text is
identical to another report, give all of them the same group ID (the first report number).
Trend counts use one count per group.

## Mapping to ISO 14971 terms (for the FMEA comparison in step 6)

| Category | Hazard | Example hazardous situation | Possible harm |
|---|---|---|---|
| FM01 | Mechanical failure of catheter shaft | Fragment released into circulation | Embolism, cardiac injury, invasive retrieval |
| FM02 | Mechanical failure of external parts | Open fluid path outside the body | Blood loss, air embolism, infection, therapy interruption |
| FM03 | Loss of fluid path | Therapy cannot be delivered | Delayed treatment, line replacement |
| FM04 | Mechanical deformation | Restricted flow or stress concentration | Occlusion, later breakage |
| FM05 | Accessory failure | Wire or sheath fragment in vessel | Embolism, invasive retrieval |
| FM06 | Incorrect tip position | Infusion into wrong vessel or cardiac chamber | Thrombosis, arrhythmia, extravasation |
| FM08 | Contamination or assembly defect | Non-sterile or incomplete device reaches use | Infection, therapy delay |
| FM09 | Biological (microbial) | Colonised line in bloodstream | Bloodstream infection, sepsis |
| FM10 | Biological (thrombogenic) | Thrombus forms on catheter | DVT, pulmonary embolism |
| FM11 | Mechanical/energy | Vessel wall breached | Tamponade, extravasation injury |
| FM13 | Biological (biocompatibility) | Tissue reacts to material | Inflammation, hypersensitivity |

## Link to the reference FMEA

| Category | Reference FMEA row | FMEA severity (S) |
|---|---|---|
| FM01 Catheter body break | 2. Line breaks | 5 |
| FM02 External component failure | 5. Cap or clamp fails; 8. Foreign liquid enters line | 4 |
| FM03 Occlusion | 7. Resistance when drawing or infusing | 3 |
| FM04 Kink / deformation | none | |
| FM05 Insertion accessory failure | none | |
| FM06 Malposition / migration | none | |
| FM07 Difficult insertion / removal | none | |
| FM08 Packaging / assembly before use | 1. Not sterile; 4. Device re-used | 5 |
| FM09 Infection | consequence of rows 1, 4, 8 | 5 |
| FM10 Thrombosis | 6. Thrombosis | 3 |
| FM11 Vessel / cardiac injury | none | |
| FM13 Tissue reaction | 3. Line rejected by the body | 5 |

Categories with no FMEA row are candidate gaps, to be tested against the data in step 6.

## Change history

| Version | Change |
|---|---|
| 1.0 | Reviewed against reference FMEA; FM13 added; midlines excluded |
| 1.2 | After validation: unplanned replacement of the central line = S3; repair, trim or removal without replacement = S2; severity is patient-only; the model receives the full manufacturer narrative |
| 1.1 | After 20-report pilot: FM01 covers the whole tube inside or outside the body; FM02 includes septa/stoppers; FM08 widened to assembly defects before use; rules 5-6 for leaks; new fields G (user harm) and H (complaint group) |

## Scope decisions

- **Midline catheters excluded.** Midlines end in a peripheral vein, so their hazards differ from central lines (e.g. no tamponade or central fragment embolism). Reports mentioning a midline are kept in the raw data but excluded from analysis.
- **Severity scale:** 5 levels confirmed.

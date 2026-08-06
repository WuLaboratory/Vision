# Phase 3 live-camera results

**Total trials:** 295
**Overall accuracy:** 213/295 (72.2%)
**QC accuracy (arc < 100.0):** 182/210 (86.67%)
**Misclassified with arc > 100.0:** 65.9% of failures

## Per plot (all trials | QC-pass)

| Plot | N (all) | Acc all | N (QC) | Acc QC |
|------|---------|---------|--------|--------|
| line1 | 15 | 60.0% | 5 | 0.0% |
| line2 | 24 | 58.33% | 13 | 23.08% |
| line3 | 15 | 93.33% | 6 | 83.33% |
| quadratic1 | 54 | 81.48% | 44 | 100.0% |
| quadratic2 | 63 | 87.3% | 55 | 100.0% |
| sinusoid1 | 23 | 60.87% | 13 | 100.0% |
| sinusoid2 | 35 | 71.43% | 25 | 96.0% |
| sinusoid3 | 66 | 57.58% | 49 | 77.55% |

## Confusion (misclassified)

- SINUSOID → LINE: 31
- QUADRATIC → LINE: 18
- LINE → QUADRATIC: 17
- SINUSOID → QUADRATIC: 16

## Figures

- `figures/phase3_accuracy_vs_arc.png`
- `figures/phase3_per_plot_raw_vs_qc.png`
- `figures/phase3_confusion_matrix.png`

# WebPlotDigitizer baseline

**Classification:** 7/8 correct by penalized model selection

| File | N pts | Cal OK | Detected | GT | m err% | Notes |
|------|-------|--------|----------|-----|--------|-------|
| line1.jpg | 10 | yes | LINE | LINE | 0.100722 |  |
| line2.jpg | 10 | yes | QUADRATIC | LINE | 0.321861 |  |
| line3.jpg | 10 | yes | LINE | LINE | 0.595433 |  |
| quadratic1.jpg | 11 | yes | QUADRATIC | QUADRATIC | — |  |
| quadratic2.jpg | 10 | yes | QUADRATIC | QUADRATIC | — |  |
| sinusoid1.jpg | 10 | no | SINUSOID | SINUSOID | — | y_obs=[0.016,6.5] vs GT y=[-2,2] |
| sinusoid2.jpg | 12 | yes | SINUSOID | SINUSOID | — |  |
| sinusoid3.jpg | 10 | yes | SINUSOID | SINUSOID | — |  |

Mean line slope error (WPD): 0.339%

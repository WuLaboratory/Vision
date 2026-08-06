# Validation Results — Static JPEG Analysis

**Images analyzed:** 15  
**Classification correct:** 15/15 (100%)

Pipeline: `find_largest_quad` → `warp_plot` → `analyze_shape` (same as camera app).

## Results table

| File | True class | Detected | OK | Best equation | RMSE | R² |
|------|------------|----------|-----|---------------|------|-----|
| line1.jpg | LINE | LINE | yes | y = 9.972 x + 1.016 | 0.04514 | 1.000 |
| line2.jpg | LINE | LINE | yes | y = 4.985 x + 1.507 | 0.02511 | 1.000 |
| line3.jpg | LINE | LINE | yes | y = 2.003 x + 2.998 | 0.01761 | 0.999 |
| sinusoid1.jpg | SINUSOID | SINUSOID | yes | y = 1.822 sin(5.819 x + -0.5112) + 0.00031 | 0.04688 | 0.998 |
| sinusoid2.jpg | SINUSOID | SINUSOID | yes | y = 2.711 sin(10.46 x + 1.139) + 0.004437 | 0.07934 | 0.998 |
| sinusoid3.jpg | SINUSOID | SINUSOID | yes | y = 2.112 sin(3.222 x + 0.6436) + 0.2029 | 0.02542 | 0.999 |
| quadratic1.jpg | QUADRATIC | QUADRATIC | yes | y = 0.9974 x^2 + 1.994 x + 3.006 | 0.01251 | 1.000 |
| quadratic2.jpg | QUADRATIC | QUADRATIC | yes | y = 4.989 x^2 + 7.98 x + 13.02 | 0.05727 | 1.000 |
| line1a.jpg | LINE | LINE | yes | y = 9.972 x + 1.016 | 0.04514 | 1.000 |
| line3a.jpg | LINE | LINE | yes | y = 2.003 x + 2.998 | 0.01761 | 0.999 |
| sinusoid1a.jpg | SINUSOID | SINUSOID | yes | y = 1.822 sin(5.819 x + -0.5112) + 0.00031 | 0.04688 | 0.998 |
| sinusoid2a.jpg | SINUSOID | SINUSOID | yes | y = 2.711 sin(10.46 x + 1.139) + 0.004437 | 0.07934 | 0.998 |
| sinusoid3a.jpg | SINUSOID | SINUSOID | yes | y = 2.112 sin(3.222 x + 0.6436) + 0.2029 | 0.02542 | 0.999 |
| quadratic1a.jpg | QUADRATIC | QUADRATIC | yes | y = 0.9974 x^2 + 1.994 x + 3.006 | 0.01251 | 1.000 |
| quadratic2a.jpg | QUADRATIC | QUADRATIC | yes | y = 4.989 x^2 + 7.98 x + 13.02 | 0.05727 | 1.000 |

## Parameter errors vs. MATLAB ground truth (`linear.m`)

- **line1.jpg:** m_pct=0.2756, b_abs=0.01638
- **line2.jpg:** m_pct=0.2921, b_abs=0.007162
- **line3.jpg:** m_pct=0.1489, b_abs=0.002175
- **sinusoid1.jpg:** A_pct=8.878, omega_pct=16.38, phi_rad=0.5112
- **sinusoid2.jpg:** A_pct=9.648, omega_pct=16.17, phi_rad=1.144
- **sinusoid3.jpg:** A_pct=8.177, omega_pct=7.409, phi_rad=0.0732
- **quadratic1.jpg:** a_pct=0.2617, b_pct=0.2884, c_pct=0.1953
- **quadratic2.jpg:** a_pct=0.2169, b_pct=0.2486, c_pct=0.1591
- **line1a.jpg:** m_pct=0.2756, b_abs=0.01638
- **line3a.jpg:** m_pct=0.1489, b_abs=0.002175
- **sinusoid1a.jpg:** A_pct=8.878, omega_pct=16.38, phi_rad=0.5112
- **sinusoid2a.jpg:** A_pct=9.648, omega_pct=16.17, phi_rad=1.144
- **sinusoid3a.jpg:** A_pct=8.177, omega_pct=7.409, phi_rad=0.0732
- **quadratic1a.jpg:** a_pct=0.2617, b_pct=0.2884, c_pct=0.1953
- **quadratic2a.jpg:** a_pct=0.2169, b_pct=0.2486, c_pct=0.1591

## Camera verification (next step)

1. Print each labeled JPEG (or use the `*a` unlabeled grid variants).
2. Run `.venv/bin/python line_camera.py`.
3. Calibrate corners (`m`) and set axis preset to match:
   - Lines: preset `1`/`2`/`3` for line1/2/3
   - Sinusoids / quadratics: tune `[` `]` `,` `.` to match printed axis ranges above.
4. Compare on-screen **Shape** and equation to this table.
5. Save frames with `s` into `captures/` for records.

Overlay images: `validation/results/overlays/`

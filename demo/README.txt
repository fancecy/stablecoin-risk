STABLECOIN DEPEGGING RISK PREDICTION AND RESERVE STRESS TESTING
Midterm Prototype: Historical Events and Intervention Analysis

OPEN THE DEMO
1. Extract the entire ZIP archive to a normal folder.
2. Open index.html in Chrome, Edge, Firefox, or Safari.
3. Keep index.html and all its companion files in the same extracted folder.

No installation, account, Python runtime, web server, or internet connection is required for the interactive demo. All scenario data and charts are bundled locally. Source URLs in the provenance notes are optional external references; the reserve PDF is also included.

Do not open index.html inside a ZIP preview. Do not send only index.html: send the complete ZIP archive. If your messaging app shows a preview instead of the demo, save and extract the archive first, then choose Open With and select your browser. Use a desktop or laptop for the presentation.

WHAT TO SHOW
- Browse the six historical events.
- Select the SVB / USDC case for the reserve simulation.
- Compare the four interventions under the default scenario.
- Change credit activation to day 5.
- Test 40% redemptions, a 45-day freeze, and a 0.1% daily sales cap.
- Review timing, failure brackets, financing debt, and solvency warnings.
- Export the results, daily paths, and scenario configuration.

REPORT AND DATA
report-en.html: English research report.
presentation-notes.txt: English presentation notes.
results/: original model outputs; monetary values in CSV files are USD.
figures/: report figures; see axis labels for units.
evidence/: reserve snapshot, source notes, and original reserve PDF.
manifest.json: experiment settings and provenance hashes.
audit.json: accounting validation results.

The display uses USD billion. Recovery means clearing redemption backlogs, not restoring the market peg. Results are conditional simulations, not causal estimates of historical policy effects. The prototype contains 300 selectable configurations computed with one model; it does not interpolate between configurations.

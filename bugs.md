# Bugs

Lightweight defect registry. When a bug fix is requested, add a short entry here before making the code change.

## Open

- None currently tracked.

## Fixed

- Leakage Rate quarterly chart was clipped because the Streamlit metric iframe height still assumed a single chart.
- Defects by Status & Environment chart rendered many statuses as black, making legend and stacks hard to distinguish.
- Cumulative Open vs Closed chart lost area fill after adding High+Critical overlay lines.
- Run Analysis button was hidden while upload/header processing was incomplete, leaving users unsure what to do.
- Run Analysis button placeholder appeared between uploader and mapping/filter section instead of at the bottom.

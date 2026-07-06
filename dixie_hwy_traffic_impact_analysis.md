# Dixie Highway Traffic Impact Analysis

**[Full project files and interactive map →](dixie-hwy-traffic-analysis/)**

## One-sentence summary

Built a multi-model traffic impact analysis that reveals how a proposed lane reduction on US-25 Dixie Highway (Kenton County, KY) would increase per-vehicle delay by 83% — a finding hidden by the standard BPR formula — and identified the commercial driveway conflicts, not intersection timing, as the real bottleneck.

## What I built

- **BPR macroscopic model** — Bureau of Public Roads link-performance function comparing 5-lane vs. 3-lane capacity across a range of traffic volumes (10k–31k AADT).
- **Discrete-event microsimulation** — Custom Python simulator with a heapq event queue, 8 signalized intersections, Poisson vehicle arrivals, and FIFO queuing. Captures queue buildup that BPR ignores.
- **Geospatial corridor overlay** — Used osmnx to pull the real OSM road network by bounding box, extracted US-25 centerline geometry, plotted 16 commercial POIs (Kroger, Lowe's, Chick-fil-A, Dixie Heights HS, etc.) with their 31 driveway access points, and rendered it as a before/after interactive folium map.
- **Auto-generated report** — Text summary of all model outputs written programmatically from simulation results.

## Key results

| Model | Travel time / delay — current | Travel time / delay — proposed | Change |
|---|---|---|---|
| BPR macroscopic | 2.31 min | 2.34 min | **+1.3%** |
| Discrete-event micro | 563 s avg delay | 1,030 s avg delay | **+82.9%** |
| With geospatial POI reality | ~5.34 min | ~5.55–5.66 min | **+4–6%** |

The gap between +1.3% (BPR) and +82.9% (microsim) is the core finding: simple capacity formulas understate real-world congestion because they don't model queue propagation across signal cycles.

The 52% capacity reduction (8,750 → 4,200 veh/hr) combined with 31 mid-block commercial access points makes the road diet unviable without mitigations — specifically, right-in/right-out restrictions at the top 5 driveways, peak-hour left-turn restrictions, and turn-pocket extensions at the Kroger/Lowe's/school clusters.

## Tools

Python 3.11 · NumPy · Pandas · Matplotlib · Folium · osmnx · Shapely · Jupyter

## Why it matters for a portfolio

This project demonstrates being able to go beyond plug-and-play tools: implementing a custom discrete-event simulator from scratch, integrating real geospatial data to ground a purely quantitative model, and using the *disagreement* between two modeling approaches as the analytical insight rather than treating one as ground truth.

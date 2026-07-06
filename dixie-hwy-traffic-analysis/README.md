# Dixie Highway (US-25) Traffic Impact Analysis
**Kenton County, KY — Proposed 5-lane → 3-lane Road Diet**

## What this project does

Quantifies the traffic impact of converting a 4-mile segment of US-25 Dixie Highway from a 5-lane undivided arterial to a 3-lane configuration with a shared center turn lane. Uses two independent modeling approaches and a real geospatial overlay to arrive at a grounded, data-backed recommendation.

## Key finding

The macroscopic BPR model says travel time increases by only **+1.3%** — misleadingly optimistic. The discrete-event microsimulation, which captures queue dynamics at all 8 signalized intersections, finds **+82.9% per-vehicle delay** under the proposed configuration. The gap between these two numbers is the story: simple capacity formulas hide what actually happens at traffic signals.

Adding the geospatial layer (31 commercial driveway access points, 16 POIs including Kroger, Lowe's, Chick-fil-A) raises the real-world estimate to **+4–6%** corridor travel time — driven more by mid-block turning conflicts than by intersection timing.

**Bottom line:** The road diet is not viable as proposed. It becomes viable with RIRO restrictions at the top 5 commercial driveways, left-turn restrictions during peak hours, and turn-pocket extensions at the 3 highest-conflict clusters.

## Models implemented

| Model | Type | Finding |
|---|---|---|
| Bureau of Public Roads (BPR) | Macroscopic link-performance | +1.3% travel time @ 18k AADT |
| Discrete-event microsimulation | 8 intersections, Poisson arrivals, FIFO queuing | +82.9% per-vehicle delay |
| Geospatial POI overlay | 31 access points, 16 commercial POIs | True impact ~4–6% |

## Files

| File | What it is |
|---|---|
| `traffic_sim.ipynb` | Main analysis notebook — all three models + outputs |
| `generate_dixie_hwy_map_v2.py` | Standalone script: fetches real OSM road network via osmnx, generates before/after folium map |
| `generate_us25_map.py` | Earlier map generation script |
| `dixie_hwy_geospatial_map_v2.html` | Interactive before/after corridor map (open in browser) |
| `dixie_hwy_geospatial_static.png` | Publication-ready static map with 16 POIs and 8 intersections |
| `travel_time_plot.png` | BPR model results across AADT range |
| `baseline_comparison.png` | Scenario comparison: current vs. proposed (BPR) |
| `micro_travel_times.png` | Microsimulation travel time results |
| `micro_baseline_comparison.png` | Microsimulation scenario comparison |
| `dixie_hwy_analysis_results.csv` | Quantitative results (BPR + microsim, 21 scenarios) |
| `corridor_metrics.csv` | Corridor-level summary metrics |
| `corridor_analysis_report.txt` | Auto-generated text report |
| `COMPLETE_ANALYSIS_SUMMARY.md` | Full narrative summary with recommendations |
| `GEOSPATIAL_ANALYSIS_README.md` | Geospatial analysis detail and POI impact breakdown |

## Stack

- Python 3.11 — NumPy, Pandas, Matplotlib
- Folium + Branca — interactive map rendering
- osmnx — real OSM road network extraction by bounding box
- Shapely — geometry handling
- Jupyter (also Databricks-compatible)

## How to run

```bash
pip install numpy pandas matplotlib folium branca osmnx shapely jupyter

# Full analysis
jupyter notebook traffic_sim.ipynb

# Regenerate the interactive map against live OSM data
python generate_dixie_hwy_map_v2.py
```

The map script caches the OSM graph locally (`osm_graph_cache.pkl`) so repeated runs are fast.

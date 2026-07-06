"""
Generate an improved interactive map for Dixie Highway (US-25) using OSM data.
Outputs:
 - dixie_hwy_us25_map.html  (interactive folium map)
 - dixie_hwy_us25_static.png (static png snapshot)

Requires: osmnx, geopandas, folium, contextily, matplotlib
Run with the project's virtualenv Python to ensure packages are available.
"""

import os
import sys
from pathlib import Path
import folium
import osmnx as ox
import geopandas as gpd
import shapely.geometry as geom
import matplotlib.pyplot as plt

# Parameters / bounding box (Commonwealth Ave to Turkeyfoot Rd)
lat_north = 39.0450
lat_south = 39.0120
lon_west = -84.4700
lon_east = -84.4500

out_dir = Path(__file__).resolve().parent
html_out = out_dir / 'dixie_hwy_us25_map.html'
png_out = out_dir / 'dixie_hwy_us25_static.png'

print(f"Using bbox: N={lat_north}, S={lat_south}, W={lon_west}, E={lon_east}")

# 1) Fetch road network in bounding box
print('Fetching road network from OSM...')
G = ox.graph_from_bbox(lat_north, lat_south, lon_east, lon_west, network_type='drive')

# Convert to GeoDataFrames
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G)
print(f'Network retrieved: {len(nodes_gdf)} nodes, {len(edges_gdf)} edges')

# 2) Try to locate US-25 / Dixie Highway by name on edges
candidate_names = ['US 25', 'US-25', 'U.S. 25', 'U.S. Route 25', 'Dixie Hwy', 'Dixie Highway', 'Dixie Hwy.']
print('Searching for highway edges matching known names...')

# edges_gdf['name'] may be list or string
matches = []
for idx, row in edges_gdf.iterrows():
    name = row.get('name')
    if name is None:
        continue
    names = name if isinstance(name, list) else [name]
    for n in names:
        for cand in candidate_names:
            if cand.lower() in str(n).lower():
                matches.append(idx)
                break
        else:
            continue
        break

if matches:
    print(f'Found {len(matches)} edges explicitly named as US-25/Dixie Hwy')
    us25_edges = edges_gdf.loc[list(set(matches))].copy()
else:
    # Fallback: pick the longest primary/secondary road running north-south in bbox
    print('No explicit name matches found; using heuristic to find main N-S road')
    # Filter by highway tag types
    def highway_priority(val):
        if val is None:
            return 0
        if isinstance(val, list):
            val = val[0]
        mapping = {'primary':4, 'secondary':3, 'tertiary':2, 'residential':1}
        return mapping.get(val, 0)
    edges_gdf['hwy_prio'] = edges_gdf['highway'].apply(highway_priority)
    candidates = edges_gdf[edges_gdf['hwy_prio'] >= 2].copy()
    # compute length
    candidates['length_m'] = candidates.geometry.length
    # pick the longest continuous group near center longitude
    # sort by length and take top geometries
    top = candidates.sort_values('length_m', ascending=False).head(20)
    # further filter by centroid longitude close to center
    center_lon = (lon_west + lon_east) / 2
    top['centroid_lon_diff'] = top.geometry.centroid.x.apply(lambda x: abs(x - center_lon))
    top = top.sort_values(['centroid_lon_diff','length_m'])
    us25_edges = top.head(6).copy()
    print(f'Heuristic selected {len(us25_edges)} edges as main corridor')

# 3) Fetch POIs from OSM: fast_food, restaurant, fuel, shop=supermarket, amenity=school
print('Fetching POIs (fast_food, restaurant, fuel, supermarket, school) from OSM...')
poi_tags = {'amenity': ['fast_food', 'restaurant', 'school', 'fuel'], 'shop': ['supermarket', 'convenience']}
# Use geometries_from_bbox to get features matching any of these tags
poi_gdfs = []
for key, vals in poi_tags.items():
    for v in vals:
        try:
            g = ox.geometries_from_bbox(lat_north, lat_south, lon_east, lon_west, {key: v})
            if not g.empty:
                poi_gdfs.append(g)
        except Exception as e:
            print('Warning fetching POI', key, v, e)

if poi_gdfs:
    pois = gpd.GeoDataFrame(pd.concat(poi_gdfs, ignore_index=True))
    # normalize geometry to points (centroid if polygon)
    pois['geometry'] = pois.geometry.centroid
    print(f'Collected {len(pois)} POI features')
else:
    pois = gpd.GeoDataFrame(columns=['geometry'])
    print('No POI features found in bbox')

# Filter for named POIs of interest if available
poi_names_of_interest = ['Kroger', 'KFC', 'Chipotle', 'Dixie Heights High', "Dixie Heights High School", 'Shell', 'BP', 'McDonald', 'Wendy', 'Subway', 'Chick-fil-A', 'Domino']
selected_pois = []
if not pois.empty:
    for idx, row in pois.iterrows():
        name = row.get('name')
        if name:
            for needle in poi_names_of_interest:
                if needle.lower() in str(name).lower():
                    selected_pois.append((name, row.geometry))

# If no named matches, take nearest pois to corridor centerline
if not selected_pois and not pois.empty:
    print('No named POI matches; selecting top POI by proximity to corridor centerline')
    # build corridor centerline from us25_edges
    centerline = us25_edges.unary_union
    pois['dist_to_corr'] = pois.geometry.apply(lambda g: g.distance(centerline))
    nearest = pois.sort_values('dist_to_corr').head(12)
    selected_pois = [(r.get('name') or 'POI', r.geometry) for i, r in nearest.iterrows()]

# 4) Build Folium map with US-25 geometry and selected POIs
m = folium.Map(location=[(lat_north+lat_south)/2, (lon_west+lon_east)/2], zoom_start=14, tiles='CartoDB positron')

# Add full edges for context (light gray)
for _, row in edges_gdf.iterrows():
    try:
        coords = [(y, x) for x, y in row.geometry.coords]
        folium.PolyLine(coords, color='#d3d3d3', weight=2, opacity=0.6).add_to(m)
    except Exception:
        # MultiLineString or other geometry
        try:
            for geompart in row.geometry:
                coords = [(y, x) for x, y in geompart.coords]
                folium.PolyLine(coords, color='#d3d3d3', weight=2, opacity=0.6).add_to(m)
        except Exception:
            continue

# Emphasize US-25 corridor
for _, row in us25_edges.iterrows():
    geom_line = row.geometry
    # handle multilines
    if geom_line.geom_type == 'MultiLineString':
        for part in geom_line:
            coords = [(pt[1], pt[0]) for pt in part.coords]
            folium.PolyLine(coords, color='#FF4500', weight=6, opacity=0.9).add_to(m)
    else:
        try:
            coords = [(pt[1], pt[0]) for pt in geom_line.coords]
            folium.PolyLine(coords, color='#FF4500', weight=6, opacity=0.9).add_to(m)
        except Exception:
            # try to iterate
            for part in geom_line:
                coords = [(pt[1], pt[0]) for pt in part.coords]
                folium.PolyLine(coords, color='#FF4500', weight=6, opacity=0.9).add_to(m)

# Add POI markers
import pandas as pd
if selected_pois:
    for name, geom_pt in selected_pois:
        lat, lon = geom_pt.y, geom_pt.x
        folium.Marker([lat, lon], popup=f"<b>{name}</b>", tooltip=name,
                      icon=folium.Icon(color='blue', icon='info-sign')).add_to(m)
else:
    print('No POIs selected to add to map')

# Add previously defined signalized intersections approximate positions
intersections = [
    ('Commonwealth Ave', 39.0440, -84.4585),
    ('Signal 2', 39.0400, -84.4585),
    ('Signal 3', 39.0360, -84.4585),
    ('Signal 4', 39.0320, -84.4585),
    ('Signal 5', 39.0280, -84.4585),
    ('Signal 6', 39.0240, -84.4585),
    ('Signal 7', 39.0200, -84.4585),
    ('Turkeyfoot Rd', 39.0140, -84.4585),
]
for name, lat, lon in intersections:
    folium.CircleMarker([lat, lon], radius=6, color='red', fill=True, fill_color='red', popup=name).add_to(m)

# Save HTML
m.save(str(html_out))
print('Saved interactive map to', html_out)

# 5) Create a simple static PNG via matplotlib for quick presentation
print('Creating static PNG using geopandas/matplotlib...')
fig, ax = plt.subplots(figsize=(10, 12))
# plot edges
edges_gdf.plot(ax=ax, color='lightgray', linewidth=1)
# plot US-25 emphasized
us25_edges.plot(ax=ax, color='#FF4500', linewidth=4)
# plot POIs
if selected_pois:
    xs = [pt.x for _, pt in selected_pois]
    ys = [pt.y for _, pt in selected_pois]
    ax.scatter(xs, ys, c='blue', s=50, edgecolor='k')
    for name, pt in selected_pois:
        ax.annotate(name, xy=(pt.x, pt.y), xytext=(3,3), textcoords='offset points', fontsize=8)
# plot intersections
for name, lat, lon in intersections:
    ax.plot(lon, lat, marker='s', color='red', markersize=6)
    ax.text(lon+0.0003, lat+0.0002, name, fontsize=8)

ax.set_title('Dixie Highway (US-25) - Actual Road Geometry with POIs')
ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
plt.tight_layout()
plt.savefig(str(png_out), dpi=150)
print('Saved static PNG to', png_out)
print('Done.')

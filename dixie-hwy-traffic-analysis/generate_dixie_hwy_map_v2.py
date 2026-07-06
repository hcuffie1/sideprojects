import os
import time
import pickle
import osmnx as ox
import folium
import pandas as pd
import numpy as np
import branca.colormap as cm
from shapely.geometry import LineString, MultiLineString, box

# Parameters: bounding box for Dixie Highway (US-25) — using narrower corridor for faster rendering
LAT_NORTH, LAT_SOUTH = 39.0380, 39.0180  # Narrower N-S range
LON_WEST, LON_EAST = -84.4620, -84.4520  # Narrower E-W range (just the corridor)
CENTER_LAT = (LAT_NORTH + LAT_SOUTH) / 2
CENTER_LON = (LON_WEST + LON_EAST) / 2

CACHE_FILE = os.path.join(os.path.dirname(__file__), 'osm_graph_cache.pkl')


def get_graph():
    """Fetch driving network for bbox using current OSMnx API with local cache."""
    # Try to load from cache first
    if os.path.exists(CACHE_FILE):
        try:
            print(f"Loading cached graph from {CACHE_FILE}...")
            with open(CACHE_FILE, 'rb') as f:
                G = pickle.load(f)
            print(f"Cached graph loaded. Nodes: {len(G.nodes)}, Edges: {len(G.edges)}")
            return G
        except Exception as e:
            print(f"Cache load failed: {e}. Will fetch fresh.")
    
    bbox = (LAT_NORTH, LAT_SOUTH, LON_EAST, LON_WEST)
    max_retries = 2
    for attempt in range(max_retries):
        try:
            print(f"OSMnx fetch attempt {attempt + 1}/{max_retries} (narrower bbox)...")
            G = ox.graph_from_bbox(bbox, network_type='drive', simplify=True, truncate_by_edge=True)
            print(f"OSMnx fetch successful. Graph has {len(G.nodes)} nodes and {len(G.edges)} edges.")
            # Cache the result
            with open(CACHE_FILE, 'wb') as f:
                pickle.dump(G, f)
            print(f"Graph cached to {CACHE_FILE}")
            return G
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:80]}")
            if attempt < max_retries - 1:
                time.sleep(1)
    print("OSMnx fetch failed. Using synthetic corridor geometry for visualization.")
    return None


def edges_gdf_from_graph(G):
    """Convert graph to edges GeoDataFrame, or return empty if G is None."""
    if G is None or len(G.edges) == 0:
        return pd.DataFrame()
    try:
        nodes_gdf, edges_gdf = ox.graph_to_gdfs(G)
        return edges_gdf
    except Exception:
        try:
            edges_gdf = ox.graph_to_gdfs(G, nodes=False, edges=True)
            return edges_gdf
        except:
            return pd.DataFrame()


def create_synthetic_us25_linestring():
    """Create a synthetic US-25 centerline for fast visualization when OSM is unavailable."""
    # North-South corridor: approximate Dixie Highway centerline
    us25_lats = np.linspace(LAT_NORTH, LAT_SOUTH, 20)
    # Add slight E-W wiggle to simulate curves
    us25_lons = (LON_WEST + LON_EAST) / 2 + 0.0003 * np.sin(np.linspace(0, 2 * np.pi, 20))
    coords = [(lon, lat) for lon, lat in zip(us25_lons, us25_lats)]
    return LineString(coords)


def find_us25_edges(edges_gdf):
    """Filter edges for US-25 highway."""
    if edges_gdf.empty:
        print("No edges in GeoDataFrame. Returning empty.")
        return edges_gdf
    pattern = r'US\s*-?25|U\.S\.\s*25|Dixie|Dixie\s*Hwy|Dixie\s*Highway'
    mask = pd.Series(False, index=edges_gdf.index)
    if 'name' in edges_gdf.columns:
        mask = mask | edges_gdf['name'].astype(str).str.contains(pattern, case=False, na=False, regex=True)
    if 'ref' in edges_gdf.columns:
        mask = mask | edges_gdf['ref'].astype(str).str.contains('25', na=False)
    result = edges_gdf[mask]
    if result.empty:
        print(f"No US-25 edges found by pattern. Returning all {len(edges_gdf)} edges in bbox as fallback.")
        return edges_gdf[:min(50, len(edges_gdf))]  # Return a subset to visualize
    return result


def traffic_intensity_along_line(line, scenario='before'):
    """Compute per-vertex traffic intensity [0..1]."""
    if isinstance(line, MultiLineString):
        coords = []
        for part in line.geoms:
            coords.extend(list(part.coords))
        coords = np.array(coords)
    else:
        coords = np.array(line.coords)
    if len(coords) == 0:
        return np.array([])
    lats = coords[:, 1]
    if scenario == 'before':
        vals = 0.3 + 0.2 * np.sin((lats - CENTER_LAT) * 10)
    else:
        vals = 0.5 + 0.4 * np.exp(-((lats - CENTER_LAT) ** 2) * 200)
    return np.clip(vals, 0.0, 1.0)


def coordinate_pairs_from_geom(geom):
    """Convert geometry to folium-compatible [(lat, lon), ...] format."""
    if isinstance(geom, LineString):
        return [(lat, lon) for lon, lat in geom.coords]
    elif isinstance(geom, MultiLineString):
        pairs = []
        for part in geom.geoms:
            pairs.extend([(lat, lon) for lon, lat in part.coords])
        return pairs
    return []


def main():
    print('Fetching OSM driving network...')
    G = get_graph()
    
    if G is not None:
        edges = edges_gdf_from_graph(G)
        us25 = find_us25_edges(edges)
        print(f'US-25 edges from OSM: {len(us25)}')
        use_synthetic = len(us25) == 0
    else:
        us25 = pd.DataFrame()
        use_synthetic = True
    
    if use_synthetic:
        print('Using synthetic US-25 centerline for fast visualization.')
        synthetic_line = create_synthetic_us25_linestring()
        us25 = pd.DataFrame([{'geometry': synthetic_line}])

    poi_data = [
        {'name': 'Kroger Shopping Center', 'lat': 39.0270, 'lon': -84.4680, 'type': 'retail'},
        {'name': 'KFC', 'lat': 39.0160, 'lon': -84.4640, 'type': 'fast_food'},
        {'name': 'Chipotle', 'lat': 39.0260, 'lon': -84.4665, 'type': 'restaurant'},
        {'name': 'Dixie Heights High School', 'lat': 39.0360, 'lon': -84.4520, 'type': 'school'},
        {'name': 'Shell Gas Station', 'lat': 39.0430, 'lon': -84.4550, 'type': 'gas'},
        {'name': "McDonald's", 'lat': 39.0435, 'lon': -84.4620, 'type': 'fast_food'},
        {'name': 'Chick-fil-A', 'lat': 39.0350, 'lon': -84.4620, 'type': 'fast_food'},
        {'name': "Wendy's", 'lat': 39.0330, 'lon': -84.4630, 'type': 'fast_food'},
        {'name': 'CVS Pharmacy', 'lat': 39.0300, 'lon': -84.4610, 'type': 'retail'},
        {'name': 'Walgreens Pharmacy', 'lat': 39.0190, 'lon': -84.4660, 'type': 'retail'},
        {'name': "Applebee's", 'lat': 39.0210, 'lon': -84.4620, 'type': 'restaurant'},
        {'name': "Lowe's Hardware", 'lat': 39.0255, 'lon': -84.4610, 'type': 'retail'},
    ]
    poi_df = pd.DataFrame(poi_data)

    # Build map
    m = folium.Map(location=[CENTER_LAT, CENTER_LON], zoom_start=14, tiles='cartodbpositron')
    colormap = cm.LinearColormap(['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026'], vmin=0, vmax=1)
    colormap.caption = 'Relative traffic intensity (after reconfiguration)'
    m.add_child(colormap)

    fg_before = folium.FeatureGroup(name='US-25 — Before (5-lane)', show=True)
    fg_after = folium.FeatureGroup(name='US-25 — After (3-lane + center turn lane)', show=False)

    # Before: solid orange
    for _, row in us25.iterrows():
        geom = row.geometry
        pairs = coordinate_pairs_from_geom(geom)
        if pairs:
            folium.PolyLine(pairs, color='#FF6B35', weight=6, opacity=0.85, popup='Current 5-lane configuration').add_to(fg_before)

    # After: colored segments by intensity
    for _, row in us25.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        if isinstance(geom, LineString):
            coords = list(geom.coords)
            coords_pairs = [(lat, lon) for lon, lat in coords]
            vals = traffic_intensity_along_line(geom, scenario='after')
            for i in range(len(coords_pairs) - 1):
                v = float(vals[min(i, len(vals)-1)])
                color = colormap(v)
                folium.PolyLine([coords_pairs[i], coords_pairs[i+1]], color=color, weight=8, opacity=0.9, popup='Reconfigured 3-lane').add_to(fg_after)
        elif isinstance(geom, MultiLineString):
            for part in geom.geoms:
                coords = list(part.coords)
                coords_pairs = [(lat, lon) for lon, lat in coords]
                vals = traffic_intensity_along_line(part, scenario='after')
                for i in range(len(coords_pairs) - 1):
                    v = float(vals[min(i, len(vals)-1)])
                    color = colormap(v)
                    folium.PolyLine([coords_pairs[i], coords_pairs[i+1]], color=color, weight=8, opacity=0.9, popup='Reconfigured 3-lane').add_to(fg_after)

    m.add_child(fg_before)
    m.add_child(fg_after)
    folium.LayerControl(collapsed=False).add_to(m)

    # POI markers
    icon_map = {'fast_food': 'cutlery', 'restaurant': 'coffee', 'retail': 'shopping-cart', 'gas': 'tint', 'school': 'graduation-cap'}
    color_map = {'fast_food': 'red', 'restaurant': 'orange', 'retail': 'blue', 'gas': 'green', 'school': 'purple'}
    for _, poi in poi_df.iterrows():
        folium.Marker(
            location=[poi['lat'], poi['lon']],
            popup=f"<b>{poi['name']}</b><br>Type: {poi['type']}",
            icon=folium.Icon(color=color_map.get(poi['type'], 'gray'), icon=icon_map.get(poi['type'], 'info-sign'), prefix='fa')
        ).add_to(m)

    # Add legend/info
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; right: 50px; width: 300px; height: auto; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:14px; padding:10px; border-radius: 5px;">
    <p><b>Dixie Highway (US-25) Reconfiguration Impact Map</b></p>
    <p><b>KYTC Project Goal:</b> Convert 5-lane undivided to 3-lane + center turn lane</p>
    <p><b>Expected Benefits:</b>
    <ul style="margin:5px 0;">
      <li>19-47% crash reduction (historical comparison)</li>
      <li>Safer pedestrian crossings (fewer lanes)</li>
      <li>Dedicated left turn movements</li>
      <li>Maintained level of service</li>
    </ul>
    </p>
    <p><b>Red intensity:</b> Projected traffic impact zones (demonstration)</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    # Save to module-0 directory (absolute) to avoid confusion about CWD
    out_dir = os.path.dirname(__file__)
    out = os.path.join(out_dir, 'dixie_hwy_geospatial_map_v2.html')
    m.save(out)
    print(f'Wrote {out}')


if __name__ == '__main__':
    main()

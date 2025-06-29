from flask import Flask, request, render_template, send_file
import requests
import tempfile
import json
import gpxpy
import gpxpy.gpx
from shapely.geometry import shape, Polygon, MultiPolygon
import folium

app = Flask(__name__)

NIBIO_WFS_URL = "https://wfs.nibio.no/geoserver/eiendom/wfs"

def fetch_nibio_geojson(kommune, gnr, bnr):
    cql = f"kommunenr='{kommune}' AND gardsnr='{gnr}' AND bruksnr='{bnr}'"
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": "eiendom:eiendomsflate",
        "outputFormat": "application/json",
        "cql_filter": cql
    }
    r = requests.get(NIBIO_WFS_URL, params=params)
    if r.status_code != 200 or not r.text.strip().startswith("{"):
        raise Exception("Ugyldig svar fra NIBIO WFS – sjekk GNR/BNR/Kommune")
    return r.json()

def convert_to_gpx(geojson):
    gpx = gpxpy.gpx.GPX()
    for feature in geojson["features"]:
        geom = shape(feature["geometry"])
        polygons = [geom] if isinstance(geom, Polygon) else geom.geoms if isinstance(geom, MultiPolygon) else []
        for polygon in polygons:
            segment = gpxpy.gpx.GPXTrackSegment()
            for lon, lat in polygon.exterior.coords:
                segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon))
            gpx.tracks.append(gpxpy.gpx.GPXTrack(segments=[segment]))
    return gpx

def convert_to_kml(geojson):
    from fastkml import kml
    k = kml.KML()
    ns = "{http://www.opengis.net/kml/2.2}"
    doc = kml.Document(ns, "1", "Eiendom", "Grenser fra NIBIO")
    k.append(doc)
    for feature in geojson["features"]:
        geom = shape(feature["geometry"])
        placemark = kml.Placemark(ns, "2", "Eiendom", "")
        placemark.geometry = geom
        doc.append(placemark)
    return k.to_string(prettyprint=True)

def create_map(geojson):
    if not geojson["features"]:
        return ""
    geom = shape(geojson["features"][0]["geometry"])
    bounds = geom.bounds
    m = folium.Map(location=[(bounds[1]+bounds[3])/2, (bounds[0]+bounds[2])/2], zoom_start=17)
    folium.GeoJson(geojson).add_to(m)
    map_path = tempfile.NamedTemporaryFile(delete=False, suffix=".html").name
    m.save(map_path)
    with open(map_path, encoding="utf-8") as f:
        return f.read()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        kommune = request.form.get("kommune")
        gnr = request.form.get("gnr")
        bnr = request.form.get("bnr")
        filtype = request.form.get("filtype")

        try:
            geojson = fetch_nibio_geojson(kommune, gnr, bnr)
            kart_html = create_map(geojson)

            if filtype == "gpx":
                gpx = convert_to_gpx(geojson)
                temp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpx")
                temp.write(gpx.to_xml().encode("utf-8"))
            else:
                kml = convert_to_kml(geojson)
                temp = tempfile.NamedTemporaryFile(delete=False, suffix=".kml")
                temp.write(kml.encode("utf-8"))
            temp.close()
            return render_template("index.html", map_html=kart_html, download_link="/nedlast/" + os.path.basename(temp.name))

        except Exception as e:
            return f"Feil: {e}"

    return render_template("index.html", map_html=None)

@app.route("/nedlast/<path:filename>")
def nedlast(filename):
    return send_file(f"/tmp/{filename}", as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
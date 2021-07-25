import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import pandas as pd
import json
from urllib.request import urlopen
from geomet import wkt
import requests
from bs4 import BeautifulSoup
import datetime
import math
import sys
from decouple import config

# --------------------
#       CHANGELOG
# In prior versions, covid_data_url_raw was removed from website... so replaced with https://raw.githubusercontent.com/nychealth/coronavirus-data/master/totals/data-by-modzcta.csv
# and had to add covid_data_totals_url to ref latest change in datetime
# --------------------


# DATA COLLECTION

covid_data_url = 'https://github.com/nychealth/coronavirus-data'
covid_data_totals_url = 'https://github.com/nychealth/coronavirus-data/blob/master/totals/data-by-modzcta.csv'
covid_data_url_raw = 'https://raw.githubusercontent.com/nychealth/coronavirus-data/master/totals/data-by-modzcta.csv'

df = pd.read_csv(covid_data_url_raw)
df2 = pd.read_csv('ZIP_Code_Tabulation_Areas__ZCTAs_.csv')

# TIME UPDATE
my_user_agent = config('MY_USER_AGENT')

def get_soup(url):
    html = requests.get(url, headers={"User-Agent": my_user_agent})
    soup = BeautifulSoup(html.text, 'html.parser')
    return soup


soup = get_soup(covid_data_totals_url)

tests_row = soup.select_one('tr:contains("data-by-modzcta.csv")')
time_ago = soup.find("relative-time")['datetime']
time_ago_datetime = datetime.datetime.strptime(time_ago, "%Y-%m-%dT%H:%M:%SZ")
time_ago_datetime_str = time_ago_datetime.strftime(
    "%a %b %d, %Y - %I:%M:%S %p")

date_var = dict(v=time_ago_datetime)

# Cast df zips to list, as int, and remove NaN + Make new df matched by zip codes and rename column
ziplist = df['MODIFIED_ZCTA'].tolist()
ziplistfix = []

for i in ziplist:
    if math.isnan(i):
        continue
    else:
        ziplistfix.append(int(i))

df_geomatch = df2[df2['ZCTA Code'].isin(ziplistfix)]
df_geomatch = df_geomatch.rename(columns={'the_geom': 'geometry'})
df_geomatch = df_geomatch.rename(columns={'ZCTA Code': 'ZCTA_Code'})


# Use wkt and json module to create a geojson column in df_geomatch Dataframe
# Apply function to create new column
df_geomatch["geojson"] = df_geomatch["polygon_geom"].apply(
    lambda x: json.dumps(wkt.loads(x)))


# Drop NaN in original df, cast MODZCTA to int, make a copy of df (df_prefinal) and rename MODZCTA to ZCTA_Code...
df.dropna(inplace=True)
df['MODIFIED_ZCTA'] = df['MODIFIED_ZCTA'].astype(int)
df_prefinal = df
df_prefinal = df_prefinal.rename(
    columns={'MODIFIED_ZCTA': 'ZCTA_Code', 'COVID_CASE_COUNT': 'Total'})


# Merge Dataframes df_geomatch and df_prefinal on ZCTA_Code & Inspect
df_final_merged = df_geomatch.merge(df_prefinal, how='inner', on=['ZCTA_Code'])

# Cast ZCTA_Code to string
df_final_merged['ZCTA_Code'] = df_final_merged['ZCTA_Code'].astype(str)


# Create a geojson string from df_final_merged with geo/coordinate data and COVID data
def df_to_geojson(df, properties, zcta='ZCTA_Code', gj='geojson'):
    geojson = {'type': 'FeatureCollection', 'features': []}
    for _, row in df.iterrows():
        feature = {'type': 'Feature',
                   'properties': {},
                   'geometry': '',
                   'id': []}
        feature['geometry'] = json.loads(row[gj])
        feature['id'] = row[zcta]
        for prop in properties:
            feature['properties'][prop] = row[prop]
        geojson['features'].append(feature)
    return geojson


cols = ["Total", 'ZCTA_Code']
geojson_dict = df_to_geojson(df_final_merged, properties=cols)
geojson_str = json.dumps(geojson_dict, indent=2)


# Read in Cleaned Data - csv and geojson
data = df_final_merged
geojson = json.loads(geojson_str)


# Make Map
my_map = go.Choroplethmapbox(geojson=geojson, locations=data['ZCTA_Code'], z=data['Total'], name='NYC_COVID-MAP',
                             colorscale=[[0, 'rgb(255,239,213)'], [0.25, 'rgb(255,203,164)'],
                                         [0.5, 'rgb(234,60,83)'], [1, 'rgb(139,0,0)']],
                             zmin=data['Total'].min(), zmax=data['Total'].max(),
                             marker_opacity=0.7, marker_line_width=0,
                             colorbar=dict(title='Total Number of Cases'),
                             hovertemplate='Total Number of Cases: %{z}<extra>NY Zip Code: %{properties.ZCTA_Code}</extra>')


app = dash.Dash(__name__)  # , external_stylesheets=external_stylesheets)
server = app.server

app.renderer = 'var renderer = new DashRenderer();'

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
    <link href="https://fonts.googleapis.com/css2?family=Francois+One&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Francois+One&family=Questrial&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:ital,wght@0,400;0,500;0,700;0,900;1,400;1,500;1,700;1,900&display=swap" rel="stylesheet">
    {%css%}
    </head>
    <div class="wrapper">
        <body>
          {%app_entry%}
          <footer id = "font-page-footer">
            <p><em>*Number of COVID-19 cases per Zip Code Area in NYC | Data sourced from NYC Health</em></p>
            <p>This page was created by <a href ="https://www.daveberry.co" target ="_blank"> <strong>Dave Berry</strong></a>.</p>
            {%config%}
            {%scripts%}
            {%renderer%}
          </footer>
        </body>
    </div>
</html>
'''

my_graph = [dcc.Graph(id='choropleth',
                      figure={'data': [my_map],
                              'layout':go.Layout(title='Choropleth Map!', mapbox_style="carto-positron",
                                                 mapbox_zoom=9, mapbox_center={"lat": 40.730610, "lon": -73.935242},
                                                 margin={"r": 0, "t": 0, "l": 0, "b": 0})
                              })]

app.layout = html.Div([
    html.H1('COVID-19 Cases - NYC', className="header1style1"),
    html.Div(html.H2(
        f'Last updated on: {time_ago_datetime_str}', id="h2date"), className="h2date-wrap"),
    html.Div(my_graph, className="main-content")
])

if __name__ == '__main__':
    app.run_server()

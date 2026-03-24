"""
app.py — Airbnb Investment Dashboard (Dash)
"""

import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Import data - pre-cleaned using methods from jupyter notebook
df = pd.read_csv("data/processed/all_listings.csv")

# City-level summary (all cities)
city_stats = df.groupby("city").agg(
    median_price=("price", "median"),
    occupancy_rate=("occupancy_rate", "median"),
    median_annual_revenue=("annual_revenue", "median"),
    listing_count=("price", "count"),
    zillow_home_price=("zillow_home_price", "first"),
).reset_index()
city_stats["gross_yield"] = (
    city_stats["median_annual_revenue"] / city_stats["zillow_home_price"]
).round(4)
n = len(city_stats)
city_stats["investment_score"] = (
    (city_stats["gross_yield"].rank() / n
     + city_stats["occupancy_rate"].rank() / n
     + (1 - city_stats["listing_count"].rank() / n)) / 3
).round(3)

# Metrics the dropdown can rank by
METRICS = {
    "Gross Yield":          {"col": "gross_yield",           "label": "Gross Yield (annual revenue / home price)"},
    "Occupancy Rate":       {"col": "occupancy_rate",        "label": "Occupancy Rate"},
    "Annual Revenue ($)":   {"col": "median_annual_revenue", "label": "Median Annual Revenue ($)"},
    "Median Nightly Price": {"col": "median_price",          "label": "Median Nightly Price ($)"},
    "Home Price ($)":       {"col": "zillow_home_price",     "label": "Zillow Median Home Price ($)"},
    "Listing Count":        {"col": "listing_count",         "label": "Number of Listings"},
    "Investment Score":     {"col": "investment_score",       "label": "Investment Score"},
}

# Chart 4 data (static — doesn't depend on the dropdown) only has mouseover interaction
state_prices = pd.read_csv("data/processed/state_prices.csv")
city_bubbles = df.groupby("city").agg(
    lat=("latitude", "mean"), lon=("longitude", "mean"),
    listing_count=("price", "count"),
).reset_index()

# Build cloropleth once

fig_choropleth = go.Figure()
fig_choropleth.add_trace(go.Choropleth(
    locations=state_prices["State"], z=state_prices["median_home_price"],
    locationmode="USA-states", colorscale="YlOrRd",
    colorbar=dict(title="Median Home<br>Price ($)", x=1.0, tickformat="$,.0f"),
    hovertemplate="<b>%{location}</b><br>Median Home Price: $%{z:,.0f}<extra></extra>",
))
fig_choropleth.add_trace(go.Scattergeo(
    lat=city_bubbles["lat"], lon=city_bubbles["lon"], text=city_bubbles["city"],
    marker=dict(
        size=city_bubbles["listing_count"], sizemode="area",
        sizeref=2.0 * city_bubbles["listing_count"].max() / (40**2),
        sizemin=4, color="rgba(0, 100, 200, 0.6)",
        line=dict(width=1, color="white"),
    ),
    hovertemplate="<b>%{text}</b><br>Listings: %{marker.size:,}<extra></extra>",
    showlegend=False,
))
fig_choropleth.update_layout(
    title="US Real Estate Prices with Airbnb Listing Density"
          "<br><sup>Bubble size = number of Airbnb listings</sup>",
    title_x=0.5,
    geo=dict(scope="usa", showlakes=True, lakecolor="rgb(200, 220, 240)"),
    height=550, margin=dict(l=0, r=0, t=60, b=0),
)

# Build Dash App
app = dash.Dash(__name__)
server = app.server  # need to set gunicorn entry point to app.server, not app on render

app.layout = html.Div(style={"maxWidth": "1200px", "margin": "0 auto",
                              "padding": "20px", "fontFamily": "sans-serif"}, children=[
    html.H1("Airbnb Investment Dashboard", style={"textAlign": "center"}),
    html.P("US Cities — Home Prices, Revenue & Listing Density",
           style={"textAlign": "center", "color": "#666", "marginBottom": "20px"}),

    html.Div(style={"textAlign": "center", "marginBottom": "20px"}, children=[
        html.Label("Rank cities by: ", style={"fontWeight": "bold", "marginRight": "8px"}),
        dcc.Dropdown(
            id="metric-dropdown",
            options=[{"label": k, "value": k} for k in METRICS],
            value="Gross Yield",
            clearable=False,
            style={"width": "300px", "display": "inline-block", "verticalAlign": "middle"},
        ),
    ]),

    dcc.Graph(id="bar-chart"),
    dcc.Graph(id="scatter-chart"),
    dcc.Graph(id="box-chart"),
    dcc.Graph(id="choropleth", figure=fig_choropleth),
])


# ── Callback: updates when the dropdown is used
@app.callback(
    Output("bar-chart", "figure"),
    Output("scatter-chart", "figure"),
    Output("box-chart", "figure"),
    Input("metric-dropdown", "value"),
)


def update_charts(metric_name):
    col = METRICS[metric_name]["col"]
    label = METRICS[metric_name]["label"]

    top10 = city_stats.nlargest(10, col).reset_index(drop=True)
    top_df = df[df["city"].isin(top10["city"])]
    sorted_data = top10.sort_values(col, ascending=True)

    palette = px.colors.qualitative.Plotly
    colors = {city: palette[i % len(palette)]
              for i, city in enumerate(top10.sort_values(col, ascending=False)["city"])}

    # Chart 1: Bar
    fig_bar = px.bar(
        sorted_data, x=col, y="city", orientation="h",
        title=f"Top 10 Cities by {metric_name}",
        labels={col: label, "city": ""},
        color="city", color_discrete_map=colors,
    )
    fig_bar.update_traces(hovertemplate="%{y}: %{x}<extra></extra>")
    fig_bar.update_yaxes(categoryorder="array",
                         categoryarray=sorted_data["city"].tolist())
    fig_bar.update_layout(height=400, showlegend=False, title_x=0.5)

    # Chart 2: Scatter
    fig_scatter = px.scatter(
        top10, x="zillow_home_price", y="median_annual_revenue",
        size="listing_count", text="city",
        title=(f"Home Price vs Annual Revenue (Top 10 by {metric_name})"
               "<br><sup>Bubble size = number of Airbnb listings</sup>"),
        labels={"zillow_home_price": "Median Home Price ($)",
                "median_annual_revenue": "Median Annual Revenue ($)",
                "listing_count": "Listing Count"},
    )
    max_price = top10["zillow_home_price"].max() * 1.1
    fig_scatter.add_trace(go.Scatter(
        x=[0, max_price], y=[0, max_price * 0.05],
        mode="lines", name="5% Yield Line",
        line=dict(dash="dash", color="gray"),
    ))
    fig_scatter.update_traces(textposition="top center",
                              selector=dict(mode="markers+text"))
    fig_scatter.update_layout(height=500, showlegend=True, title_x=0.5)

    # Chart 3: Box
    city_order = top10.sort_values(col, ascending=False)["city"].tolist()
    fig_box = px.box(
        top_df, x="city", y="monthly_revenue",
        title=f"Monthly Revenue Distribution — Top 10 by {metric_name}",
        labels={"monthly_revenue": "Monthly Revenue ($)", "city": ""},
        color="city", color_discrete_map=colors,
        category_orders={"city": city_order},
    )
    y_cap = top_df["monthly_revenue"].quantile(0.99)
    fig_box.update_yaxes(range=[0, y_cap * 1.05])
    fig_box.update_layout(height=450, showlegend=False,
                          xaxis_tickangle=-45, title_x=0.5)

    return fig_bar, fig_scatter, fig_box

if __name__ == "__main__":
    app.run()

"""
data_prep.py — Build the Airbnb + Zillow dataset from real data.
"""

import pandas as pd
import numpy as np
import os
import sys

OUTPUT_DIR = "data/processed"
RAW_FILE = "data/raw/AB_US_2023.csv"
ZILLOW_CITY_FILE = "data/raw/zillow_zhvi_city.csv"
ZILLOW_METRO_FILE = "data/raw/zillow_zhvi_metro.csv"

# ── Map Airbnb city names → Zillow lookup keys ────────────────────────────

AIRBNB_TO_ZILLOW = {
    "Asheville":          ("Asheville", "NC", "city"),
    "Austin":             ("Austin", "TX", "city"),
    "Boston":             ("Boston", "MA", "city"),
    "Broward County":     ("Fort Lauderdale", "FL", "city"),
    "Cambridge":          ("Cambridge", "MA", "city"),
    "Chicago":            ("Chicago", "IL", "city"),
    "Clark County":       ("Las Vegas", "NV", "city"),
    "Columbus":           ("Columbus", "OH", "city"),
    "Denver":             ("Denver", "CO", "city"),
    "Jersey City":        ("Jersey City", "NJ", "city"),
    "Los Angeles":        ("Los Angeles", "CA", "city"),
    "Nashville":          ("Nashville", "TN", "city"),
    "New Orleans":        ("New Orleans", "LA", "city"),
    "New York City":      ("New York", "NY", "city"),
    "Oakland":            ("Oakland", "CA", "city"),
    "Pacific Grove":      ("Pacific Grove", "CA", "city"),
    "Portland":           ("Portland", "OR", "city"),
    "Rhode Island":       ("Providence, RI", None, "metro"),
    "Salem":              ("Salem", "OR", "city"),
    "San Diego":          ("San Diego", "CA", "city"),
    "San Francisco":      ("San Francisco", "CA", "city"),
    "San Mateo County":   ("San Mateo", "CA", "city"),
    "Santa Clara County": ("Santa Clara", "CA", "city"),
    "Santa Cruz County":  ("Santa Cruz", "CA", "city"),
    "Seattle":            ("Seattle", "WA", "city"),
    "Twin Cities MSA":    ("Minneapolis, MN", None, "metro"),
    "Washington D.C.":    ("Washington", "DC", "city"),
}


def load_zillow_prices():
    """Load real Zillow ZHVI data and build a lookup dict for Airbnb cities.

    Reads the city-level and metro-level Zillow CSVs and uses the most
    recent month's ZHVI value for each city we need.

    Also computes state-level median home prices (from city-level data)
    for the choropleth map.
    """
    zillow_city = pd.read_csv(ZILLOW_CITY_FILE)
    zillow_metro = pd.read_csv(ZILLOW_METRO_FILE)

    # The most recent ZHVI value is in the last column
    latest_city_col = zillow_city.columns[-1]
    latest_metro_col = zillow_metro.columns[-1]
    print(f"  Zillow data as of: {latest_city_col}")

    prices = {}
    for airbnb_name, (zillow_name, state, source) in AIRBNB_TO_ZILLOW.items():
        if source == "city":
            match = zillow_city[
                (zillow_city["RegionName"] == zillow_name) &
                (zillow_city["State"] == state)
            ]
            if len(match) == 1:
                val = match[latest_city_col].values[0]
                prices[airbnb_name] = round(val)
            else:
                print(f"  WARNING: no unique match for {airbnb_name} "
                      f"({zillow_name}, {state}) — got {len(match)} rows")
        else:  # metro
            match = zillow_metro[
                zillow_metro["RegionName"] == zillow_name
            ]
            if len(match) == 1:
                val = match[latest_metro_col].values[0]
                prices[airbnb_name] = round(val)
            else:
                print(f"  WARNING: no unique match for {airbnb_name} "
                      f"(metro: {zillow_name}) — got {len(match)} rows")

    print(f"  Loaded Zillow prices for {len(prices)} / {len(AIRBNB_TO_ZILLOW)} cities")

    # State-level median home prices for the choropleth
    state_prices = (
        zillow_city.groupby("State")[latest_city_col]
        .median()
        .reset_index()
        .rename(columns={latest_city_col: "median_home_price"})
    )

    return prices, state_prices


def load_kaggle_data():
    """Load and clean the Kaggle US Airbnb dataset."""
    print(f"Loading {RAW_FILE}...")
    df = pd.read_csv(RAW_FILE, low_memory=False)
    print(f"  Raw: {len(df):,} listings across {df['city'].nunique()} cities")

    # Standardize column names to match our schema
    df = df.rename(columns={
        "neighbourhood": "neighbourhood",
        "number_of_reviews": "number_of_reviews",
    })

    # Keep only whole-home rentals (no private/shared rooms)
    df = df[df["room_type"] == "Entire home/apt"].copy()
    print(f"  After filtering to Entire home/apt: {len(df):,}")

    # Remove extreme price outliers (keep $10–$2000/night)
    df = df[(df["price"] >= 10) & (df["price"] <= 2000)].copy()
    print(f"  After removing price outliers: {len(df):,}")

    # Add Zillow home prices from real ZHVI data
    zillow_prices, _ = load_zillow_prices()
    df["zillow_home_price"] = df["city"].map(zillow_prices)
    
    # Drop cities we don't have Zillow data for
    df = df.dropna(subset=["zillow_home_price"]).copy()

    # Normalize Washington D.C. naming
    df["city"] = df["city"].replace({"Washington D.C.": "Washington DC"})

    # Keep only the columns we need
    df = df[["city", "price", "room_type", "neighbourhood", "latitude",
             "longitude", "reviews_per_month", "availability_365",
             "minimum_nights", "zillow_home_price"]].copy()

    print(f"  Final: {len(df):,} listings across {df['city'].nunique()} cities")
    return df


def add_derived_columns(df):
    """Add occupancy rate and revenue estimates."""
    df["occupancy_rate"] = ((365 - df["availability_365"]) / 365).round(3)
    df["nightly_revenue"] = df["price"]
    df["weekly_revenue"] = df["price"] * 7
    df["monthly_revenue"] = (df["price"] * 30 * df["occupancy_rate"]).round(0)
    df["annual_revenue"] = (df["price"] * 365 * df["occupancy_rate"]).round(0)
    df["gross_yield"] = (df["annual_revenue"] / df["zillow_home_price"]).round(4)
    return df


def build_city_summary(df):
    """Aggregate to city-level summary, ranked by investment score.

    Investment score = average of percentile ranks for:
      - gross yield  (higher = better return)
      - occupancy    (higher = more reliable income)
      - 1/listing_count (lower saturation = less competition)
    """
    city_stats = df.groupby("city").agg(
        median_price=("price", "median"),
        mean_price=("price", "mean"),
        occupancy_rate=("occupancy_rate", "median"),
        median_annual_revenue=("annual_revenue", "median"),
        total_reviews=("reviews_per_month", "sum"),
        listing_count=("price", "count"),
        zillow_home_price=("zillow_home_price", "first"),
    ).reset_index()

    city_stats["gross_yield"] = (
        city_stats["median_annual_revenue"] / city_stats["zillow_home_price"]
    ).round(4)

    # Percentile-rank composite: yield + occupancy + low saturation
    n = len(city_stats)
    city_stats["yield_rank"] = city_stats["gross_yield"].rank() / n
    city_stats["occ_rank"] = city_stats["occupancy_rate"].rank() / n
    city_stats["sat_rank"] = (1 - city_stats["listing_count"].rank() / n)
    city_stats["investment_score"] = (
        (city_stats["yield_rank"] + city_stats["occ_rank"] + city_stats["sat_rank"]) / 3
    ).round(3)

    top10 = city_stats.nlargest(10, "investment_score").reset_index(drop=True)
    return top10


def main():
    df = load_kaggle_data()
    df = add_derived_columns(df)

    # Save all listings
    all_path = os.path.join(OUTPUT_DIR, "all_listings.csv")
    df.to_csv(all_path, index=False)

    _, state_prices = load_zillow_prices()
    state_path = os.path.join(OUTPUT_DIR, "state_prices.csv")
    state_prices.to_csv(state_path, index=False)


if __name__ == "__main__":
    main()

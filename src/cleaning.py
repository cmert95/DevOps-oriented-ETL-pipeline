import glob
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

logging.basicConfig(
    filename="logs/cleaning_logs.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# Find the most recent raw json file
def find_latest_file(path="data/raw"):
    try:
        latest_file = max(glob.glob(os.path.join(path, "raw_weather_*.json")), key=os.path.getctime)
    except ValueError:
        logging.error("No raw json files found.")
        return None
    except Exception as e:
        logging.error(f"Error finding the latest file: {e}")
        return None
    else:
        logging.info(f"Last file found: {latest_file}")
        return latest_file


# Load city and postal info from JSON
def get_location_info(filename="config/location.json"):
    try:
        with open(filename, "r") as f:
            location = json.load(f)
        city = location["city"]
        postal = location["postal"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logging.error(f"Error reading location info: {e}")
        return None, None
    else:
        logging.info(f"Location info retrieved: {city}, {postal}")
        return city, postal


# Load raw JSON weather data
def load_raw_data(file_path):
    try:
        with open(file_path, "r") as f:
            raw_data = json.load(f)
        logging.info(f"Raw data loaded from: {file_path}")
        return raw_data
    except Exception as e:
        logging.error(f"Error loading raw data from {file_path}: {e}")
        return None


# Clean and format raw weather data with interpolated half-hour values
def clean_data(raw_data, city, postal):
    try:
        # Flatten hourly forecast
        records = []
        for day in raw_data["forecast"]["forecastday"]:
            for hour in day["hour"]:
                records.append(hour)

        df = pd.json_normalize(records)

        # Rename columns
        df = df[["time", "temp_c", "condition.text", "humidity", "wind_kph", "feelslike_c"]]
        df.columns = [
            "DateTime",
            "Temperature_C",
            "Condition",
            "Humidity_perc",
            "WindSpeed_kph",
            "FeelsLike_C",
        ]

        # Parse datetime
        df["DateTime"] = pd.to_datetime(df["DateTime"])

        # Clean condition labels
        df["Condition"] = df["Condition"].str.strip().str.title()

        # Add city and postal code
        df["City"] = city
        df["PostalCode"] = postal

        # Drop unrealistic temperature values
        df = df[(df["Temperature_C"] <= 60) & (df["Temperature_C"] >= -30)]

        # Resample
        df.set_index("DateTime", inplace=True)
        interval = os.getenv("INTERVAL", "30min")
        df = df.resample(interval).asfreq()

        # Filling numeric columns
        num_cols = df.select_dtypes(include="number").columns
        df[num_cols] = df[num_cols].interpolate(method="linear").round(1)

        # Filling non-numeric columns
        non_num_cols = df.select_dtypes(exclude="number").columns
        df[non_num_cols] = df[non_num_cols].ffill()

        df.reset_index(inplace=True)
        logging.info("Forecast data cleaned and interpolated successfully.")
        return df

    except Exception as e:
        logging.error(f"Data cleaning failed: {e}")
        return pd.DataFrame()


# Save cleaned data to CSV and Parquet
def save_cleaned_data(df):
    local_now = datetime.now(ZoneInfo("Europe/Berlin"))
    timestamp = local_now.strftime("%d%m%Y_%H%M%S")
    csv_path = f"data/cleaned/cleaned_weather_{timestamp}.csv"
    parquet_path = f"data/cleaned/cleaned_weather_{timestamp}.parquet"

    try:
        df.to_csv(csv_path, index=False)
        logging.info(f"Cleaned data saved to CSV: {csv_path}")
    except Exception as e:
        logging.error(f"Failed to save cleaned data to CSV: {e}")

    try:
        df.to_parquet(parquet_path, index=False)
        logging.info(f"Cleaned data saved to Parquet: {parquet_path}")
    except Exception as e:
        logging.error(f"Failed to save cleaned data to Parquet: {e}")


if __name__ == "__main__":
    raw_data = load_raw_data(find_latest_file())
    df_clean = clean_data(raw_data, *get_location_info())
    save_cleaned_data(df_clean)

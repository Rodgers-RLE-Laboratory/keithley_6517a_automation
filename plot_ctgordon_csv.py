import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# === Configuration ===
FILE = 'ctgordon_20251015_10.csv'
DATA_FOLDER = '/Users/sfnagle/MIT Dropbox/Steven Nagle/Rodgers Lab Home/Projects/2025.10 ctgordon - chemical sensors/' + FILE
OUTPUT_HTML = DATA_FOLDER + ".html"
TIME_COLUMN = "time"       # adjust if needed
DATA_COLUMN = "value"      # adjust if needed
AVERAGE_WINDOW_SEC = 1  # 1/60 s = 16.666... ms (for 60 Hz)

# === Load data ===
df = pd.read_csv(DATA_FOLDER)

# Column inference (kept from your version)
if TIME_COLUMN not in df.columns:
    TIME_COLUMN = df.columns[0]
if DATA_COLUMN not in df.columns:
    DATA_COLUMN = df.columns[1]

# Ensure numeric types
df[TIME_COLUMN] = pd.to_numeric(df[TIME_COLUMN], errors="coerce")
df[DATA_COLUMN]  = pd.to_numeric(df[DATA_COLUMN],  errors="coerce")

# Clean and sort
df = df.dropna(subset=[TIME_COLUMN, DATA_COLUMN]).sort_values(TIME_COLUMN)

# Convert numeric seconds to datetime
t0 = pd.to_datetime(0, unit="s")
df["time_dt"] = pd.to_datetime(df[TIME_COLUMN], unit="s", origin=t0)

# Proper time-based rolling
window = pd.to_timedelta(AVERAGE_WINDOW_SEC, unit="s")
rolled = df.rolling(window=window, on="time_dt")

df["avg"] = rolled[DATA_COLUMN].mean()
df["min"] = rolled[DATA_COLUMN].min()
df["max"] = rolled[DATA_COLUMN].max()

# === Plot ===
fig = make_subplots(rows=1, cols=1)

# Raw data (faint background trace)
fig.add_trace(
    go.Scatter(
        x=df[TIME_COLUMN],
        y=df[DATA_COLUMN],
        mode="lines",
        name="Raw data",
        line=dict(color="lightgray", width=1),
        hoverinfo="skip",
    )
)

# Averaged data with hover showing local min/max
fig.add_trace(
    go.Scatter(
        x=df[TIME_COLUMN],
        y=df["avg"],
        mode="lines",
        name=f"Averaged ({AVERAGE_WINDOW_SEC:.6g} s window)",
        line=dict(width=2),
        hovertemplate=(
            "<b>Time:</b> %{x:.6f}s<br>"
            "<b>Average:</b> %{y:.6g}<br>"
            "<b>Local min:</b> %{customdata[0]:.6g}<br>"
            "<b>Local max:</b> %{customdata[1]:.6g}<extra></extra>"
        ),
        customdata=df[["min", "max"]].to_numpy(),
    )
)

fig.update_layout(
    title=f"{FILE} — Signal with {AVERAGE_WINDOW_SEC:.6g} s Time-Based Averaging",
    xaxis_title="Time (s)",
    yaxis_title=DATA_COLUMN,
    hovermode="x unified",
    template="plotly_white",
)

fig.show()
fig.write_html(OUTPUT_HTML, include_plotlyjs="cdn")
print(f"✅ Plot saved to {OUTPUT_HTML}")

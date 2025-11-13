# Keithley 6517A Communication Class

Python class for communicating with a Keithley 6517A Electrometer over RS-232 using PyVISA.

## Features

- **RS-232 Communication**: Direct serial communication with the instrument
- **1/60 s Averaging**: Enables instrument's built-in digital filter (16.67 ms averaging)
- **Fast Polling**: Collects measurements as quickly as possible while averaging is enabled
- **Flexible Duration**: Collect data for any specified time period (default: 5 seconds)
- **Interactive Plots**: Uses Plotly for rich, interactive data visualization
- **Multiple Functions**: Supports current, voltage, resistance, and charge measurements
- **Context Manager**: Automatic connection/disconnection handling
- **Data Export**: Save measurements to CSV and plots to HTML

## Requirements

All dependencies are already in `requirements.txt`:
- `pyvisa` (line 203)
- `pandas` (line 272)
- `plotly` (line 274)

## Quick Start

### Basic Usage

```python
from keithley_6517a import Keithley6517A

# Replace with your instrument's VISA resource name
RESOURCE = 'ASRL1::INSTR'  # Windows COM1
# RESOURCE = 'ASRL/dev/ttyUSB0::INSTR'  # Linux
# RESOURCE = 'ASRL/dev/tty.usbserial::INSTR'  # macOS

# Collect and plot data (all-in-one)
with Keithley6517A(RESOURCE) as keithley:
    df = keithley.measure_and_plot(
        duration=5.0,           # 5 seconds
        function='CURR',        # Current measurement
        range_value='AUTO',     # Auto-ranging
        save_html='plot.html',  # Save interactive plot
        save_csv='data.csv'     # Save raw data
    )
```

### Finding Your Instrument's Resource Name

```python
import pyvisa

rm = pyvisa.ResourceManager()
print(rm.list_resources())  # Lists all available VISA resources
```

Common patterns:
- **Windows**: `ASRL1::INSTR`, `ASRL2::INSTR`, etc. (COM1, COM2, ...)
- **Linux**: `ASRL/dev/ttyUSB0::INSTR`, `ASRL/dev/ttyS0::INSTR`
- **macOS**: `ASRL/dev/tty.usbserial::INSTR`, `ASRL/dev/cu.usbserial::INSTR`

## Detailed Usage

### Manual Control

```python
from keithley_6517a import Keithley6517A

keithley = Keithley6517A('ASRL1::INSTR', baud_rate=9600, timeout=5000)

try:
    # Connect
    keithley.connect()

    # Configure measurement (1/60 s averaging is ON by default)
    keithley.configure_measurement(
        function='CURR',        # CURR, VOLT, RES, or CHAR
        range_value='AUTO',     # AUTO or specific value
        averaging_on=True       # Enable 1/60 s digital filter
    )

    # Single reading
    value = keithley.read_measurement()
    print(f"Current: {value} A")

    # Collect data
    df = keithley.collect_data(duration=10.0, function='CURR')

    # Plot data
    keithley.plot_data(df,
                      title="My Measurement",
                      ylabel="Current (A)",
                      save_html="output.html",
                      rolling_window_sec=1.0)

finally:
    keithley.disconnect()
```

### Different Measurement Functions

```python
with Keithley6517A(RESOURCE) as keithley:
    # Current measurement (Amps)
    df_current = keithley.collect_data(duration=5.0, function='CURR')

    # Voltage measurement (Volts)
    df_voltage = keithley.collect_data(duration=5.0, function='VOLT')

    # Resistance measurement (Ohms)
    df_resistance = keithley.collect_data(duration=5.0, function='RES')

    # Charge measurement (Coulombs)
    df_charge = keithley.collect_data(duration=5.0, function='CHAR')
```

### Fixed Range (Faster Than Auto-Range)

```python
with Keithley6517A(RESOURCE) as keithley:
    # Use fixed 2 nA range for faster measurements
    df = keithley.measure_and_plot(
        duration=5.0,
        function='CURR',
        range_value='2e-9'  # 2 nA range
    )
```

## Class Methods

### `__init__(resource_name, baud_rate=9600, timeout=5000)`
Initialize the instrument interface.

### `connect()`
Establish RS-232 connection to the instrument.

### `disconnect()`
Close the connection.

### `configure_measurement(function='CURR', range_value='AUTO', averaging_on=True)`
Configure measurement settings including the 1/60 s digital filter.

### `read_measurement() -> float`
Read a single measurement value.

### `collect_data(duration=5.0, function='CURR', range_value='AUTO') -> pd.DataFrame`
Collect measurements for specified duration (default: 5 seconds).
Returns DataFrame with columns: `time` (s), `value`, `timestamp`.

### `plot_data(df, title, ylabel, save_html=None, rolling_window_sec=1.0)`
Create interactive Plotly visualization with raw data and rolling average.

### `measure_and_plot(duration=5.0, function='CURR', range_value='AUTO', save_html=None, save_csv=None) -> pd.DataFrame`
Convenience method: collect data, save files, and plot in one call.

## How It Works

### 1/60 s Averaging Mode

The Keithley 6517A's digital filter averages measurements over 1/60 second (16.67 ms) when enabled. This provides:
- **Noise reduction**: Filters out 60 Hz line noise
- **Stable readings**: Reduces random fluctuations
- **Fast enough**: ~60 readings/second maximum theoretical rate

The actual polling rate depends on:
- RS-232 baud rate (default: 9600)
- Communication overhead
- Instrument processing time

Typical rates: **30-50 readings/second** with averaging enabled.

### Commands Used

The class uses these Keithley 6517A SCPI commands:
```
*IDN?                    - Query instrument ID
*RST                     - Reset to default state
*CLS                     - Clear error queue
FUNC "CURR"              - Set function (CURR/VOLT/RES/CHAR)
CURR:RANG:AUTO ON        - Enable auto-ranging
CURR:AVER:TCON REP       - Repeating average filter
CURR:AVER:COUN 1         - 1 reading average (1/60 s)
CURR:AVER ON             - Enable averaging
FORM:ELEM READ           - ASCII data format
READ?                    - Trigger and read measurement
```

## Plotting

The `plot_data()` method creates an interactive Plotly graph with:
- **Raw data trace**: Semi-transparent line showing all measurements with 1/60 s averaging
- **Rolling average**: Darker line showing smoothed data over specified window (default: 1 s)
- **Hover info**: Displays time, value, and rolling statistics (mean, std, min, max)
- **Summary statistics**: Mean and standard deviation in plot title

## Troubleshooting

### "Could not open resource"
- Check that the instrument is powered on and connected
- Verify the resource name using `pyvisa.ResourceManager().list_resources()`
- Ensure no other software is using the serial port
- Check cable connections and USB-to-serial adapter if used

### Timeout errors
- Increase timeout: `Keithley6517A(RESOURCE, timeout=10000)` (10 seconds)
- Check baud rate matches instrument settings
- Verify instrument is not in local mode (press REMOTE button)

### Slow data collection rate
- Use fixed range instead of AUTO: `range_value='2e-9'`
- Increase baud rate if instrument supports it
- Check for serial communication errors in system logs

### "Module not found" errors
- Install dependencies: `pip install pyvisa pandas plotly`
- For VISA backend: `pip install pyvisa-py` (pure Python backend)
- Or install NI-VISA drivers from National Instruments

## References

- [Keithley 6517A User Manual](https://www.tek.com/en/products/keithley)
- [PyVISA Documentation](https://pyvisa.readthedocs.io/)
- [Plotly Python Documentation](https://plotly.com/python/)

"""
Keithley 6517A Electrometer Communication Class

This module provides a class for communicating with a Keithley 6517A
electrometer over RS-232, collecting measurements with 1/60 s averaging,
and plotting the results using Plotly.
"""

import time
import pyvisa
import pyvisa.resources
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import List, Tuple, Optional, cast
from datetime import datetime
import math


def eng_notation(value: float, sigfigs: int = 7) -> str:
    """
    Format a number in engineering notation with specified significant figures.

    Engineering notation uses exponents that are multiples of 3.

    Args:
        value: Number to format
        sigfigs: Number of significant figures (default: 7)

    Returns:
        String in engineering notation (e.g., "1.234567e+06")
    """
    if value == 0 or not math.isfinite(value):
        return f"{value:.{sigfigs-1}e}"

    # Get the exponent
    exponent = math.floor(math.log10(abs(value)))

    # Round to nearest multiple of 3 for engineering notation
    eng_exponent = 3 * math.floor(exponent / 3)

    # Calculate mantissa
    mantissa = value / (10 ** eng_exponent)

    # Format with appropriate significant figures
    # Adjust decimal places based on mantissa magnitude
    if abs(mantissa) >= 100:
        decimals = sigfigs - 3
    elif abs(mantissa) >= 10:
        decimals = sigfigs - 2
    else:
        decimals = sigfigs - 1

    decimals = max(0, decimals)  # Ensure non-negative

    return f"{mantissa:.{decimals}f}e{eng_exponent:+03d}"


class Keithley6517A:
    """
    Interface for Keithley 6517A Electrometer over RS-232.

    Supports fast measurement polling with instrument averaging enabled
    and data visualization using Plotly.
    """

    def __init__(self, resource_name: str, baud_rate: int = 9600,
                 timeout: int = 5000):
        """
        Initialize connection to Keithley 6517A.

        Args:
            resource_name: VISA resource name (e.g., 'ASRL/dev/ttyUSB0::INSTR'
                          or 'ASRL1::INSTR' on Windows)
            baud_rate: Serial baud rate (default: 9600)
            timeout: Communication timeout in milliseconds (default: 5000)
        """
        self.resource_name = resource_name
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.instrument: Optional[pyvisa.resources.SerialInstrument] = None
        self.rm: Optional[pyvisa.ResourceManager] = None

    def _ensure_connected(self) -> pyvisa.resources.SerialInstrument:
        """Ensure instrument is connected and return it for type narrowing."""
        if self.instrument is None:
            raise RuntimeError("Instrument not connected. Call connect() first.")
        return self.instrument

    def check_errors(self) -> str:
        """
        Check and print any instrument errors.

        Returns:
            Error string from instrument
        """
        instr = self._ensure_connected()
        try:
            error = instr.query(':SYST:ERR?')
            if not error.startswith('0,'):
                print(f"⚠️  Instrument error: {error.strip()}")
            return error.strip()
        except Exception as e:
            error_msg = f"Error checking instrument status: {e}"
            print(f"⚠️  {error_msg}")
            return error_msg

    def flush_buffer(self):
        """
        Flush any pending data from the input buffer.

        This prevents RS-232 buffer overflow (error 807) by clearing
        any unexpected or unread data from the serial buffer.
        """
        instr = self._ensure_connected()
        flushed_count = 0
        try:
            # Try to read any pending data, with short timeout
            original_timeout = instr.timeout
            instr.timeout = 100  # 100ms timeout for flushing

            while flushed_count < 10:  # Limit iterations to prevent infinite loop
                try:
                    data = instr.read()
                    flushed_count += 1
                except:
                    break  # No more data to read

            instr.timeout = original_timeout

            if flushed_count > 0:
                print(f"Flushed {flushed_count} pending message(s) from buffer")

        except Exception as e:
            print(f"⚠️  Error flushing buffer: {e}")

    def abort_measurement(self):
        """
        Abort any measurement in progress and clear the instrument state.

        This should be called between measurement sequences to ensure
        the instrument is ready for new commands.
        """
        instr = self._ensure_connected()
        try:
            # Abort any measurement in progress
            instr.write(':ABOR')
            time.sleep(0.1)

            # Clear status and errors
            instr.write('*CLS')
            time.sleep(0.1)

            # Flush any pending output
            self.flush_buffer()

            # Verify no errors remain
            error = self.check_errors()
            if not error.startswith('0,'):
                print(f"⚠️  Errors after abort: {error}")

        except Exception as e:
            print(f"⚠️  Error aborting measurement: {e}")

    def connect(self):
        """Establish connection to the instrument."""
        try:
            self.rm = pyvisa.ResourceManager()
            # Cast to SerialInstrument for proper attribute access
            self.instrument = cast(
                pyvisa.resources.SerialInstrument,
                self.rm.open_resource(self.resource_name)
            )

            # Configure serial communication
            self.instrument.baud_rate = self.baud_rate
            self.instrument.timeout = self.timeout
            self.instrument.read_termination = '\n'
            self.instrument.write_termination = '\n'

            # Clear any pending data in buffers
            print("Clearing communication buffers...")
            try:
                self.instrument.clear()
            except:
                pass

            # Try to clear any stuck state with Device Clear
            try:
                self.instrument.write('*CLS')
                time.sleep(0.2)
            except:
                pass

            # Try to flush any pending output
            try:
                self.instrument.read()
            except:
                pass  # Expected to fail if no data

            # Get instrument ID (with retry)
            print("Connecting to instrument...")
            for attempt in range(3):
                try:
                    idn = self.instrument.query('*IDN?')
                    print(f"Connected to: {idn.strip()}")
                    break
                except Exception as e:
                    if attempt < 2:
                        print(f"Connection attempt {attempt+1} failed, retrying...")
                        time.sleep(0.5)
                        try:
                            self.instrument.clear()
                        except:
                            pass
                    else:
                        raise e

            # Reset to known state
            self.instrument.write('*RST')
            time.sleep(1.0)  # Give instrument time to reset

            # Clear any errors
            self.instrument.write('*CLS')
            time.sleep(0.1)

        except Exception as e:
            raise ConnectionError(f"Failed to connect to instrument: {e}")

    def disconnect(self):
        """Close connection to the instrument."""
        if self.instrument:
            self.instrument.close()
        if self.rm:
            self.rm.close()
        print("Disconnected from instrument")

    def set_zero_check(self, enabled: bool):
        """
        Control zero check (measurement circuit connection).

        Args:
            enabled: True to enable zero check (disconnect meter),
                    False to disable (connect meter for measurements)
        """
        instr = self._ensure_connected()
        state = 'ON' if enabled else 'OFF'
        instr.write(f':SYST:ZCH {state}')
        print(f"Zero check: {state} (meter {'disconnected' if enabled else 'connected'})")
        self.check_errors()

    def configure_voltage_source(self, voltage: float):
        """
        Configure voltage source level (does NOT enable output).

        IMPORTANT: This only sets the voltage level. Use enable_output(True)
        to actually turn on the output. This separation is for safety since
        the instrument can output up to 1000V.

        Args:
            voltage: Source voltage in volts (-1000 to +1000)
        """
        instr = self._ensure_connected()

        # Set voltage source range and level
        instr.write(f':SOUR:VOLT:RANG {abs(voltage)}')
        time.sleep(0.5)  # Let command process
        instr.write(f':SOUR:VOLT {voltage}')
        time.sleep(0.5)

        # Enable measure connection (V-Source LO to Ammeter LO)
        instr.write(':SOUR:VOLT:MCON ON')
        time.sleep(0.5)

        print(f"Voltage source configured: {voltage} V")

    def enable_output(self, enable: bool = True):
        """
        Enable or disable the voltage source output.

        SAFETY WARNING: This turns on the high voltage output. Ensure all
        connections are secure and personnel are clear before enabling.
        The instrument can output up to 1000V.

        Args:
            enable: True to turn output ON, False to turn output OFF
        """
        instr = self._ensure_connected()

        state = 'ON' if enable else 'OFF'
        instr.write(f':OUTP:STAT {state}')
        print(f"⚠️  Output: {state}")
        self.check_errors()

    def configure_measurement(self, function: str = 'CURR',
                            range_value: str = 'AUTO',
                            averaging_on: bool = True):
        """
        Configure measurement settings.

        Args:
            function: Measurement function ('CURR', 'VOLT', 'RES', 'CHAR')
            range_value: Measurement range ('AUTO' or specific value)
            averaging_on: Enable 1/60 s (16.67 ms) digital filter averaging
        """
        instr = self._ensure_connected()

        # Set measurement function
        instr.write(f':SENS:FUNC "{function}"')
        time.sleep(0.5)

        # Set range
        if range_value.upper() == 'AUTO':
            instr.write(f':SENS:{function}:RANG:AUTO ON')
        else:
            instr.write(f':SENS:{function}:RANG {range_value}')
            time.sleep(0.5)
            instr.write(f':SENS:{function}:RANG:AUTO OFF')
        time.sleep(0.5)

        # Configure averaging (digital filter)
        # The 6517A uses AVER:TCON (time control) for filtering
        if averaging_on:
            instr.write(f':SENS:{function}:AVER:TCON REP')  # Repeating average
            time.sleep(0.5)
            instr.write(f':SENS:{function}:AVER:COUN 1')    # 1 reading (1/60 s)
            time.sleep(0.5)
            instr.write(f':SENS:{function}:AVER ON')
            time.sleep(0.5)
            print(f"Averaging enabled: 1/60 s (16.67 ms) filter")
        else:
            instr.write(f':SENS:{function}:AVER OFF')
            time.sleep(0.5)
            print("Averaging disabled")

        # Set data format to ASCII with only reading value (no timestamp, status, etc.)
        instr.write(':FORM:ELEM READ')
        time.sleep(0.5)

        # Flush buffer to prevent overflow after configuration
        self.flush_buffer()

        # Configure trigger system for immediate triggering by default
        # This ensures measurements work whether using READ? or INIT/FETC pattern
        self.configure_trigger('IMM')

    def configure_trigger(self, source: str = 'IMM', count: int = 1,
                         delay: float = 0.0):
        """
        Configure trigger subsystem.

        Args:
            source: Trigger source - 'IMM' (immediate/internal), 'BUS' (software),
                   'TIM' (timer), 'TLINK' (trigger link), 'EXT' (external)
            count: Number of trigger events (1-9999 or INF)
            delay: Delay after trigger before measurement in seconds (0-999999.999)
        """
        instr = self._ensure_connected()

        # Set trigger source
        instr.write(f':TRIG:SOUR {source}')
        time.sleep(0.5)
        print(f"Trigger source: {source}")

        # Set trigger count
        if count == float('inf'):
            instr.write(':TRIG:COUN INF')
        else:
            instr.write(f':TRIG:COUN {count}')
        time.sleep(0.5)
        print(f"Trigger count: {count}")

        # Set trigger delay
        instr.write(f':TRIG:DEL {delay}')
        time.sleep(0.5)
        if delay > 0:
            print(f"Trigger delay: {delay} s")

    def initiate_measurement(self):
        """
        Initiate a measurement (trigger).

        This arms the trigger system and initiates a measurement based on
        the configured trigger source. For immediate triggering, this will
        start the measurement immediately.
        """
        instr = self._ensure_connected()
        instr.write(':INIT')

    def fetch_measurement(self) -> float:
        """
        Fetch the last triggered measurement without initiating a new one.

        Returns:
            Measurement value as float
        """
        instr = self._ensure_connected()
        try:
            result = instr.query(':FETC?')
            result_str = result.strip()

            # Handle case where multiple data elements are returned
            # Format might be: "+1.234E+05NVDC,+0000159.631046secs,+00867rdng#"
            # We only want the first numeric value
            if ',' in result_str:
                # Multiple elements - take only the first (the reading)
                first_element = result_str.split(',')[0]
                # Remove any trailing non-numeric characters
                for i, char in enumerate(first_element):
                    if char.isalpha():
                        first_element = first_element[:i]
                        break
                return float(first_element)
            else:
                return float(result_str)
        except Exception as e:
            print(f"Error fetching measurement: {e}")
            return float('nan')

    def test_measurement(self) -> None:
        """
        Test measurement with detailed debugging output.

        This method performs a single measurement and prints diagnostic
        information to help troubleshoot any issues.
        """
        instr = self._ensure_connected()

        print("\n=== Measurement Test ===")

        # Check current function
        try:
            func = instr.query(':SENS:FUNC?')
            print(f"Current function: {func.strip()}")
        except Exception as e:
            print(f"Error querying function: {e}")

        # Check measurement range
        try:
            func_str = func.strip().strip('"')
            range_val = instr.query(f':SENS:{func_str}:RANG?')
            print(f"Current range: {range_val.strip()}")
            range_auto = instr.query(f':SENS:{func_str}:RANG:AUTO?')
            print(f"Auto range: {range_auto.strip()}")
        except Exception as e:
            print(f"Error querying range: {e}")

        # Check zero check status
        try:
            zcheck = instr.query(':SYST:ZCH?')
            print(f"Zero check: {zcheck.strip()}")
        except Exception as e:
            print(f"Error querying zero check: {e}")

        # Check voltage source and output status
        try:
            vsource_level = instr.query(':SOUR:VOLT?')
            print(f"Voltage source level: {vsource_level.strip()} V")
            output_state = instr.query(':OUTP:STAT?')
            print(f"Output state: {output_state.strip()}")
        except Exception as e:
            print(f"Error querying voltage source/output: {e}")

        # Check trigger source
        try:
            trig_src = instr.query(':TRIG:SOUR?')
            print(f"Trigger source: {trig_src.strip()}")
        except Exception as e:
            print(f"Error querying trigger source: {e}")

        # Check for errors
        print("\nChecking for errors...")
        self.check_errors()

        # Try READ? command
        print("\nTrying READ? command...")
        try:
            result = instr.query('READ?')
            print(f"READ? result: {result.strip()}")
            value = float(result.strip())
            print(f"Parsed value: {value}")
        except Exception as e:
            print(f"Error with READ?: {e}")
            self.check_errors()

        # Try INIT/FETCH pattern
        print("\nTrying INIT/FETCH pattern...")
        try:
            instr.write(':INIT')
            print("INIT sent")
            self.check_errors()

            # Wait for measurement to complete
            import time
            time.sleep(0.1)

            result = instr.query(':FETC?')
            print(f"FETCH? result: {result.strip()}")
            value = float(result.strip())
            print(f"Parsed value: {value}")
        except Exception as e:
            print(f"Error with INIT/FETCH: {e}")
            self.check_errors()

        print("\n=== Test Complete ===\n")

    def read_measurement(self, explicit_trigger: bool = False) -> float:
        """
        Read a single measurement value.

        Args:
            explicit_trigger: If True, use explicit INIT/FETCH pattern with separate
                            initiate_measurement() and fetch_measurement() calls.
                            If False (default), use READ? which combines trigger
                            and fetch in a single command.

        Returns:
            Measurement value as float
        """
        instr = self._ensure_connected()
        try:
            if explicit_trigger:
                # Use explicit INIT/FETCH pattern (separate commands)
                self.initiate_measurement()
                return self.fetch_measurement()
            else:
                # Use READ? (combined trigger and fetch in one command)
                result = instr.query('READ?')
                result_str = result.strip()

                # Handle case where multiple data elements are returned
                if ',' in result_str:
                    first_element = result_str.split(',')[0]
                    # Remove any trailing non-numeric characters
                    for i, char in enumerate(first_element):
                        if char.isalpha():
                            first_element = first_element[:i]
                            break
                    return float(first_element)
                else:
                    return float(result_str)
        except Exception as e:
            print(f"Error reading measurement: {e}")
            return float('nan')

    def collect_data(self, duration: float = 5.0,
                    function: str = 'CURR',
                    range_value: str = 'AUTO',
                    explicit_trigger: bool = True) -> pd.DataFrame:
        """
        Collect measurement data for a specified duration.

        Args:
            duration: Collection time in seconds (default: 5.0)
            function: Measurement function ('CURR', 'VOLT', 'RES', 'CHAR')
            range_value: Measurement range ('AUTO' or specific value)
            explicit_trigger: Use explicit INIT/FETCH pattern (default: True)

        Returns:
            pandas DataFrame with columns: 'time' (seconds), 'value',
            'timestamp' (absolute time)
        """
        # Configure instrument (including trigger system)
        self.configure_measurement(function, range_value, averaging_on=True)

        print(f"\nCollecting data for {duration} seconds...")
        print("Press Ctrl+C to stop early\n")

        times = []
        values = []
        timestamps = []
        ranges = []

        start_time = time.time()

        try:
            # Get the measurement function for range queries
            instr = self._ensure_connected()

            while (time.time() - start_time) < duration:
                t = time.time() - start_time
                value = self.read_measurement(explicit_trigger=explicit_trigger)
                timestamp = datetime.now()

                # Query current range
                try:
                    range_val = instr.query(f':SENS:{function}:RANG?')
                    current_range = float(range_val.strip())
                except:
                    current_range = float('nan')

                times.append(t)
                values.append(value)
                timestamps.append(timestamp)
                ranges.append(current_range)

                # Print progress
                print(f"t = {t:.3f} s, value = {eng_notation(value)} Ω", end='\r')

                # Delay for ~2 Hz sample rate (0.5s between measurements)
                time.sleep(0.5)

        except KeyboardInterrupt:
            print("\n\nData collection interrupted by user")

        elapsed = time.time() - start_time
        num_readings = len(times)

        print(f"\nCollection complete!")
        print(f"Duration: {elapsed:.2f} s")
        print(f"Readings collected: {num_readings}")
        print(f"Average rate: {num_readings/elapsed:.1f} readings/s")

        # Create DataFrame
        df = pd.DataFrame({
            'time': times,
            'value': values,
            'timestamp': timestamps,
            'range': ranges
        })

        return df

    def plot_data(self, df: pd.DataFrame,
                 title: str = "Keithley 6517A Measurement",
                 ylabel: str = "Value",
                 save_html: Optional[str] = None,
                 rolling_window_sec: float = 1.0):
        """
        Plot collected measurement data using Plotly.

        Args:
            df: DataFrame with 'time' and 'value' columns
            title: Plot title
            ylabel: Y-axis label
            save_html: Optional filename to save interactive HTML plot
            rolling_window_sec: Window size for rolling average display (seconds)
        """
        # Calculate rolling statistics
        df_clean = df.dropna(subset=['time', 'value']).copy()

        if len(df_clean) < 2:
            print("Not enough data points to plot")
            return

        # Convert time to datetime for proper time-based rolling
        t0 = pd.to_datetime(0, unit='s')
        df_clean['time_dt'] = pd.to_datetime(df_clean['time'], unit='s', origin=t0)

        # Calculate rolling statistics
        window = pd.to_timedelta(rolling_window_sec, unit='s')
        rolled = df_clean.rolling(window=window, on='time_dt', min_periods=1)

        df_clean['avg'] = rolled['value'].mean()
        df_clean['min'] = rolled['value'].min()
        df_clean['max'] = rolled['value'].max()
        df_clean['std'] = rolled['value'].std()

        # Create plot
        fig = make_subplots(rows=1, cols=1)

        # Format values for hover display
        df_clean['value_formatted'] = df_clean['value'].apply(eng_notation)

        # Raw data (semi-transparent)
        # Check if range column exists
        if 'range' in df_clean.columns:
            df_clean['range_formatted'] = df_clean['range'].apply(lambda x: eng_notation(x) if pd.notna(x) else 'N/A')
            fig.add_trace(
                go.Scatter(
                    x=df_clean['time'],
                    y=df_clean['value'],
                    mode='lines',
                    name='Raw data (1/60 s averaging)',
                    line=dict(color='lightblue', width=1),
                    customdata=df_clean[['value_formatted', 'range_formatted']].to_numpy(),
                    hovertemplate=(
                        "<b>Time:</b> %{x:.4f} s<br>"
                        "<b>Value:</b> %{customdata[0]}<br>"
                        "<b>Range:</b> %{customdata[1]}<extra></extra>"
                    ),
                )
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=df_clean['time'],
                    y=df_clean['value'],
                    mode='lines',
                    name='Raw data (1/60 s averaging)',
                    line=dict(color='lightblue', width=1),
                    customdata=df_clean[['value_formatted']].to_numpy(),
                    hovertemplate=(
                        "<b>Time:</b> %{x:.4f} s<br>"
                        "<b>Value:</b> %{customdata[0]}<extra></extra>"
                    ),
                )
            )

        # Rolling average - format statistics for hover
        df_clean['avg_formatted'] = df_clean['avg'].apply(eng_notation)
        df_clean['std_formatted'] = df_clean['std'].apply(lambda x: eng_notation(x) if pd.notna(x) else 'N/A')
        df_clean['min_formatted'] = df_clean['min'].apply(eng_notation)
        df_clean['max_formatted'] = df_clean['max'].apply(eng_notation)

        fig.add_trace(
            go.Scatter(
                x=df_clean['time'],
                y=df_clean['avg'],
                mode='lines',
                name=f'Rolling average ({rolling_window_sec} s)',
                line=dict(color='darkblue', width=2),
                hovertemplate=(
                    "<b>Time:</b> %{x:.4f} s<br>"
                    "<b>Average:</b> %{customdata[0]}<br>"
                    "<b>Std Dev:</b> %{customdata[1]}<br>"
                    "<b>Min:</b> %{customdata[2]}<br>"
                    "<b>Max:</b> %{customdata[3]}<extra></extra>"
                ),
                customdata=df_clean[['avg_formatted', 'std_formatted', 'min_formatted', 'max_formatted']].to_numpy(),
            )
        )

        # Calculate statistics for title
        mean_val = df_clean['value'].mean()
        std_val = df_clean['value'].std()

        fig.update_layout(
            title=f"{title}<br><sub>Mean: {eng_notation(mean_val)}, Std: {eng_notation(std_val)}</sub>",
            xaxis_title="Time (s)",
            yaxis_title=ylabel,
            hovermode='x unified',
            template='plotly_white',
            showlegend=True,
        )

        # Show plot
        fig.show()

        # Save if requested
        if save_html:
            fig.write_html(save_html, include_plotlyjs='cdn')
            print(f"Plot saved to {save_html}")

    def measure_and_plot(self, duration: float = 5.0,
                        function: str = 'CURR',
                        range_value: str = 'AUTO',
                        save_html: Optional[str] = None,
                        save_csv: Optional[str] = None) -> pd.DataFrame:
        """
        Convenience method to collect data and plot in one call.

        Args:
            duration: Collection time in seconds (default: 5.0)
            function: Measurement function ('CURR', 'VOLT', 'RES', 'CHAR')
            range_value: Measurement range ('AUTO' or specific value)
            save_html: Optional filename to save interactive HTML plot
            save_csv: Optional filename to save data as CSV

        Returns:
            pandas DataFrame with collected data
        """
        # Collect data
        df = self.collect_data(duration, function, range_value)

        # Save CSV if requested
        if save_csv:
            df.to_csv(save_csv, index=False)
            print(f"Data saved to {save_csv}")

        # Determine ylabel based on function
        ylabel_map = {
            'CURR': 'Current (A)',
            'VOLT': 'Voltage (V)',
            'RES': 'Resistance (Ω)',
            'CHAR': 'Charge (C)'
        }
        ylabel = ylabel_map.get(function.upper(), 'Value')

        # Plot data
        self.plot_data(df,
                      title=f"Keithley 6517A {function.upper()} Measurement",
                      ylabel=ylabel,
                      save_html=save_html)

        return df

    @staticmethod
    def plot_saved_data(csv_file: str, save_html: Optional[str] = None,
                       title: Optional[str] = None):
        """
        Plot previously saved measurement data from CSV file.

        This method loads a CSV file saved by measure_and_plot() or main()
        and plots it using the same style as plot_voltage_sweep(), with
        statistics (mean, median, std, stderr) for each trace and overall.

        Args:
            csv_file: Path to CSV file with columns: time, value, timestamp,
                     range, voltage, direction, sequence
            save_html: Optional filename to save interactive HTML plot
            title: Optional custom title for the plot
        """
        import numpy as np

        # Load the CSV file
        df = pd.read_csv(csv_file)

        # Check if this is a voltage sweep (multiple sequences) or single measurement
        if 'sequence' in df.columns and df['sequence'].nunique() > 1:
            # Multi-sequence voltage sweep
            voltage_sequence = df.groupby('sequence')['voltage'].first().tolist()

            # Calculate statistics for each trace
            print("\n" + "="*70)
            print("Statistics by Trace:")
            print("="*70)

            trace_stats = []
            for seq_idx in sorted(df['sequence'].unique()):
                subset = df[df['sequence'] == seq_idx]
                voltage = subset['voltage'].iloc[0]
                direction = subset['direction'].iloc[0]

                mean_val = subset['value'].mean()
                median_val = subset['value'].median()
                std_val = subset['value'].std()
                stderr_val = std_val / np.sqrt(len(subset))
                n_points = len(subset)

                trace_stats.append({
                    'sequence': seq_idx,
                    'voltage': voltage,
                    'direction': direction,
                    'n': n_points,
                    'mean': mean_val,
                    'median': median_val,
                    'std': std_val,
                    'stderr': stderr_val
                })

                print(f"\nTrace {seq_idx+1}: {voltage}V {direction}")
                print(f"  N points:      {n_points}")
                print(f"  Mean:          {eng_notation(mean_val)}")
                print(f"  Median:        {eng_notation(median_val)}")
                print(f"  Std Dev:       {eng_notation(std_val)}")
                print(f"  Std Error:     {eng_notation(stderr_val)}")

            # Calculate overall statistics
            print("\n" + "="*70)
            print("Overall Statistics (All Traces Combined):")
            print("="*70)

            overall_mean = df['value'].mean()
            overall_median = df['value'].median()
            overall_std = df['value'].std()
            overall_stderr = overall_std / np.sqrt(len(df))

            print(f"  N points:      {len(df)}")
            print(f"  Mean:          {eng_notation(overall_mean)}")
            print(f"  Median:        {eng_notation(overall_median)}")
            print(f"  Std Dev:       {eng_notation(overall_std)}")
            print(f"  Std Error:     {eng_notation(overall_stderr)}")
            print("="*70 + "\n")

            # Generate default title if not provided
            if title is None:
                voltages_str = ', '.join([f"{v}V" for v in sorted(set(voltage_sequence))])
                title = f"Keithley 6517A Voltage Sweep: {voltages_str}"

            # Add overall statistics to title
            title = (f"{title}<br>"
                    f"<sub>Overall: Mean={eng_notation(overall_mean)}, "
                    f"Median={eng_notation(overall_median)}, "
                    f"StdDev={eng_notation(overall_std)}, "
                    f"StdErr={eng_notation(overall_stderr)}</sub>")

            # Use the voltage sweep plotting function with statistics
            plot_voltage_sweep(df, voltage_sequence, save_html=save_html,
                             title=title, trace_stats=trace_stats)
        else:
            # Single measurement - use the simpler plot_data style
            keithley = Keithley6517A('')  # Create dummy instance for method access

            # Calculate statistics
            mean_val = df['value'].mean()
            median_val = df['value'].median()
            std_val = df['value'].std()
            stderr_val = std_val / np.sqrt(len(df))

            print("\n" + "="*70)
            print("Statistics:")
            print("="*70)
            print(f"  N points:      {len(df)}")
            print(f"  Mean:          {eng_notation(mean_val)}")
            print(f"  Median:        {eng_notation(median_val)}")
            print(f"  Std Dev:       {eng_notation(std_val)}")
            print(f"  Std Error:     {eng_notation(stderr_val)}")
            print("="*70 + "\n")

            # Generate default title if not provided
            if title is None:
                if 'voltage' in df.columns:
                    voltage = df['voltage'].iloc[0]
                    title = f"Keithley 6517A Measurement at {voltage}V"
                else:
                    title = "Keithley 6517A Measurement"

            # Determine ylabel from data range
            if mean_val > 1e6:
                ylabel = "Resistance (Ω)"
            elif mean_val < 1e-3:
                ylabel = "Current (A)"
            else:
                ylabel = "Value"

            keithley.plot_data(df, title=title, ylabel=ylabel, save_html=save_html)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


def main():
    """
    Main function to run the Keithley 6517A measurement script.

    This example measures resistance at multiple voltages (sweep up then down)
    and plots all data on a single graph.
    """
    # Configure your instrument's VISA resource name
    # Examples:
    #   Windows: 'ASRL1::INSTR', 'ASRL3::INSTR'
    #   Linux: 'ASRL/dev/ttyUSB0::INSTR'
    #   macOS: 'ASRL/dev/tty.usbserial::INSTR'

    RESOURCE_NAME = 'ASRL/dev/tty.usbserial-110::INSTR'  # Change this to match your system

    # Voltage sweep configuration
    # Just 10 repeats at 50V
    voltage_sequence = [50] * 5
    # Results in: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50]

    measurement_duration = 60.0  # seconds per voltage level

    # Storage for all measurements
    all_data = []

    # Use context manager for automatic connect/disconnect
    with Keithley6517A(RESOURCE_NAME) as keithley:
        # Disable zero check (connect meter)
        keithley.set_zero_check(False)

        # Enable high voltage output
        keithley.enable_output(True)

        print(f"\n{'='*60}")
        print(f"Voltage Sweep: {voltage_sequence}")
        print(f"Measurement duration: {measurement_duration} s per voltage")
        print(f"{'='*60}\n")

        # Loop through voltage sequence
        for i, voltage in enumerate(voltage_sequence):
            # All measurements are repeats at 50V
            direction = f"#{i+1}"  # Repeat number

            print(f"\n{'='*60}")
            print(f"[{i+1}/{len(voltage_sequence)}] Repeat {i+1}: {voltage} V")
            print(f"{'='*60}")

            # Delay between voltage changes to let previous operations complete
            if i > 0:
                time.sleep(0.5)
                # Flush any pending data from buffer to prevent overflow
                keithley.flush_buffer()

            # Configure voltage source
            keithley.configure_voltage_source(voltage)

            # Wait for voltage to settle
            time.sleep(0.5)

            # Verify output is ON and check instrument status
            try:
                instr = keithley._ensure_connected()
                output_check = instr.query(':OUTP:STAT?')
                voltage_check = instr.query(':SOUR:VOLT?')
                zcheck = instr.query(':SYST:ZCH?')
                range_check = instr.query(':SENS:RES:RANG?')
                range_auto = instr.query(':SENS:RES:RANG:AUTO?')

                print(f"Output state: {output_check.strip()} (1=ON, 0=OFF)")
                print(f"Zero check: {zcheck.strip()} (0=OFF/connected, 1=ON/disconnected)")
                print(f"Voltage level: {float(voltage_check.strip()):.1f} V")
                print(f"Resistance range: {float(range_check.strip()):.3g} Ω (Auto: {range_auto.strip()})")

                if output_check.strip() != '1':
                    print("⚠️  WARNING: Output is OFF! Turning it on...")
                    keithley.enable_output(True)
                    time.sleep(1.0)

                if zcheck.strip() != '0':
                    print("⚠️  WARNING: Zero check is ON (meter disconnected)! Disabling...")
                    keithley.set_zero_check(False)
                    time.sleep(1.0)

            except Exception as e:
                print(f"⚠️  Warning: Could not verify status: {e}")
                print(f"Continuing with voltage {voltage}V...")

            # Collect data at this voltage
            try:
                df = keithley.collect_data(
                    duration=measurement_duration,
                    function='RES',
                    range_value='AUTO',
                    explicit_trigger=True
                )

                # Add voltage and direction labels to the data
                df['voltage'] = voltage
                df['direction'] = direction
                df['sequence'] = i

                # Store in list
                all_data.append(df)

                print(f"Mean resistance: {eng_notation(df['value'].mean())} Ω")
                print(f"Std deviation: {eng_notation(df['value'].std())} Ω")

                # Flush buffer after collection to prevent buildup
                keithley.flush_buffer()

            except Exception as e:
                print(f"⚠️  ERROR during data collection at {voltage}V: {e}")
                print(f"Skipping this voltage level...")
                keithley.flush_buffer()
                time.sleep(1.0)  # Give instrument time to recover
                continue

        # Turn off voltage source output
        print(f"\n{'='*60}")
        print("Shutting down...")
        print(f"{'='*60}")
        keithley.enable_output(False)
        keithley.set_zero_check(True)

        # Check if we have any data
        if not all_data:
            print("⚠️  ERROR: No data collected! All measurements failed.")
            return

        # Combine all data
        combined_df = pd.concat(all_data, ignore_index=True)

        # Save combined data
        combined_df.to_csv('keithley_voltage_sweep.csv', index=False)
        print(f"\nCombined data saved to keithley_voltage_sweep.csv")

        # Summary
        print(f"\n{'='*60}")
        print(f"Collected {len(all_data)} out of {len(voltage_sequence)} voltage levels")
        print(f"Total readings: {len(combined_df)}")
        print(f"{'='*60}")

        # Create multi-voltage plot
        plot_voltage_sweep(combined_df, voltage_sequence, save_html='keithley_voltage_sweep.html')

        print(f"\n{'='*60}")
        print("Measurement complete!")
        print(f"{'='*60}\n")


def plot_voltage_sweep(df: pd.DataFrame, voltage_sequence: list,
                       save_html: Optional[str] = None, title: Optional[str] = None,
                       trace_stats: Optional[list] = None):
    """
    Plot resistance measurements from voltage sweep with dual y-axes.

    Left y-axis: Absolute resistance values
    Right y-axis: Difference from overall mean

    Args:
        df: DataFrame with 'time', 'value', 'voltage', 'direction', 'sequence' columns
        voltage_sequence: List of voltages in measurement order
        save_html: Optional filename to save interactive HTML plot
        title: Optional custom title for the plot
        trace_stats: Optional list of dicts with statistics for each trace
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # Calculate overall mean for difference calculation
    overall_mean = df['value'].mean()

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Color scheme - 10 colors for 10 repeats at 50V
    colors = ['red', 'orangered', 'darkorange', 'orange', 'coral',
              'tomato', 'lightsalmon', 'salmon', 'indianred', 'crimson']

    # Create a lookup dict for trace stats if provided
    stats_lookup = {}
    if trace_stats:
        for stat in trace_stats:
            stats_lookup[stat['sequence']] = stat

    # Plot each voltage level
    for seq_idx in df['sequence'].unique():
        subset = df[df['sequence'] == seq_idx].copy()
        voltage = subset['voltage'].iloc[0]
        direction = subset['direction'].iloc[0]

        # Use color based on sequence index (0-9)
        color = colors[seq_idx] if seq_idx < len(colors) else 'red'

        # Calculate difference from overall mean
        subset['diff_from_mean'] = subset['value'] - overall_mean

        # Format values for hover display
        subset['value_formatted'] = subset['value'].apply(eng_notation)
        subset['diff_formatted'] = subset['diff_from_mean'].apply(eng_notation)
        subset['range_formatted'] = subset['range'].apply(lambda x: eng_notation(x) if pd.notna(x) else 'N/A')

        # Build hover template with statistics if available
        if seq_idx in stats_lookup:
            stats = stats_lookup[seq_idx]
            hovertemplate = (
                f"<b>{voltage}V {direction}</b><br>"
                "<b>Time:</b> %{x:.3f} s<br>"
                "<b>Resistance:</b> %{customdata[0]} Ω<br>"
                "<b>Diff from Mean:</b> %{customdata[1]} Ω<br>"
                "<b>Range:</b> %{customdata[2]} Ω<br>"
                "<br><b>Trace Statistics:</b><br>"
                f"Mean: {eng_notation(stats['mean'])} Ω<br>"
                f"Median: {eng_notation(stats['median'])} Ω<br>"
                f"StdDev: {eng_notation(stats['std'])} Ω<br>"
                f"StdErr: {eng_notation(stats['stderr'])} Ω<br>"
                f"N: {stats['n']}<extra></extra>"
            )
        else:
            hovertemplate = (
                f"<b>{voltage}V {direction}</b><br>"
                "<b>Time:</b> %{x:.3f} s<br>"
                "<b>Resistance:</b> %{customdata[0]} Ω<br>"
                "<b>Diff from Mean:</b> %{customdata[1]} Ω<br>"
                "<b>Range:</b> %{customdata[2]} Ω<extra></extra>"
            )

        # Add trace for absolute values (left y-axis)
        fig.add_trace(
            go.Scatter(
                x=subset['time'],
                y=subset['value'],
                mode='lines',
                name=f'{voltage}V {direction}',
                line=dict(color=color, width=2),
                customdata=subset[['value_formatted', 'diff_formatted', 'range_formatted']].to_numpy(),
                hovertemplate=hovertemplate,
                legendgroup=f'group{seq_idx}',
            ),
            secondary_y=False,
        )

        # Add trace for difference from mean (right y-axis)
        fig.add_trace(
            go.Scatter(
                x=subset['time'],
                y=subset['diff_from_mean'],
                mode='lines',
                name=f'{voltage}V {direction} (diff)',
                line=dict(color=color, width=1, dash='dot'),
                customdata=subset[['value_formatted', 'diff_formatted', 'range_formatted']].to_numpy(),
                hovertemplate=hovertemplate,
                legendgroup=f'group{seq_idx}',
                showlegend=False,  # Don't show in legend (same as main trace)
            ),
            secondary_y=True,
        )

    # Calculate the range for centering on mean
    # Use the maximum absolute difference to set symmetric ranges
    max_abs_diff = df['value'].sub(overall_mean).abs().max()
    # Add some padding (20%) for visual clarity
    y_range_padding = max_abs_diff * 1.2

    # Update layout
    plot_title = title if title else "Keithley 6517A Resistance Measurements"
    fig.update_layout(
        title=plot_title,
        xaxis_title="Time (s)",
        hovermode='closest',
        template='plotly_white',
        showlegend=True,
        legend=dict(
            title="Repeat #",
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=1.02,  # Position to the right of the plot area
            bordercolor="Black",
            borderwidth=1
        ),
        height=600,
        width=1100,  # Add width to accommodate legend on the right
    )

    # Set y-axes titles and ranges (both centered on mean/zero)
    fig.update_yaxes(
        title_text="Resistance (Ω)",
        range=[overall_mean - y_range_padding, overall_mean + y_range_padding],
        secondary_y=False
    )
    fig.update_yaxes(
        title_text="Difference from Mean (Ω)",
        range=[-y_range_padding, y_range_padding],
        secondary_y=True
    )

    # Add a horizontal line at y=0 on the secondary axis
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5,
                  secondary_y=True, annotation_text="Mean",
                  annotation_position="right")

    # Show plot
    fig.show()

    # Save if requested
    if save_html:
        fig.write_html(save_html, include_plotlyjs='cdn')
        print(f"Plot saved to {save_html}")


if __name__ == '__main__':
    # Example 1: Run a new measurement sequence
    main()

    # # Example 2: Plot previously saved data
    # Keithley6517A.plot_saved_data(
    #     csv_file='keithley_voltage_sweep_20251107.csv',
    #     save_html='keithley_voltage_sweep_20251107.html',
    #     title='Keithley 6517A Resistance Measurements - 50V Repeats'
    # )

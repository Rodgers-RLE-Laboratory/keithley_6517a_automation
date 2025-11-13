#!/usr/bin/env python3
"""
Debug script for Keithley 6517A measurement issues.
This script tests the instrument configuration and measurements.
"""

import time
from keithley_6517a import Keithley6517A

# Configure your instrument's VISA resource name
RESOURCE_NAME = 'ASRL/dev/tty.usbserial-110::INSTR'  # Change this to match your system


def main():
    """Run diagnostic tests on the Keithley 6517A."""

    print("=" * 60)
    print("Keithley 6517A Diagnostic Test")
    print("=" * 60)

    with Keithley6517A(RESOURCE_NAME) as keithley:
        print("\n[1] Disabling zero check...")
        keithley.set_zero_check(False)

        print("\n[2] Configuring voltage source (does NOT enable output)...")
        keithley.configure_voltage_source(50.0)

        print("\n[3] Configuring resistance measurement...")
        keithley.configure_measurement('RES', 'AUTO', averaging_on=True)

        print("\n[4] Running measurement test (output still OFF)...")
        keithley.test_measurement()

        print("\n[5] Enabling high voltage output...")
        keithley.enable_output(True)

        print("\n[6] Waiting for source to settle...")
        time.sleep(0.5)

        print("\n[7] Running measurement test (output now ON)...")
        keithley.test_measurement()

        print("\n[8] Trying a few manual measurements...")
        for i in range(3):
            print(f"\nMeasurement {i+1}:")
            print(f"  explicit_trigger=False: {keithley.read_measurement(explicit_trigger=False):.6e}")
            print(f"  explicit_trigger=True:  {keithley.read_measurement(explicit_trigger=True):.6e}")
            time.sleep(0.1)

        print("\n[9] Shutting down...")
        keithley.enable_output(False)
        keithley.set_zero_check(True)

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()

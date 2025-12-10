#!/usr/bin/env python3
"""
Recovery script for Keithley 6517A when it's stuck/unresponsive.

Run this if you get timeout errors when trying to connect.
If this doesn't work, power cycle the instrument (turn off and back on).
"""

import pyvisa
import time

RESOURCE_NAME = 'ASRL/dev/tty.usbserial-2110::INSTR'

def recover_instrument():
    """Try to recover a stuck Keithley 6517A instrument."""

    print("=" * 60)
    print("Keithley 6517A Recovery Script")
    print("=" * 60)
    print("\nAttempting to recover instrument communication...")
    print(f"Resource: {RESOURCE_NAME}\n")

    try:
        rm = pyvisa.ResourceManager()
        instr = rm.open_resource(RESOURCE_NAME)

        # Configure serial
        instr.baud_rate = 9600
        instr.timeout = 2000  # Short timeout for recovery
        instr.read_termination = '\n'
        instr.write_termination = '\n'

        print("[1] Clearing buffers...")
        try:
            instr.clear()
            time.sleep(0.2)
        except Exception as e:
            print(f"    Clear failed (expected): {e}")

        print("[2] Flushing any pending data...")
        for _ in range(5):
            try:
                data = instr.read()
                print(f"    Flushed: {data.strip()}")
            except:
                break

        print("[3] Sending abort command...")
        try:
            instr.write(':ABOR')
            time.sleep(0.2)
        except Exception as e:
            print(f"    Abort failed: {e}")

        print("[4] Sending clear status...")
        try:
            instr.write('*CLS')
            time.sleep(0.2)
        except Exception as e:
            print(f"    Clear status failed: {e}")

        print("[5] Attempting identity query...")
        try:
            idn = instr.query('*IDN?')
            print(f"    Success! Instrument: {idn.strip()}")
        except Exception as e:
            print(f"    Failed: {e}")
            print("\n⚠️  Recovery unsuccessful.")
            print("    Please power cycle the instrument (turn off and back on)")
            instr.close()
            rm.close()
            return False

        print("[6] Sending reset command...")
        try:
            instr.write('*RST')
            time.sleep(1.5)
            print("    Reset sent, waiting for instrument to settle...")
        except Exception as e:
            print(f"    Reset failed: {e}")

        print("[7] Final status check...")
        try:
            instr.write('*CLS')
            time.sleep(0.2)
            error = instr.query(':SYST:ERR?')
            print(f"    Error status: {error.strip()}")
        except Exception as e:
            print(f"    Status check failed: {e}")

        instr.close()
        rm.close()

        print("\n" + "=" * 60)
        print("✓ Recovery complete!")
        print("=" * 60)
        print("\nYou can now try running your measurement script.")
        return True

    except Exception as e:
        print(f"\n⚠️  Recovery failed with error: {e}")
        print("\nPlease:")
        print("1. Check the USB cable connection")
        print("2. Verify the resource name is correct")
        print("3. Power cycle the instrument (turn off and back on)")
        print("4. Try running this script again")
        return False


if __name__ == '__main__':
    recover_instrument()

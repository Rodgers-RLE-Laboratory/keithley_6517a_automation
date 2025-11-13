"""
Simple test script to verify PyVISA installation.
"""

import sys

print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")

try:
    import pyvisa
    print(f"\n✅ PyVISA imported successfully!")
    print(f"PyVISA version: {pyvisa.__version__}")

    # List available VISA backends
    print(f"\nAvailable backends:")
    print(f"  - pyvisa-py (pure Python, no drivers needed)")

    # Try to create a resource manager
    try:
        rm = pyvisa.ResourceManager()
        print(f"\n✅ ResourceManager created successfully")
        print(f"Backend: {rm}")

        # List available resources
        resources = rm.list_resources()
        if resources:
            print(f"\nFound {len(resources)} VISA resource(s):")
            for res in resources:
                print(f"  - {res}")
        else:
            print(f"\nNo VISA resources found (this is normal if no instruments are connected)")

    except Exception as e:
        print(f"\n⚠️  Could not create ResourceManager: {e}")
        print(f"\nTo use PyVISA without NI-VISA drivers, install pyvisa-py:")
        print(f"  pip install pyvisa-py")

except ImportError as e:
    print(f"\n❌ Failed to import PyVISA: {e}")
    print(f"\nPlease install PyVISA:")
    print(f"  pip install pyvisa")

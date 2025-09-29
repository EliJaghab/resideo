#!/usr/bin/env python3
"""
Wrapper script that runs token refresh and then thermostat control
in the same process to preserve environment variables.
"""
import subprocess
import sys
import os

def main():
    print("Token expired, refreshing...")

    # Run token refresh
    try:
        import automated_token_refresh
        result = automated_token_refresh.main()
        if result != 0:
            print("Token refresh failed")
            return 1
    except Exception as e:
        print(f"Token refresh error: {e}")
        return 1

    print("Token refresh successful, retrying thermostat control...")

    # Run thermostat control in same process (environment preserved)
    try:
        import thermostat_control
        return 0
    except SystemExit as e:
        return e.code
    except Exception as e:
        print(f"Thermostat control error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
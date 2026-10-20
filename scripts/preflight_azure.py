"""Live service capability checks; run only after Azure login, never in dry-run mode."""
import os
import sys

from scripts.onboard_azure import azure_readiness

if __name__ == "__main__":
    try:
        azure_readiness(os.environ.get("AZURE_LOCATION", "eastus"),
                        os.environ.get("AZURE_HOSTING", "containerapps"),
                        os.environ.get("AZURE_POSTGRES_SKU", "Standard_B1ms"),
                        os.environ.get("AZURE_POSTGRES_TIER", "Burstable"))
    except RuntimeError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from None

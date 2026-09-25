"""Compatibility wrapper for checkpoint fairness audit v0.2."""
from audit_checkpoint_fairness_v02 import *  # noqa: F401,F403
from audit_checkpoint_fairness_v02 import _load_frozen_gzip, main


if __name__ == "__main__":
    main()

"""Episodic Pivot scanner — Agent 1 technical filter."""

__all__ = ["run_ep_scan"]


def __getattr__(name: str):
    if name == "run_ep_scan":
        from stock_analyze.scanners.ep.runner import run_ep_scan

        return run_ep_scan
    raise AttributeError(name)

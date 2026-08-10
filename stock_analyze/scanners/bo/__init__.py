"""Qullamaggie Breakout scanner — Agent 1 structural filter."""

__all__ = ["run_bo_scan"]


def __getattr__(name: str):
    if name == "run_bo_scan":
        from stock_analyze.scanners.bo.runner import run_bo_scan

        return run_bo_scan
    raise AttributeError(name)

"""Volatility Contraction Pattern scanner — Agent 1 structural filter."""

__all__ = ["run_vcp_scan"]


def __getattr__(name: str):
    if name == "run_vcp_scan":
        from stock_analyze.scanners.vcp.runner import run_vcp_scan

        return run_vcp_scan
    raise AttributeError(name)

"""
Pydantic Models for VCP Stock Analysis
========================================
Centralized data validation and serialization for all modules.
Provides type-safe, validated data structures with clear schemas.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# TradingView Data Models
# =============================================================================


class StockCandle(BaseModel):
    """A single OHLCV data point from TradingView."""

    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @field_validator("open", "high", "low", "close")
    @classmethod
    def validate_price_non_negative(cls, v: float, info: Any) -> float:
        if v < 0:
            raise ValueError(f"{info.field_name} must be non-negative, got {v}")
        return v

    @field_validator("volume")
    @classmethod
    def validate_volume_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"volume must be non-negative, got {v}")
        return v


class StockDataSummary(BaseModel):
    """Summary of fetched stock data."""

    symbol: str
    exchange: str
    interval: str
    total_bars: int
    date_range_start: str
    date_range_end: str
    price_min: float
    price_max: float
    current_price: float
    average_volume: float


class StockDataResult(BaseModel):
    """Complete result from fetching stock data."""

    symbol: str
    exchange: str
    interval: str
    candles: list[StockCandle]
    summary: StockDataSummary


# =============================================================================
# VCP Scan Models (from vcp_scan.py)
# =============================================================================


class PivotPoint(BaseModel):
    """Represents a swing high or low pivot point in price action."""

    date: str
    price: float
    type: str = Field(..., pattern="^(high|low)$")
    index: int = Field(..., ge=0)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in ("high", "low"):
            raise ValueError(f"type must be 'high' or 'low', got {v}")
        return v_lower


class Contraction(BaseModel):
    """Represents a single price contraction in a VCP pattern."""

    number: int = Field(..., ge=1)
    high_price: float = Field(..., gt=0)
    low_price: float = Field(..., gt=0)
    high_date: str
    low_date: str
    depth: float  # Percentage contraction
    start_date: str
    end_date: str
    avg_volume: float = Field(..., ge=0)

    @field_validator("depth")
    @classmethod
    def validate_depth_range(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"depth must be non-negative, got {v}")
        return v


class VCPSetup(BaseModel):
    """Complete VCP pattern analysis result."""

    contractions: list[Contraction]
    pivot_points: list[PivotPoint]
    is_valid: bool
    trend_valid: bool
    volatility_contracting: bool
    volume_contracting: bool
    near_highs: bool
    analysis_date: str

    def contraction_count(self) -> int:
        """Return the number of contractions detected."""
        return len(self.contractions)

    def sorted_contractions(self) -> list[Contraction]:
        """Return contractions sorted by number (oldest first)."""
        return sorted(self.contractions, key=lambda c: c.number)

    def pattern_quality(self) -> str:
        """Assess the overall pattern quality."""
        if not self.is_valid:
            return "N/A"
        if self.volatility_contracting and self.volume_contracting:
            return "Excellent"
        if self.volatility_contracting or self.volume_contracting:
            return "Good"
        return "Fair"


# =============================================================================
# VCP Analyzer Models (from vcp_analyzer.py)
# =============================================================================


class DataResult(BaseModel):
    """Result from the Data Retrieval Agent."""

    success: bool
    symbol: str
    exchange: str
    data_summary: str = ""
    agent_response: str = ""
    error: str = ""
    attempts: int = 0


class AnalysisResult(BaseModel):
    """Result from the VCP Analysis Agent."""

    success: bool
    report: str = ""
    rating: str = "N/A"
    error: str = ""


# =============================================================================
# Report Models
# =============================================================================


class ScanMetadata(BaseModel):
    """Metadata about a scan run."""

    scan_date: datetime = Field(default_factory=datetime.now)
    symbols_scanned: int = 0
    scan_duration_seconds: float = 0.0
    version: str = "1.0.0"


class ScanSummary(BaseModel):
    """High-level summary of scan results."""

    total_scanned: int = 0
    vcp_detected: int = 0
    vcp_rate: float = 0.0
    avg_quality: Optional[float] = None
    top_signals: list[str] = Field(default_factory=list)


class StockReportEntry(BaseModel):
    """A single stock's entry in the scan report."""

    symbol: str
    exchange: str
    vcp_detected: bool = False
    pattern_quality: Optional[str] = None
    buy_point: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_reward: Optional[float] = None
    ma_alignment: Optional[str] = None
    rsi: Optional[float] = None
    macd_signal: Optional[str] = None
    adx: Optional[float] = None
    obv_trend: Optional[str] = None
    error: Optional[str] = None


class VCPReport(BaseModel):
    """Complete scan report with metadata and all stock entries."""

    scan_metadata: ScanMetadata = Field(default_factory=ScanMetadata)
    summary: ScanSummary = Field(default_factory=ScanSummary)
    details: list[StockReportEntry] = Field(default_factory=list)


# =============================================================================
# API / Serialization Helpers
# =============================================================================


class VCPSerializer:
    """Utility for serializing VCP models to various formats."""

    @staticmethod
    def setup_to_dict(setup: VCPSetup) -> dict:
        """Convert a VCPSetup to a JSON-compatible dictionary."""
        return setup.model_dump()

    @staticmethod
    def setup_to_json(setup: VCPSetup, indent: int = 2) -> str:
        """Convert a VCPSetup to a JSON string."""
        return setup.model_dump_json(indent=indent)

    @staticmethod
    def report_to_dict(report: VCPReport) -> dict:
        """Convert a VCPReport to a JSON-compatible dictionary."""
        return report.model_dump()

    @staticmethod
    def report_to_json(report: VCPReport, indent: int = 2) -> str:
        """Convert a VCPReport to a JSON string."""
        return report.model_dump_json(indent=indent)
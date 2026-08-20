"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { CandlestickSeries, ColorType, HistogramSeries, createChart, createSeriesMarkers } from "lightweight-charts";
import type { OhlcvBar } from "@/lib/types";
import { toChartTime, type PatternOverlay } from "@/lib/flow";

const UP = "#2fbf9a";
const DOWN = "#e05c5c";

/**
 * Pattern-evidence candlestick chart. Overlays are computed from scanner-row
 * anchors (base region, pivot, breakout bar, gap day) — charts are for
 * understanding what the scanner saw, never for confirming decisions.
 */
export function ChartCard({
  symbol,
  bars,
  overlay,
  footer,
}: {
  symbol: string;
  bars: OhlcvBar[];
  overlay: PatternOverlay;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || bars.length === 0) return;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#121316" },
        textColor: "#717886",
        fontSize: 10,
        fontFamily: "IBM Plex Mono",
      },
      grid: {
        vertLines: { color: "#1b1d22" },
        horzLines: { color: "#1b1d22" },
      },
      rightPriceScale: { borderColor: "#262a31" },
      timeScale: { borderColor: "#262a31", rightOffset: 4, barSpacing: 5 },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
    });
    candles.setData(
      bars.map((b) => ({
        time: toChartTime(b.datetime),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );

    const vol = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(
      bars.map((b) => ({
        time: toChartTime(b.datetime),
        value: b.volume,
        color: b.close >= b.open ? "rgba(47,191,154,0.28)" : "rgba(224,92,92,0.28)",
      })),
    );

    for (const pl of overlay.priceLines) {
      candles.createPriceLine({
        price: pl.price,
        color: pl.color,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: pl.title,
      });
    }
    const markers = createSeriesMarkers(candles, overlay.markers);

    chart.timeScale().fitContent();
    return () => {
      markers.detach();
      chart.remove();
    };
  }, [bars, overlay]);

  return (
    <div className="overflow-hidden rounded-md border border-ink-800 bg-ink-900">
      <div ref={ref} className="h-[250px] w-full" />
      {footer}
    </div>
  );
}

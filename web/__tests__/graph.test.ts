import { describe, expect, it } from "vitest";
import {
  UNIVERSE_ID,
  componentNodes,
  defaultsFor,
  isWireValid,
  scannerGroups,
  universeNodes,
  visibleVars,
} from "@/lib/graph";
import type { GraphNode, PortDef, ToolSpec, VariableDef } from "@/lib/types";

function port(id: string, type: PortDef["type"], required = true): PortDef {
  return { id, type, required, label: id };
}

const SCANNER_VARS: VariableDef[] = [
  { key: "family", label: "Family", kind: "select", default: "vcp", group: "Family", options: ["ep", "vcp", "bo", "custom"] },
  { key: "ep_limit", label: "Limit", kind: "number", default: 300, group: "EP" },
  { key: "rs_floor", label: "RS floor", kind: "number", default: 80, group: "VCP" },
];

const scanner: ToolSpec = {
  id: "scanner",
  name: "Scanner",
  description: "Technical screening",
  phase: 1,
  inputs: [port("universe", "symbolkey")],
  outputs: [port("bucket", "scan_rows")],
  variables: SCANNER_VARS,
};

const report: ToolSpec = {
  id: "report",
  name: "Report",
  description: "Rating, ranking, caps",
  phase: 4,
  inputs: [port("structural", "report_rows")],
  outputs: [port("rated", "report_rows")],
  variables: [],
};

function nodeData(component: ToolSpec, variables: Record<string, string | number | boolean> = {}) {
  return { component, variables };
}

describe("defaultsFor", () => {
  it("fills every variable with its default", () => {
    expect(defaultsFor(scanner)).toEqual({ family: "vcp", ep_limit: 300, rs_floor: 80 });
  });
});

describe("scannerGroups", () => {
  it("maps each family to its inspector groups", () => {
    expect(scannerGroups("ep")).toEqual(["Family", "EP", "EP baseline", "EP strict"]);
    expect(scannerGroups("vcp")).toEqual(["Family", "VCP"]);
    expect(scannerGroups("bo")).toEqual(["Family", "BO"]);
    expect(scannerGroups("custom")).toEqual(["Family", "Custom"]);
    expect(scannerGroups("nope")).toEqual(["Family", "EP", "EP baseline", "EP strict"]);
  });
});

describe("visibleVars", () => {
  it("filters scanner vars to the active family groups", () => {
    const all = defaultsFor(scanner);
    const vcp = visibleVars(scanner, { ...all, family: "vcp" }).map((v) => v.key);
    expect(vcp).toEqual(["family", "rs_floor"]);
    const ep = visibleVars(scanner, { ...all, family: "ep" }).map((v) => v.key);
    expect(ep).toEqual(["family", "ep_limit"]);
  });

  it("returns all vars for non-scanner tools", () => {
    expect(visibleVars(report, {})).toEqual([]);
  });
});

describe("isWireValid", () => {
  const univSpec: ToolSpec = {
    id: UNIVERSE_ID,
    name: "Universe",
    description: "",
    phase: 0,
    inputs: [],
    outputs: [port("out", "symbolkey")],
    variables: [],
  };
  const src = { id: "u", data: nodeData(univSpec) };
  const tgt = { id: "sc", data: nodeData(scanner) };
  const tgtRpt = { id: "r", data: nodeData(report) };

  it("accepts symbolkey -> symbolkey", () => {
    expect(isWireValid(src, tgt, "out", "universe")).toBe(true);
  });

  it("rejects stage mismatches (symbolkey -> report_rows)", () => {
    expect(isWireValid(src, tgtRpt, "out", "structural")).toBe(false);
  });

  it("rejects unknown handles", () => {
    expect(isWireValid(src, tgt, "nope", "universe")).toBe(false);
    expect(isWireValid(src, tgt, "out", "nope")).toBe(false);
  });

  it("rejects self-wires and missing nodes", () => {
    expect(isWireValid(tgt, tgt, "bucket", "universe")).toBe(false);
    expect(isWireValid(undefined, tgt, "out", "universe")).toBe(false);
    expect(isWireValid(src, undefined, "out", "universe")).toBe(false);
  });
});

describe("universeNodes / componentNodes", () => {
  const nodes: GraphNode[] = [
    { id: "universe", type: UNIVERSE_ID, position: { x: 0, y: 0 }, variables: {} },
    { id: "sc_1", type: "scanner", position: { x: 0, y: 0 }, variables: {} },
    { id: "r_1", type: "report", position: { x: 0, y: 0 }, variables: {} },
  ];

  it("splits universe from components", () => {
    expect(universeNodes(nodes).map((n) => n.id)).toEqual(["universe"]);
    expect(componentNodes(nodes).map((n) => n.id)).toEqual(["sc_1", "r_1"]);
  });
});

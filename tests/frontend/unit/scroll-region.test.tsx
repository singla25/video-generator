// A11Y-SCROLL: every horizontal scroll container is keyboard accessible (axe: scrollable-region-focusable).
// Cases: TT-A11Y-SCROLL-*
//
// CONTRACT
//   frontend/src/components/ScrollRegion.tsx   export function ScrollRegion({ label, children, className? })
//     renders <div role="region" tabIndex={0} aria-label={label} class="overflow-x-auto ...">children</div>
//   Each of the five tables below renders its scroll container through <ScrollRegion label="...">:
//     DraftsSection "Drafts table", BatchListTable "Batches table", RowsTable "Rows table",
//     HistoryPage "History table", StepMap "Sheet preview table".
//   No raw `overflow-x-auto` may remain in those files (only inside ScrollRegion.tsx).
import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { ScrollRegion } from "../../../frontend/src/components/ScrollRegion";

const SRC = resolve(__dirname, "../../../frontend/src");

const USERS: [string, string][] = [
  ["components/DraftsSection.tsx", "Drafts table"],
  ["components/BatchListTable.tsx", "Batches table"],
  ["components/RowsTable.tsx", "Rows table"],
  ["pages/HistoryPage.tsx", "History table"],
  ["pages/wizard/StepMap.tsx", "Sheet preview table"],
];

describe("ScrollRegion", () => {
  it("is a focusable, labelled region that scrolls horizontally", () => {
    render(
      <ScrollRegion label="Demo table">
        <table />
      </ScrollRegion>,
    );
    const region = screen.getByRole("region", { name: "Demo table" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region.className).toContain("overflow-x-auto");
    expect(region.querySelector("table")).not.toBeNull();
  });

  it("keeps an extra className next to the scroll class", () => {
    render(
      <ScrollRegion label="X" className="rounded-tile border">
        <p />
      </ScrollRegion>,
    );
    const region = screen.getByRole("region", { name: "X" });
    expect(region.className).toContain("overflow-x-auto");
    expect(region.className).toContain("rounded-tile");
  });
});

describe.each(USERS)("%s", (file, label) => {
  const source = readFileSync(resolve(SRC, file), "utf8");

  it("uses ScrollRegion with its specific label", () => {
    expect(source).toMatch(new RegExp(`<ScrollRegion[^>]*label=\\{?["']${label}["']`));
  });

  it("has no raw overflow-x-auto container left", () => {
    expect(source).not.toContain("overflow-x-auto");
  });
});

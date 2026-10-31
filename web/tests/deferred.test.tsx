import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { DeferredContent } from "../src/components/DeferredContent";

it("defers offscreen controls until intersection and disconnects its observer", () => {
  let update: (entries: { isIntersecting: boolean }[]) => void = () => {};
  const disconnect = vi.fn();
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: typeof update) {
        update = callback;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
  const children = vi.fn(() => <p>Prices ready</p>);
  render(<DeferredContent>{children}</DeferredContent>);
  expect(children).not.toHaveBeenCalled();
  act(() => update([{ isIntersecting: false }]));
  expect(children).not.toHaveBeenCalled();
  act(() => update([{ isIntersecting: true }]));
  expect(screen.getByText("Prices ready")).toBeVisible();
  expect(disconnect).toHaveBeenCalled();
});

it("preserves keyboard focus when revealing controls and supports explicit activation", () => {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  render(
    <DeferredContent>{() => <button>Choose a car</button>}</DeferredContent>,
  );
  act(() =>
    screen.getByRole("button", { name: "Explore city prices" }).focus(),
  );
  expect(
    screen.getByRole("group", { name: "City prices and market details" }),
  ).toHaveFocus();
  expect(screen.getByRole("button", { name: "Choose a car" })).toBeVisible();
});

it("renders immediately without intersection support", () => {
  render(<DeferredContent>{() => <p>All market details</p>}</DeferredContent>);
  expect(screen.getByText("All market details")).toBeVisible();
});

it("responds to the explicit exploration button", () => {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  render(<DeferredContent>{() => <p>All market details</p>}</DeferredContent>);
  fireEvent.click(screen.getByRole("button", { name: "Explore city prices" }));
  expect(screen.getByText("All market details")).toBeVisible();
});

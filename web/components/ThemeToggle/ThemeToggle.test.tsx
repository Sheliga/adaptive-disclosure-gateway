import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { readStoredThemePreference } from "@/lib/theme";

import { ThemeToggle } from "./ThemeToggle";

function mockMatchMedia(prefersDark: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === "(prefers-color-scheme: dark)" ? prefersDark : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  mockMatchMedia(false);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ThemeToggle", () => {
  it("renders correctly with no stored preference, following the system preference", () => {
    mockMatchMedia(true);
    render(<ThemeToggle />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });

  it("flips data-theme on the document root and persists the choice when clicked", async () => {
    mockMatchMedia(false);
    render(<ThemeToggle />);

    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(button);

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(readStoredThemePreference()).toBe("dark");
  });

  it("flips back to light on a second click", async () => {
    mockMatchMedia(false);
    render(<ThemeToggle />);
    const button = screen.getByRole("button");

    await userEvent.click(button);
    await userEvent.click(button);

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(readStoredThemePreference()).toBe("light");
  });
});

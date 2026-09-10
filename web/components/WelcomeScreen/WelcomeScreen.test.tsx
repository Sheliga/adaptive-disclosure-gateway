import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithLocale } from "@/i18n/renderWithLocale";
import { copy } from "@/lib/copy";
import { enUS } from "@/lib/copy.en-US";

import { WelcomeScreen } from "./WelcomeScreen";

beforeEach(() => {
  window.localStorage.clear();
});

describe("WelcomeScreen", () => {
  it("renders the heading and CTA from copy.ts, not hardcoded text", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1, name: copy.howItWorks.title })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary })).toBeInTheDocument();
  });

  it("renders all three concept steps from copy.ts", () => {
    render(<WelcomeScreen onStart={vi.fn()} />);

    for (const step of copy.howItWorks.steps) {
      expect(screen.getByText(step.description)).toBeInTheDocument();
    }
  });

  it("calls onStart when the primary CTA is clicked", async () => {
    const onStart = vi.fn();
    render(<WelcomeScreen onStart={onStart} />);

    await userEvent.click(screen.getByRole("button", { name: copy.howItWorks.ctaPrimary }));

    expect(onStart).toHaveBeenCalledTimes(1);
  });
});

describe("WelcomeScreen -- switches to English (T21 fourth slice)", () => {
  it("renders the English heading, steps and CTA when en-US is the active locale", async () => {
    await renderWithLocale(<WelcomeScreen onStart={vi.fn()} />, "en-US");

    expect(screen.getByRole("heading", { level: 1, name: enUS.howItWorks.title })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: enUS.howItWorks.ctaPrimary })).toBeInTheDocument();
    for (const step of enUS.howItWorks.steps) {
      expect(screen.getByText(step.description)).toBeInTheDocument();
    }
    expect(screen.queryByText(copy.howItWorks.title)).not.toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { copy } from "@/lib/copy";

import { WelcomeScreen } from "./WelcomeScreen";

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

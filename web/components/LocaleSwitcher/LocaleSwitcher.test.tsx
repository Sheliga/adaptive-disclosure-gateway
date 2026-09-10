import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";

import { LocaleSwitcher } from "./LocaleSwitcher";

beforeEach(() => {
  window.localStorage.clear();
});

function renderSwitcher() {
  return render(
    <LocaleProvider>
      <LocaleSwitcher />
    </LocaleProvider>,
  );
}

describe("LocaleSwitcher -- discreet, keyboard-operable, text-labeled control", () => {
  it("is a real button, not a decorative element -- keyboard operable by construction", () => {
    renderSwitcher();
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("shows the current locale using a text label, never only a flag", () => {
    renderSwitcher();
    const button = screen.getByRole("button");
    // Text content must name the language in words -- Português/English or
    // PT/EN -- never rely on emoji/flag glyphs as the only indicator (flags
    // denote countries, not languages).
    expect(button.textContent).toMatch(/português|portugu|pt-br|pt\b/i);
  });

  it("has a clear accessible name describing what the control does", () => {
    renderSwitcher();
    // Either the visible text or an aria-label must communicate purpose;
    // getByRole with no name filter already found it above -- this asserts
    // the accessible name is not empty/generic.
    const button = screen.getByRole("button");
    const accessibleName = button.getAttribute("aria-label") ?? button.textContent ?? "";
    expect(accessibleName.trim().length).toBeGreaterThan(0);
  });

  it("switches to English on click and updates its own displayed state", async () => {
    renderSwitcher();
    const button = screen.getByRole("button");

    await userEvent.click(button);

    expect(button.textContent).toMatch(/english|en\b/i);
  });

  it("is operable from the keyboard (Enter activates it, same as any button)", async () => {
    const user = userEvent.setup();
    renderSwitcher();
    const button = screen.getByRole("button");

    await user.tab(); // moves focus onto the (only focusable) button
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(button.textContent).toMatch(/english|en\b/i);
  });

  it("toggles back to Portuguese on a second activation", async () => {
    renderSwitcher();
    const button = screen.getByRole("button");

    await userEvent.click(button);
    await userEvent.click(button);

    expect(button.textContent).toMatch(/português|portugu|pt-br|pt\b/i);
  });
});

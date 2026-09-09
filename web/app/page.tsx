import { GuidedFlow } from "@/components/GuidedFlow/GuidedFlow";

/**
 * The guided flow (Boas-vindas -> Novo teste -> Revisão -> Resultado,
 * `docs/advisor-demo.md`'s MVP v2 experience) is the whole app for this
 * slice. All state/wiring lives in `GuidedFlow`; this file is just the
 * route entry point.
 */
export default function Home() {
  return <GuidedFlow />;
}

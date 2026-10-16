import { Button } from "@/components/ui/button";

const upcomingSections = [
  "Jobs",
  "Nodes",
  "Agents",
  "Models",
  "Workspaces",
  "Integrations / MCP",
  "Activity / Audit",
  "Settings",
];

function NavigationItems() {
  return (
    <>
      <a
        href="#main-content"
        aria-current="page"
        className="block rounded-md border bg-card px-3 py-2.5 text-sm font-semibold"
      >
        Overview
      </a>
      <p className="mt-6 mb-2 px-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
        Planned sections
      </p>
      <ul className="grid grid-cols-2 gap-1 sm:grid-cols-4 lg:grid-cols-1">
        {upcomingSections.map((section) => (
          <li key={section}>
            <span
              aria-disabled="true"
              className="block px-3 py-2 text-sm text-muted-foreground"
            >
              {section}
              <span className="sr-only"> — unavailable in Phase 01</span>
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}

export default function Home() {
  return (
    <>
      <a
        href="#main-content"
        className="sr-only fixed top-4 left-4 z-50 rounded-md bg-card p-3 focus:not-sr-only"
      >
        Skip to content
      </a>
      <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
        <aside className="border-b bg-sidebar p-6 lg:sticky lg:top-0 lg:h-screen lg:border-r lg:border-b-0">
          <a
            href="#main-content"
            className="flex items-center gap-3 rounded-md"
          >
            <span
              aria-hidden="true"
              className="flex size-10 items-center justify-center rounded-lg border bg-card font-serif text-xl"
            >
              G
            </span>
            <span>
              <span className="block text-sm font-bold tracking-widest uppercase">
                The Godfather
              </span>
              <span className="text-xs text-muted-foreground">
                Command Center
              </span>
            </span>
          </a>
          <nav aria-label="Main navigation" className="mt-7">
            <div className="hidden lg:block">
              <NavigationItems />
            </div>
            <details className="lg:hidden">
              <summary className="cursor-pointer rounded-md border bg-card px-3 py-2.5 text-sm font-semibold">
                Navigation
              </summary>
              <div className="mt-3">
                <NavigationItems />
              </div>
            </details>
          </nav>
          <div className="mt-6 border-t pt-4 text-xs leading-relaxed text-muted-foreground lg:absolute lg:right-6 lg:bottom-6 lg:left-6">
            Local development only
            <br />
            No cluster connected
          </div>
        </aside>

        <div className="min-w-0">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b px-6 py-5 sm:px-10">
            <p className="text-sm text-muted-foreground">
              Command Center <span aria-hidden="true">/</span>{" "}
              <span className="text-foreground">Overview</span>
            </p>
            <span className="rounded-full border px-3 py-1 text-xs font-medium">
              Development · Phase 01
            </span>
          </header>

          <main
            id="main-content"
            tabIndex={-1}
            className="mx-auto max-w-6xl px-6 py-10 sm:px-10 sm:py-14"
          >
            <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground uppercase">
              A shared platform. Independent nodes.
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              Your Command Center starts here.
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">
              One place to coordinate work across Windows, macOS, and Linux.
              This first phase establishes the local foundation.
            </p>

            <section
              aria-labelledby="connection-title"
              className="mt-10 rounded-lg border bg-card p-6 sm:p-8"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                    Platform connection
                  </p>
                  <h2
                    id="connection-title"
                    className="mt-3 text-xl font-semibold"
                  >
                    Backend not connected
                  </h2>
                </div>
                <span className="rounded-md bg-muted px-3 py-1.5 text-xs font-medium">
                  Shell only
                </span>
              </div>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-muted-foreground">
                Node health, jobs, and activity are unavailable. This page does
                not query a coordinator or display live telemetry. Management
                controls will arrive in later phases.
              </p>
              <div className="mt-6">
                <Button asChild variant="outline">
                  <a href="#development">View this phase</a>
                </Button>
              </div>
            </section>

            <section
              id="development"
              aria-labelledby="development-title"
              className="mt-10"
            >
              <h2 id="development-title" className="text-lg font-semibold">
                A deliberate foundation
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Phase 01 scope. These describe the foundation, not live setup
                checks or completion indicators.
              </p>
              <div className="mt-5 grid gap-4 md:grid-cols-3">
                {[
                  [
                    "01",
                    "Repeatable setup",
                    "Locked dependencies, portable tooling, and a reproducible development environment.",
                  ],
                  [
                    "02",
                    "Local by default",
                    "A browser shell and local dependencies. No public deployment or production connections.",
                  ],
                  [
                    "03",
                    "Clear boundaries",
                    "Shared administration with independent node ownership and private workspaces by default.",
                  ],
                ].map(([number, title, description]) => (
                  <article key={number} className="rounded-lg border p-5">
                    <span className="font-mono text-xs text-muted-foreground">
                      {number}
                    </span>
                    <h3 className="mt-4 text-sm font-semibold">{title}</h3>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      {description}
                    </p>
                  </article>
                ))}
              </div>
            </section>
            <footer className="mt-12 border-t pt-5 text-xs leading-6 text-muted-foreground">
              Las Vegas / Los Angeles · Development shell · No user session
            </footer>
          </main>
        </div>
      </div>
    </>
  );
}

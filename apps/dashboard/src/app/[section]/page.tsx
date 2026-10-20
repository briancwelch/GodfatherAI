import { notFound } from "next/navigation";
import CommandCenter from "@/components/command-center";
import type { Section } from "@/lib/contracts";
import { requireUser } from "@/lib/control-server";
export default async function SectionPage({
  params,
  searchParams,
}: {
  params: Promise<{ section: string }>;
  searchParams: Promise<{ workspace?: string; model?: string }>;
}) {
  const { section } = await params;
  await requireUser();
  if (!["jobs", "nodes", "agents", "models", "activity"].includes(section))
    notFound();
  const query = await searchParams;
  return (
    <CommandCenter
      section={section as Section}
      initialWorkspace={query.workspace}
      initialModel={query.model}
    />
  );
}

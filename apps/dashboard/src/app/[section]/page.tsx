import { notFound } from "next/navigation";
import CommandCenter from "@/components/command-center";
import type { Section } from "@/lib/contracts";
import { requireUser } from "@/lib/control-server";
export default async function SectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  await requireUser();
  if (!["jobs", "nodes", "agents", "models", "activity"].includes(section))
    notFound();
  return <CommandCenter section={section as Section} />;
}

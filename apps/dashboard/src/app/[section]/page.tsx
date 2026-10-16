import { notFound } from "next/navigation";
import CommandCenter from "@/components/command-center";
import type { Section } from "@/lib/contracts";
export default async function SectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  if (!["jobs", "nodes", "agents", "models", "activity"].includes(section))
    notFound();
  return <CommandCenter section={section as Section} />;
}

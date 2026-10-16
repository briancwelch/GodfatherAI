import CommandCenter from "@/components/command-center";
import { requireUser } from "@/lib/control-server";
export default async function NodePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireUser();
  return <CommandCenter section="nodes" detailId={(await params).id} />;
}

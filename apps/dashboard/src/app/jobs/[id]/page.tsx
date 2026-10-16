import CommandCenter from "@/components/command-center";
import { requireUser } from "@/lib/control-server";
export default async function JobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireUser();
  return <CommandCenter section="jobs" detailId={(await params).id} />;
}

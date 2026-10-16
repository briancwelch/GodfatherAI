import CommandCenter from "@/components/command-center";
export default async function JobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <CommandCenter section="jobs" detailId={(await params).id} />;
}

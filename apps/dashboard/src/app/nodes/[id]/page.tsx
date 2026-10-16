import CommandCenter from "@/components/command-center";
export default async function NodePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <CommandCenter section="nodes" detailId={(await params).id} />;
}

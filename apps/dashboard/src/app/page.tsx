import CommandCenter from "@/components/command-center";
export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ auth?: string }>;
}) {
  return <CommandCenter authError={(await searchParams).auth} />;
}

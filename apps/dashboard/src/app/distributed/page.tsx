import DistributedJobs from "../../components/shared-inference-jobs";
import { requireUser } from "../../lib/control-server";
export default async function DistributedPage({
  searchParams,
}: {
  searchParams: Promise<{ workspace?: string }>;
}) {
  return (
    <DistributedJobs
      user={await requireUser()}
      initialWorkspace={(await searchParams).workspace || ""}
    />
  );
}

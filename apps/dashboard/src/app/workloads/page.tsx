import Workloads from "../../components/workloads";
import { requireUser } from "../../lib/control-server";

export default async function Page() {
  return <Workloads user={await requireUser()} />;
}

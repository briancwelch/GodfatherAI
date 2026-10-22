import Workloads from "../../components/workloads";
import { requireUser } from "../../lib/control-server";
export default async function AnalyticsPage() {
  return <Workloads user={await requireUser()} workflow="analytics" />;
}

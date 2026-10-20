import ProviderConnections from "../../components/provider-connections";
import { requireUser } from "../../lib/control-server";

export default async function Page() {
  const user = await requireUser();
  return <ProviderConnections user={user} />;
}

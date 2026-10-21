import AccountConnections from "../../components/account-connections";
import { requireUser } from "../../lib/control-server";

export default async function Page() {
  const user = await requireUser();
  return <AccountConnections user={user} />;
}

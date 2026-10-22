import AccountProfile from "../../components/account-profile";
import { requireUser } from "../../lib/control-server";
export default async function AccountPage() {
  return <AccountProfile initialUser={await requireUser()} />;
}
